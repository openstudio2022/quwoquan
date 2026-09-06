package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

type releaseIdentityDocument struct {
	Environment    string `bson:"environment"`
	SourceOwner    string `bson:"sourceOwner"`
	ReleaseID      string `bson:"releaseId"`
	ManifestDigest string `bson:"manifestDigest"`
}

type homepageReleaseProjectionDocument struct {
	Environment          string                            `bson:"environment"`
	SourceOwner          string                            `bson:"sourceOwner"`
	ReleaseID            string                            `bson:"releaseId"`
	ManifestDigest       string                            `bson:"manifestDigest"`
	HomepageID           string                            `bson:"homepageId"`
	EntityRef            string                            `bson:"entityRef"`
	Title                string                            `bson:"title"`
	HomepageType         string                            `bson:"homepageType"`
	City                 string                            `bson:"city,omitempty"`
	Location             *geoJSONPoint                     `bson:"location,omitempty"`
	CategoryTags         []string                          `bson:"categoryTags,omitempty"`
	CoverURL             string                            `bson:"coverUrl,omitempty"`
	IntroductionMarkdown string                            `bson:"introductionMarkdown,omitempty"`
	IntroductionAssets   []homepagemodel.IntroductionAsset `bson:"introductionAssets,omitempty"`
	StructuredFacts      *homepagemodel.StructuredFacts    `bson:"structuredFacts,omitempty"`
	PrimarySource        *homepagemodel.Source             `bson:"primarySource,omitempty"`
	SourceURLs           []string                          `bson:"sourceUrls,omitempty"`
	ProjectionVersion    int64                             `bson:"projectionVersion"`
	ClosureDigest        string                            `bson:"closureDigest"`
	DocumentDigest       string                            `bson:"documentDigest"`
	VerifiedAt           time.Time                         `bson:"verifiedAt"`
}

type homepageReleaseCandidateStateDocument struct {
	Environment            string    `bson:"environment"`
	SourceOwner            string    `bson:"sourceOwner"`
	ReleaseID              string    `bson:"releaseId"`
	ManifestDigest         string    `bson:"manifestDigest"`
	ProjectionVersion      int64     `bson:"projectionVersion"`
	VerifiedAt             time.Time `bson:"verifiedAt"`
	ClosureDigest          string    `bson:"closureDigest"`
	ExpectedCount          int       `bson:"expectedCount"`
	ProjectedCount         int       `bson:"projectedCount"`
	EntityRefMappingDigest string    `bson:"entityRefMappingDigest"`
}

func (s *MongoHomepageStore) StageReleaseCandidate(
	ctx context.Context,
	state homepageports.ReleaseCandidateState,
	projections []homepageports.ReleaseProjection,
) (bool, error) {
	filter := releaseIdentityFilter(state.Identity)
	var current homepageReleaseCandidateStateDocument
	err := s.releaseCandidateStates.FindOne(ctx, filter).Decode(&current)
	if err == nil {
		return s.validateStoredReleaseCandidate(ctx, state, projections, current)
	}
	if err != mongo.ErrNoDocuments {
		return false, fmt.Errorf("read exact Homepage release candidate: %w", err)
	}
	session, err := s.releaseProjections.Database().Client().StartSession()
	if err != nil {
		return false, err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var existing homepageReleaseCandidateStateDocument
		readErr := s.releaseCandidateStates.FindOne(txCtx, filter).Decode(&existing)
		if readErr == nil {
			return nil, fmt.Errorf("homepage release candidate already exists")
		}
		if readErr != mongo.ErrNoDocuments {
			return nil, readErr
		}
		if len(projections) > 0 {
			documents := make([]any, 0, len(projections))
			for _, projection := range projections {
				documents = append(documents, releaseProjectionDocument(projection))
			}
			if _, insertErr := s.releaseProjections.InsertMany(txCtx, documents); insertErr != nil {
				return nil, insertErr
			}
		}
		_, insertErr := s.releaseCandidateStates.InsertOne(txCtx, releaseCandidateStateDocument(state))
		return nil, insertErr
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) || strings.Contains(err.Error(), "already exists") {
			if readErr := s.releaseCandidateStates.FindOne(ctx, filter).Decode(&current); readErr != nil {
				return false, err
			}
			return s.validateStoredReleaseCandidate(ctx, state, projections, current)
		}
		return false, fmt.Errorf("stage Homepage release candidate: %w", err)
	}
	return false, nil
}

func (s *MongoHomepageStore) validateStoredReleaseCandidate(
	ctx context.Context,
	expected homepageports.ReleaseCandidateState,
	projections []homepageports.ReleaseProjection,
	current homepageReleaseCandidateStateDocument,
) (bool, error) {
	actual := current.state()
	if !sameMongoReleaseCandidateState(actual, expected) {
		return false, fmt.Errorf("homepage release candidate drift for exact tuple")
	}
	var documents []homepageReleaseProjectionDocument
	cursor, err := s.releaseProjections.Find(ctx, releaseIdentityFilter(expected.Identity))
	if err != nil {
		return false, err
	}
	defer cursor.Close(ctx)
	if err := cursor.All(ctx, &documents); err != nil {
		return false, err
	}
	if len(documents) != len(projections) || len(documents) != expected.ProjectedCount {
		return false, fmt.Errorf("homepage release candidate closure drift for exact tuple")
	}
	byID := make(map[string]homepageReleaseProjectionDocument, len(documents))
	for _, document := range documents {
		byID[document.HomepageID] = document
	}
	for _, projection := range projections {
		document, found := byID[projection.HomepageID]
		if !found || document.EntityRef != projection.EntityRef || document.DocumentDigest != projection.DocumentDigest ||
			document.ProjectionVersion != expected.ProjectionVersion || document.ClosureDigest != expected.ClosureDigest {
			return false, fmt.Errorf("homepage release candidate projection drift for exact tuple")
		}
	}
	return true, nil
}

func (s *MongoHomepageStore) ReadVerifiedReleaseCandidate(
	ctx context.Context,
	identity homepageports.ReleaseIdentity,
) (homepageports.ReleaseCandidateState, bool, error) {
	if err := s.requireReleaseProjectionIndexes(ctx); err != nil {
		return homepageports.ReleaseCandidateState{}, false, err
	}
	var document homepageReleaseCandidateStateDocument
	err := s.releaseCandidateStates.FindOne(ctx, releaseIdentityFilter(identity)).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return homepageports.ReleaseCandidateState{}, false, nil
	}
	if err != nil {
		return homepageports.ReleaseCandidateState{}, false, err
	}
	state := document.state()
	if state.ProjectionVersion <= 0 || state.VerifiedAt.IsZero() || state.ClosureDigest == "" ||
		state.EntityRefMappingDigest == "" || state.ExpectedCount < 0 ||
		state.ExpectedCount != state.ProjectedCount {
		return homepageports.ReleaseCandidateState{}, false, fmt.Errorf("homepage release candidate state is invalid")
	}
	cursor, err := s.releaseProjections.Find(ctx, releaseIdentityFilter(identity))
	if err != nil {
		return homepageports.ReleaseCandidateState{}, false, err
	}
	defer cursor.Close(ctx)
	var documents []homepageReleaseProjectionDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return homepageports.ReleaseCandidateState{}, false, err
	}
	if err := validateMongoReleaseClosure(state, documents); err != nil {
		return homepageports.ReleaseCandidateState{}, false, err
	}
	return state, true, nil
}

func (s *MongoHomepageStore) LoadExactReleaseProjection(
	ctx context.Context,
	identity homepageports.ReleaseIdentity,
	homepageID string,
) (homepageports.ReleaseProjection, bool, error) {
	state, found, err := s.ReadVerifiedReleaseCandidate(ctx, identity)
	if err != nil || !found {
		return homepageports.ReleaseProjection{}, false, err
	}
	filter := releaseIdentityFilter(identity)
	filter["homepageId"] = strings.TrimSpace(homepageID)
	filter["projectionVersion"] = state.ProjectionVersion
	filter["closureDigest"] = state.ClosureDigest
	var document homepageReleaseProjectionDocument
	err = s.releaseProjections.FindOne(ctx, filter).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return homepageports.ReleaseProjection{}, false, nil
	}
	if err != nil {
		return homepageports.ReleaseProjection{}, false, err
	}
	return document.projection(), true, nil
}

func releaseIdentityFilter(identity homepageports.ReleaseIdentity) bson.M {
	return bson.M{
		"environment":    strings.TrimSpace(identity.Environment),
		"sourceOwner":    strings.TrimSpace(identity.SourceOwner),
		"releaseId":      strings.TrimSpace(identity.ReleaseID),
		"manifestDigest": strings.TrimSpace(identity.ManifestDigest),
	}
}

func releaseCandidateStateDocument(state homepageports.ReleaseCandidateState) homepageReleaseCandidateStateDocument {
	return homepageReleaseCandidateStateDocument{
		Environment: state.Identity.Environment, SourceOwner: state.Identity.SourceOwner,
		ReleaseID: state.Identity.ReleaseID, ManifestDigest: state.Identity.ManifestDigest,
		ProjectionVersion: state.ProjectionVersion, VerifiedAt: state.VerifiedAt.UTC(),
		ClosureDigest: state.ClosureDigest, ExpectedCount: state.ExpectedCount,
		ProjectedCount: state.ProjectedCount, EntityRefMappingDigest: state.EntityRefMappingDigest,
	}
}

func (d homepageReleaseCandidateStateDocument) state() homepageports.ReleaseCandidateState {
	return homepageports.ReleaseCandidateState{
		Identity: homepageports.ReleaseIdentity{
			Environment: d.Environment, SourceOwner: d.SourceOwner,
			ReleaseID: d.ReleaseID, ManifestDigest: d.ManifestDigest,
		},
		ProjectionVersion: d.ProjectionVersion, VerifiedAt: d.VerifiedAt.UTC(),
		ClosureDigest: d.ClosureDigest, ExpectedCount: d.ExpectedCount,
		ProjectedCount: d.ProjectedCount, EntityRefMappingDigest: d.EntityRefMappingDigest,
	}
}

func releaseProjectionDocument(value homepageports.ReleaseProjection) homepageReleaseProjectionDocument {
	return homepageReleaseProjectionDocument{
		Environment: value.Identity.Environment, SourceOwner: value.Identity.SourceOwner,
		ReleaseID: value.Identity.ReleaseID, ManifestDigest: value.Identity.ManifestDigest,
		HomepageID: value.HomepageID, EntityRef: value.EntityRef, Title: value.Title,
		HomepageType: value.HomepageType, City: value.City, Location: geoJSONFromGeoPoint(value.Location),
		CategoryTags: value.CategoryTags, CoverURL: value.CoverURL,
		IntroductionMarkdown: value.IntroductionMarkdown, IntroductionAssets: value.IntroductionAssets,
		StructuredFacts: value.StructuredFacts, PrimarySource: value.PrimarySource,
		SourceURLs: value.SourceURLs, ProjectionVersion: value.ProjectionVersion,
		ClosureDigest: value.ClosureDigest, DocumentDigest: value.DocumentDigest,
		VerifiedAt: value.VerifiedAt.UTC(),
	}
}

func (d homepageReleaseProjectionDocument) projection() homepageports.ReleaseProjection {
	return homepageports.ReleaseProjection{
		Identity: homepageports.ReleaseIdentity{
			Environment: d.Environment, SourceOwner: d.SourceOwner,
			ReleaseID: d.ReleaseID, ManifestDigest: d.ManifestDigest,
		},
		HomepageID: d.HomepageID, EntityRef: d.EntityRef, Title: d.Title,
		HomepageType: d.HomepageType, City: d.City, Location: d.Location.geoPoint(),
		CategoryTags: d.CategoryTags, CoverURL: d.CoverURL,
		IntroductionMarkdown: d.IntroductionMarkdown, IntroductionAssets: d.IntroductionAssets,
		StructuredFacts: d.StructuredFacts, PrimarySource: d.PrimarySource,
		SourceURLs: d.SourceURLs, ProjectionVersion: d.ProjectionVersion,
		ClosureDigest: d.ClosureDigest, DocumentDigest: d.DocumentDigest,
		VerifiedAt: d.VerifiedAt.UTC(),
	}
}

func sameMongoReleaseCandidateState(left, right homepageports.ReleaseCandidateState) bool {
	return left.Identity == right.Identity && left.ProjectionVersion == right.ProjectionVersion &&
		left.ClosureDigest == right.ClosureDigest && left.ExpectedCount == right.ExpectedCount &&
		left.ProjectedCount == right.ProjectedCount && left.EntityRefMappingDigest == right.EntityRefMappingDigest
}

func (s *MongoHomepageStore) requireReleaseProjectionIndexes(ctx context.Context) error {
	type expectedIndex struct {
		collection *mongo.Collection
		name       string
		keys       bson.D
	}
	expected := []expectedIndex{
		{s.releaseProjections, "uq_homepage_release_projection_identity", bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)}, {Key: "entityRef", Value: int32(1)}}},
		{s.releaseProjections, "uq_homepage_release_projection_homepage", bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)}, {Key: "homepageId", Value: int32(1)}}},
		{s.releaseCandidateStates, "uq_homepage_release_candidate_state", bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)}}},
	}
	for _, item := range expected {
		cursor, err := item.collection.Indexes().List(ctx)
		if err != nil {
			return fmt.Errorf("inspect Homepage release candidate indexes: %w", err)
		}
		var indexes []struct {
			Name   string `bson:"name"`
			Key    bson.D `bson:"key"`
			Unique bool   `bson:"unique"`
		}
		if err := cursor.All(ctx, &indexes); err != nil {
			return err
		}
		found := false
		for _, actual := range indexes {
			if actual.Name == item.name {
				found = actual.Unique && releaseIndexKeysEqual(actual.Key, item.keys)
				break
			}
		}
		if !found {
			return fmt.Errorf("required Homepage release candidate index %s.%s is absent or incompatible", item.collection.Name(), item.name)
		}
	}
	return nil
}

func releaseIndexKeysEqual(left, right bson.D) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index].Key != right[index].Key || fmt.Sprint(left[index].Value) != fmt.Sprint(right[index].Value) {
			return false
		}
	}
	return true
}

func validateMongoReleaseClosure(state homepageports.ReleaseCandidateState, documents []homepageReleaseProjectionDocument) error {
	if len(documents) != state.ProjectedCount {
		return fmt.Errorf("homepage release candidate closure count drift")
	}
	type closureEntry struct {
		EntityRef      string `json:"entityRef"`
		HomepageID     string `json:"homepageId"`
		DocumentDigest string `json:"documentDigest"`
	}
	type mappingEntry struct {
		EntityRef  string `json:"entityRef"`
		HomepageID string `json:"homepageId"`
	}
	sort.Slice(documents, func(i, j int) bool { return documents[i].EntityRef < documents[j].EntityRef })
	closure := make([]closureEntry, 0, len(documents))
	mapping := make([]mappingEntry, 0, len(documents))
	seenRefs := map[string]bool{}
	seenIDs := map[string]bool{}
	for _, document := range documents {
		projection := document.projection()
		if projection.Identity != state.Identity || projection.ProjectionVersion != state.ProjectionVersion ||
			projection.ClosureDigest != state.ClosureDigest || seenRefs[projection.EntityRef] || seenIDs[projection.HomepageID] {
			return fmt.Errorf("homepage release candidate projection identity drift")
		}
		seenRefs[projection.EntityRef] = true
		seenIDs[projection.HomepageID] = true
		expectedDocumentDigest := projection.DocumentDigest
		projection.ProjectionVersion = 0
		projection.ClosureDigest = ""
		projection.DocumentDigest = ""
		projection.VerifiedAt = time.Time{}
		actualDocumentDigest, err := mongoReleaseDigest(projection)
		if err != nil || actualDocumentDigest != expectedDocumentDigest {
			return fmt.Errorf("homepage release candidate document digest drift")
		}
		closure = append(closure, closureEntry{projection.EntityRef, projection.HomepageID, expectedDocumentDigest})
		mapping = append(mapping, mappingEntry{projection.EntityRef, projection.HomepageID})
	}
	closureDigest, err := mongoReleaseDigest(closure)
	if err != nil || closureDigest != state.ClosureDigest {
		return fmt.Errorf("homepage release candidate closure digest drift")
	}
	mappingDigest, err := mongoReleaseDigest(mapping)
	if err != nil || mappingDigest != state.EntityRefMappingDigest {
		return fmt.Errorf("homepage release candidate mapping digest drift")
	}
	return nil
}

func mongoReleaseDigest(value any) (string, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

func (s *MongoHomepageStore) EnsureReleaseShells(
	ctx context.Context,
	projections []homepageports.ReleaseProjection,
) error {
	for _, projection := range projections {
		var current homepageDocument
		err := s.homepages.FindOne(ctx, bson.M{"_id": projection.HomepageID}).Decode(&current)
		if err == nil {
			if current.SourceOwner != projection.Identity.SourceOwner || current.SourceEntityRef != projection.EntityRef {
				return fmt.Errorf("homepage release shell identity conflict")
			}
			continue
		}
		if err != mongo.ErrNoDocuments {
			return err
		}
		aggregate, err := homepagemodel.NewReleaseShell(
			projection.HomepageID, projection.EntityRef, projection.HomepageType,
			projection.Title, projection.Identity.SourceOwner, projection.VerifiedAt,
		)
		if err != nil {
			return err
		}
		if _, err := s.homepages.InsertOne(ctx, documentFromSnapshot(aggregate.Snapshot())); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				if readErr := s.homepages.FindOne(ctx, bson.M{"_id": projection.HomepageID}).Decode(&current); readErr == nil &&
					current.SourceOwner == projection.Identity.SourceOwner && current.SourceEntityRef == projection.EntityRef {
					continue
				}
			}
			return fmt.Errorf("create homepage release identity shell: %w", err)
		}
	}
	return nil
}
