package publicweb

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"net/url"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
)

type evidenceDocument struct {
	ID                string    `bson:"_id"`
	RunID             string    `bson:"runId"`
	RecordKind        string    `bson:"recordKind"`
	TargetID          string    `bson:"targetId,omitempty"`
	DocumentID        string    `bson:"documentId,omitempty"`
	SourceID          string    `bson:"sourceId,omitempty"`
	ArtifactID        string    `bson:"artifactId,omitempty"`
	TargetRef         string    `bson:"targetRef,omitempty"`
	SourceRef         string    `bson:"sourceRef,omitempty"`
	ArtifactRecordRef string    `bson:"artifactRecordRef,omitempty"`
	LinkIDs           []string  `bson:"linkIds,omitempty"`
	FetchedAt         time.Time `bson:"fetchedAt"`

	Target   *application.TargetLedgerEntry `bson:"target,omitempty"`
	Source   *application.SourceLedgerEntry `bson:"source,omitempty"`
	Document *application.Document          `bson:"document,omitempty"`
	Artifact *application.Artifact          `bson:"artifact,omitempty"`
}

// MongoEvidenceStore 是 AssistantRun 的 authoritative Public Web 来源账本、
// DocumentReader 与 ReferenceLookup。URL 与父级来源永远从该存储回查。
type MongoEvidenceStore struct {
	collection *mongo.Collection
}

func NewMongoEvidenceStore(database *mongo.Database) *MongoEvidenceStore {
	if database == nil {
		panic("public web evidence database is required")
	}
	return &MongoEvidenceStore{
		collection: database.Collection("assistant_run_web_evidence"),
	}
}

func (s *MongoEvidenceStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "runId", Value: 1}, {Key: "targetId", Value: 1}},
			Options: options.Index().SetName("uq_web_evidence_run_target").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"targetId": bson.M{"$type": "string"},
				}),
		},
		{
			Keys: bson.D{{Key: "runId", Value: 1}, {Key: "documentId", Value: 1}},
			Options: options.Index().SetName("uq_web_evidence_run_document").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"documentId": bson.M{"$type": "string"},
				}),
		},
		{
			Keys: bson.D{{Key: "runId", Value: 1}, {Key: "sourceId", Value: 1}},
			Options: options.Index().SetName("uq_web_evidence_run_source").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"sourceId": bson.M{"$type": "string"},
				}),
		},
		{
			Keys: bson.D{{Key: "runId", Value: 1}, {Key: "artifactId", Value: 1}},
			Options: options.Index().SetName("uq_web_evidence_run_artifact").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"artifactId": bson.M{"$type": "string"},
				}),
		},
		{
			Keys:    bson.D{{Key: "runId", Value: 1}, {Key: "linkIds", Value: 1}},
			Options: options.Index().SetName("idx_web_evidence_run_link"),
		},
		{
			Keys:    bson.D{{Key: "runId", Value: 1}, {Key: "fetchedAt", Value: -1}},
			Options: options.Index().SetName("idx_web_evidence_run_fetched"),
		},
	})
	if err != nil {
		return fmt.Errorf("create public web evidence indexes: %w", err)
	}
	return nil
}

func (s *MongoEvidenceStore) CommitEvidence(
	ctx context.Context,
	record application.EvidenceRecord,
) error {
	if err := validateEvidence(record); err != nil {
		return err
	}
	linkIDs := make([]string, 0, len(record.Document.Links))
	for _, link := range record.Document.Links {
		linkIDs = append(linkIDs, link.LinkID)
	}
	runID := record.Target.RunID
	target := record.Target
	source := record.Source
	document := record.Document
	artifact := record.Artifact
	// Document and Source are joined on read. Persisting the embedded copies
	// would create competing URL, lineage and artifact truth.
	document.Source = application.SourceLedgerEntry{}
	document.Target = application.Target{}
	records := []any{
		evidenceDocument{
			ID: "target:" + runID + ":" + target.TargetID, RunID: runID,
			RecordKind: "target", TargetID: target.TargetID,
			FetchedAt: target.ResolvedAt.UTC(), Target: &target,
		},
		evidenceDocument{
			ID: "source:" + runID + ":" + source.SourceID, RunID: runID,
			RecordKind: "source", SourceID: source.SourceID,
			TargetRef: source.TargetID, FetchedAt: source.FetchedAt.UTC(),
			Source: &source,
		},
		evidenceDocument{
			ID: "document:" + runID + ":" + document.DocumentID, RunID: runID,
			RecordKind: "document", DocumentID: document.DocumentID,
			TargetRef: document.TargetID, SourceRef: source.SourceID,
			ArtifactRecordRef: artifact.ArtifactID, LinkIDs: linkIDs,
			FetchedAt: document.FetchedAt.UTC(), Document: &document,
		},
		evidenceDocument{
			ID: "artifact:" + runID + ":" + artifact.ArtifactID, RunID: runID,
			RecordKind: "artifact", ArtifactID: artifact.ArtifactID,
			FetchedAt: artifact.FetchedAt.UTC(), Artifact: &artifact,
		},
	}
	session, err := s.collection.Database().Client().StartSession()
	if err != nil {
		return fmt.Errorf("%w: start ledger transaction: %v", application.ErrEvidenceCommit, err)
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		_, insertErr := s.collection.InsertMany(txCtx, records)
		return nil, insertErr
	})
	if err == nil {
		return nil
	}
	if !mongo.IsDuplicateKeyError(err) {
		return fmt.Errorf("%w: %v", application.ErrEvidenceCommit, err)
	}
	matches, verifyErr := s.evidenceMatches(ctx, record)
	if verifyErr == nil && matches {
		return nil
	}
	if verifyErr != nil {
		return fmt.Errorf("%w: verify replay: %v", application.ErrEvidenceCommit, verifyErr)
	}
	return fmt.Errorf("%w: immutable ledger identity conflict", application.ErrEvidenceCommit)
}

func (s *MongoEvidenceStore) RecordSearchReferences(
	ctx context.Context,
	runID string,
	references []application.SearchReference,
) ([]application.DiscoveredSource, error) {
	runID = strings.TrimSpace(runID)
	if runID == "" {
		return nil, application.ErrEvidenceCommit
	}
	discovered := make([]application.DiscoveredSource, 0, len(references))
	for _, reference := range references {
		normalizedURL, ok := normalizedSearchURL(reference.URL)
		if !ok {
			continue
		}
		sourceID := discoveredSourceID(runID, normalizedURL)
		fetchedAt := time.Now().UTC()
		source := application.SourceLedgerEntry{
			SourceID:      sourceID,
			Origin:        "web_search",
			RunID:         runID,
			NormalizedURL: normalizedURL,
			FetchedAt:     fetchedAt,
		}
		record := evidenceDocument{
			ID:         "source:" + runID + ":" + sourceID,
			RunID:      runID,
			SourceID:   sourceID,
			RecordKind: "search_discovery",
			FetchedAt:  fetchedAt,
			Source:     &source,
		}
		if _, err := s.collection.UpdateOne(
			ctx,
			bson.M{"_id": record.ID},
			bson.M{"$setOnInsert": record},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return nil, fmt.Errorf("%w: record public web search source: %v", application.ErrEvidenceCommit, err)
		}
		discovered = append(discovered, application.DiscoveredSource{
			SourceID: sourceID, NormalizedURL: normalizedURL,
		})
	}
	return discovered, nil
}

func (s *MongoEvidenceStore) ReadDocument(
	ctx context.Context,
	runID string,
	documentID string,
) (application.Document, error) {
	stored, err := s.read(ctx, bson.M{
		"runId":      strings.TrimSpace(runID),
		"documentId": strings.TrimSpace(documentID),
		"recordKind": "document",
	})
	if err != nil {
		return application.Document{}, err
	}
	if stored.Document == nil {
		return application.Document{}, application.ErrEvidenceUnavailable
	}
	source, err := s.readSource(ctx, runID, stored.SourceRef)
	if err != nil {
		return application.Document{}, err
	}
	target, err := s.readTarget(ctx, runID, stored.TargetRef)
	if err != nil {
		return application.Document{}, err
	}
	document := *stored.Document
	document.Source = source
	document.Target = target.Requested
	return document, nil
}

func (s *MongoEvidenceStore) LookupSource(
	ctx context.Context,
	runID string,
	sourceID string,
) (application.StoredSource, error) {
	stored, err := s.read(ctx, bson.M{
		"runId":    strings.TrimSpace(runID),
		"sourceId": strings.TrimSpace(sourceID),
	})
	if err != nil {
		return application.StoredSource{}, err
	}
	if stored.Source == nil {
		return application.StoredSource{}, application.ErrEvidenceUnavailable
	}
	return application.StoredSource{
		SourceID:      stored.Source.SourceID,
		NormalizedURL: stored.Source.NormalizedURL,
	}, nil
}

func normalizedSearchURL(raw string) (string, bool) {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || !parsed.IsAbs() || !strings.EqualFold(parsed.Scheme, "https") ||
		parsed.Hostname() == "" || parsed.User != nil ||
		(parsed.Port() != "" && parsed.Port() != "443") {
		return "", false
	}
	parsed.Scheme = "https"
	parsed.Fragment = ""
	return parsed.String(), true
}

func discoveredSourceID(runID, normalizedURL string) string {
	digest := sha256.Sum256([]byte(runID + "\x00" + normalizedURL))
	return "src_search_" + hex.EncodeToString(digest[:12])
}

func (s *MongoEvidenceStore) LookupDocumentLink(
	ctx context.Context,
	runID string,
	linkID string,
) (application.StoredDocumentLink, error) {
	stored, err := s.read(ctx, bson.M{
		"runId":      strings.TrimSpace(runID),
		"linkIds":    strings.TrimSpace(linkID),
		"recordKind": "document",
	})
	if err != nil {
		return application.StoredDocumentLink{}, err
	}
	if stored.Document == nil {
		return application.StoredDocumentLink{}, application.ErrEvidenceUnavailable
	}
	for _, link := range stored.Document.Links {
		if link.LinkID == strings.TrimSpace(linkID) &&
			link.Target.Kind == application.TargetURL {
			return application.StoredDocumentLink{
				LinkID:         link.LinkID,
				URL:            link.Target.Value,
				ParentSourceID: stored.SourceRef,
			}, nil
		}
	}
	return application.StoredDocumentLink{}, application.ErrTargetUnavailable
}

func (s *MongoEvidenceStore) ReadTarget(
	ctx context.Context,
	runID string,
	targetID string,
) (application.TargetLedgerEntry, error) {
	return s.readTarget(ctx, runID, targetID)
}

func (s *MongoEvidenceStore) readTarget(
	ctx context.Context,
	runID string,
	targetID string,
) (application.TargetLedgerEntry, error) {
	stored, err := s.read(ctx, bson.M{
		"runId":      strings.TrimSpace(runID),
		"targetId":   strings.TrimSpace(targetID),
		"recordKind": "target",
	})
	if err != nil {
		return application.TargetLedgerEntry{}, err
	}
	if stored.Target == nil {
		return application.TargetLedgerEntry{}, application.ErrEvidenceUnavailable
	}
	return *stored.Target, nil
}

func (s *MongoEvidenceStore) ReadSource(
	ctx context.Context,
	runID string,
	sourceID string,
) (application.SourceLedgerEntry, error) {
	return s.readSource(ctx, runID, sourceID)
}

func (s *MongoEvidenceStore) readSource(
	ctx context.Context,
	runID string,
	sourceID string,
) (application.SourceLedgerEntry, error) {
	stored, err := s.read(ctx, bson.M{
		"runId":    strings.TrimSpace(runID),
		"sourceId": strings.TrimSpace(sourceID),
	})
	if err != nil {
		return application.SourceLedgerEntry{}, err
	}
	if stored.Source == nil {
		return application.SourceLedgerEntry{}, application.ErrEvidenceUnavailable
	}
	return *stored.Source, nil
}

func (s *MongoEvidenceStore) ReadArtifact(
	ctx context.Context,
	runID string,
	artifactRef string,
) (application.Artifact, error) {
	stored, err := s.read(ctx, bson.M{
		"runId":                strings.TrimSpace(runID),
		"recordKind":           "artifact",
		"artifact.artifactRef": strings.TrimSpace(artifactRef),
	})
	if err != nil {
		return application.Artifact{}, err
	}
	if stored.Artifact == nil {
		return application.Artifact{}, application.ErrEvidenceUnavailable
	}
	return *stored.Artifact, nil
}

func (s *MongoEvidenceStore) evidenceMatches(
	ctx context.Context,
	record application.EvidenceRecord,
) (bool, error) {
	runID := record.Target.RunID
	target, err := s.ReadTarget(ctx, runID, record.Target.TargetID)
	if err != nil {
		return false, err
	}
	source, err := s.ReadSource(ctx, runID, record.Source.SourceID)
	if err != nil {
		return false, err
	}
	document, err := s.ReadDocument(ctx, runID, record.Document.DocumentID)
	if err != nil {
		return false, err
	}
	artifact, err := s.ReadArtifact(ctx, runID, record.Artifact.ArtifactRef)
	if err != nil {
		return false, err
	}
	return target.TargetID == record.Target.TargetID &&
			target.ResolvedURL == record.Target.ResolvedURL &&
			source.TargetID == record.Source.TargetID &&
			source.ContentDigest == record.Source.ContentDigest &&
			document.TargetID == record.Document.TargetID &&
			document.Source.SourceID == record.Source.SourceID &&
			document.ContentDigest == record.Document.ContentDigest &&
			document.ArtifactRef == record.Artifact.ArtifactRef &&
			artifact.ArtifactID == record.Artifact.ArtifactID &&
			artifact.ContentDigest == record.Artifact.ContentDigest &&
			artifact.ByteLength == record.Artifact.ByteLength,
		nil
}

func (s *MongoEvidenceStore) read(
	ctx context.Context,
	filter bson.M,
) (evidenceDocument, error) {
	var stored evidenceDocument
	err := s.collection.FindOne(ctx, filter).Decode(&stored)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return evidenceDocument{}, application.ErrTargetUnavailable
	}
	if err != nil {
		return evidenceDocument{}, fmt.Errorf("%w: %v", application.ErrEvidenceUnavailable, err)
	}
	return stored, nil
}

func validateEvidence(record application.EvidenceRecord) error {
	target := record.Target
	source := record.Source
	document := record.Document
	artifact := record.Artifact
	runID := strings.TrimSpace(target.RunID)
	if runID == "" ||
		strings.TrimSpace(target.TargetID) == "" ||
		strings.TrimSpace(target.ResolvedURL) == "" ||
		strings.TrimSpace(source.SourceID) == "" ||
		strings.TrimSpace(document.DocumentID) == "" ||
		strings.TrimSpace(artifact.ArtifactID) == "" ||
		strings.TrimSpace(artifact.ArtifactRef) == "" ||
		target.Requested.Kind == "" ||
		strings.TrimSpace(target.Requested.Value) == "" ||
		target.ResolvedAt.IsZero() ||
		source.RunID != runID ||
		artifact.RunID != runID ||
		source.TargetID != target.TargetID ||
		document.TargetID != target.TargetID ||
		document.Source.SourceID != source.SourceID ||
		document.Source.RunID != runID ||
		document.ArtifactRef != artifact.ArtifactRef ||
		document.ContentDigest != artifact.ContentDigest ||
		document.ContentDigest != source.ContentDigest ||
		int64(len(artifact.Body)) != artifact.ByteLength ||
		!document.Untrusted ||
		!artifact.Untrusted {
		return application.ErrEvidenceCommit
	}
	digest := sha256.Sum256(artifact.Body)
	if hex.EncodeToString(digest[:]) != document.ContentDigest ||
		artifact.ArtifactRef != "sha256:"+document.ContentDigest {
		return application.ErrEvidenceCommit
	}
	return nil
}
