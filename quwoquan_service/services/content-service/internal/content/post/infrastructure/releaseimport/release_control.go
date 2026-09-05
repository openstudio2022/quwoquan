package releaseimport

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	ContentReleaseCandidateReceiptSchema  = "quwoquan.content_release_candidate_receipt"
	ContentReleaseActiveReceiptSchema     = "quwoquan.content_release_active_receipt"
	ContentReleaseActivationReceiptSchema = "quwoquan.content_release_activation_receipt"
)

// ImportedReleaseCandidateClosureDigests is an immutable copy of the three
// Content-owned candidate closure digests. It exposes no Mongo documents.
type ImportedReleaseCandidateClosureDigests struct {
	Posts string `json:"posts"`
	Facts string `json:"facts"`
	Media string `json:"media"`
}

// ImportedReleaseCandidateCounts is an immutable copy of the verified
// candidate counts persisted by Content.
type ImportedReleaseCandidateCounts struct {
	PostsExpected   int `json:"postsExpected"`
	PostsProjected  int `json:"postsProjected"`
	OutboxExpected  int `json:"outboxExpected"`
	OutboxProjected int `json:"outboxProjected"`
	MediaExpected   int `json:"mediaExpected"`
	MediaProjected  int `json:"mediaProjected"`
}

// VerifiedImportedPostReleaseCandidate is the strict read-only query result
// for one exact environment/owner/release/digest identity. Found=false means
// only that this exact candidate is absent after index and legacy-shape checks.
type VerifiedImportedPostReleaseCandidate struct {
	Found             bool
	Environment       string
	SourceOwner       string
	ReleaseID         string
	ManifestDigest    string
	ReleaseClass      string
	ReleaseKind       string
	Mode              string
	DeletePolicy      string
	ProjectionVersion int64
	VerifiedAt        time.Time
	ClosureDigests    ImportedReleaseCandidateClosureDigests
	Counts            ImportedReleaseCandidateCounts
}

// ReadVerifiedImportedPostReleaseCandidate verifies and returns one exact
// Content-owned candidate without creating indexes or mutating release state.
func ReadVerifiedImportedPostReleaseCandidate(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	sourceOwner string,
	releaseID string,
	manifestDigest string,
) (VerifiedImportedPostReleaseCandidate, error) {
	if database == nil {
		return VerifiedImportedPostReleaseCandidate{}, fmt.Errorf("content release database is required")
	}
	environment = strings.TrimSpace(environment)
	sourceOwner = strings.TrimSpace(sourceOwner)
	releaseID = strings.TrimSpace(releaseID)
	manifestDigest = strings.TrimSpace(manifestDigest)
	identity := VerifiedImportedPostReleaseCandidate{
		Environment: environment, SourceOwner: sourceOwner,
		ReleaseID: releaseID, ManifestDigest: manifestDigest,
	}
	if environment == "" || sourceOwner == "" || releaseID == "" ||
		!sha256Pattern.MatchString(manifestDigest) {
		return VerifiedImportedPostReleaseCandidate{}, fmt.Errorf("verified candidate query binding is incomplete or non-canonical")
	}

	state := database.Collection("data_release_state")
	candidatePosts := database.Collection("data_release_candidate_posts")
	candidateOutbox := database.Collection("data_release_candidate_outbox")
	candidateMedia := database.Collection("data_release_candidate_media_assets")
	if err := inspectVerifiedCandidateQueryIndexes(
		ctx, state, candidatePosts, candidateOutbox, candidateMedia,
	); err != nil {
		return VerifiedImportedPostReleaseCandidate{}, err
	}
	if err := rejectLegacyReleaseStateShape(ctx, state, environment, sourceOwner); err != nil {
		return VerifiedImportedPostReleaseCandidate{}, err
	}

	var candidate importedReleaseCandidateState
	err := state.FindOne(ctx, bson.M{
		"kind": releaseCandidateKind, "environment": environment,
		"sourceOwner": sourceOwner, "releaseId": releaseID,
		"manifestDigest": manifestDigest,
	}).Decode(&candidate)
	if err == mongo.ErrNoDocuments {
		return identity, nil
	}
	if err != nil {
		return VerifiedImportedPostReleaseCandidate{}, fmt.Errorf("read exact verified Content release candidate: %w", err)
	}
	if err := validateVerifiedCandidateState(
		candidate, environment, sourceOwner, releaseID, manifestDigest,
	); err != nil {
		return VerifiedImportedPostReleaseCandidate{}, err
	}
	if err := validateStoredCandidateClosure(
		ctx, candidatePosts, candidateOutbox, candidateMedia, candidate,
	); err != nil {
		return VerifiedImportedPostReleaseCandidate{}, err
	}
	return verifiedImportedPostReleaseCandidate(candidate), nil
}

func verifiedImportedPostReleaseCandidate(candidate importedReleaseCandidateState) VerifiedImportedPostReleaseCandidate {
	return VerifiedImportedPostReleaseCandidate{
		Found: true, Environment: candidate.Environment,
		SourceOwner: candidate.SourceOwner, ReleaseID: candidate.ReleaseID,
		ManifestDigest: candidate.ManifestDigest, ReleaseClass: candidate.ReleaseClass,
		ReleaseKind: candidate.ReleaseKind, Mode: candidate.Mode,
		DeletePolicy: candidate.DeletePolicy, ProjectionVersion: candidate.ProjectionVersion,
		VerifiedAt: candidate.VerifiedAt,
		ClosureDigests: ImportedReleaseCandidateClosureDigests{
			Posts: candidate.PostClosureDigest,
			Facts: candidate.FactClosureDigest,
			Media: candidate.MediaClosureDigest,
		},
		Counts: ImportedReleaseCandidateCounts{
			PostsExpected:   candidate.Counts.PostsExpected,
			PostsProjected:  candidate.Counts.PostsProjected,
			OutboxExpected:  candidate.Counts.OutboxExpected,
			OutboxProjected: candidate.Counts.OutboxProjected,
			MediaExpected:   candidate.Counts.MediaExpected,
			MediaProjected:  candidate.Counts.MediaProjected,
		},
	}
}

func validateVerifiedCandidateState(
	candidate importedReleaseCandidateState,
	environment string,
	sourceOwner string,
	releaseID string,
	manifestDigest string,
) error {
	if candidate.Kind != releaseCandidateKind || candidate.Environment != environment ||
		candidate.SourceOwner != sourceOwner || candidate.ReleaseID != releaseID ||
		candidate.ManifestDigest != manifestDigest {
		return fmt.Errorf("GATE_BLOCK: verified candidate identity differs from exact query")
	}
	if candidate.Status != "verified" || candidate.ProjectionVersion <= 0 ||
		candidate.VerifiedAt.IsZero() {
		return fmt.Errorf("GATE_BLOCK: candidate state is not completely verified")
	}
	if candidate.ReleaseClass != "research" && candidate.ReleaseClass != "commercial" {
		return fmt.Errorf("GATE_BLOCK: verified candidate releaseClass is invalid")
	}
	if !sha256Pattern.MatchString(candidate.ManifestDigest) {
		return fmt.Errorf("GATE_BLOCK: verified candidate manifestDigest is invalid")
	}
	if err := ValidateImportOptions(ImportOptions{
		ReleaseKind:  candidate.ReleaseKind,
		Mode:         candidate.Mode,
		DeletePolicy: candidate.DeletePolicy,
	}); err != nil {
		return fmt.Errorf("GATE_BLOCK: verified candidate policy is invalid: %w", err)
	}
	for label, digest := range map[string]string{
		"Post":  candidate.PostClosureDigest,
		"fact":  candidate.FactClosureDigest,
		"media": candidate.MediaClosureDigest,
	} {
		if !sha256Pattern.MatchString(digest) {
			return fmt.Errorf("GATE_BLOCK: candidate %s closure digest is invalid", label)
		}
	}
	counts := candidate.Counts
	if counts.PostsExpected < 0 || counts.PostsProjected < 0 ||
		counts.OutboxExpected < 0 || counts.OutboxProjected < 0 ||
		counts.MediaExpected < 0 || counts.MediaProjected < 0 ||
		counts.PostsExpected != counts.PostsProjected ||
		counts.OutboxExpected != counts.OutboxProjected ||
		counts.MediaExpected != counts.MediaProjected ||
		counts.PostsExpected != counts.OutboxExpected {
		return fmt.Errorf("GATE_BLOCK: verified candidate closure counts are invalid")
	}
	return nil
}

func validateStoredActivePointer(
	pointer importedReleasePointerDocument,
	environment string,
	sourceOwner string,
) error {
	if pointer.Kind != releaseActivePointerKind || pointer.Status != "active" ||
		pointer.Environment != environment || pointer.SourceOwner != sourceOwner ||
		strings.TrimSpace(pointer.ActiveReleaseID) == "" ||
		!sha256Pattern.MatchString(pointer.ManifestDigest) ||
		(pointer.ReleaseClass != "research" && pointer.ReleaseClass != "commercial") ||
		pointer.ProjectionVersion <= 0 || pointer.Revision <= 0 || pointer.ActivatedAt.IsZero() {
		return fmt.Errorf("GATE_BLOCK: active Content release pointer is incomplete or invalid")
	}
	return nil
}

func inspectVerifiedCandidateQueryIndexes(
	ctx context.Context,
	state *mongo.Collection,
	candidatePosts *mongo.Collection,
	candidateOutbox *mongo.Collection,
	candidateMedia *mongo.Collection,
) error {
	return requireCanonicalReleaseIndexes(ctx, map[*mongo.Collection][]releaseControlIndexExpectation{
		state: {
			{
				name: "uq_data_release_state_environment_candidate",
				keys: bson.D{
					{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)},
					{Key: "kind", Value: int32(1)}, {Key: "releaseId", Value: int32(1)},
					{Key: "manifestDigest", Value: int32(1)},
				},
				unique: true, partial: bson.D{{Key: "kind", Value: releaseCandidateKind}},
			},
		},
		candidatePosts: {
			{
				name: "uq_data_release_candidate_post",
				keys: bson.D{
					{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)},
					{Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)},
					{Key: "postId", Value: int32(1)},
				}, unique: true,
			},
			{
				name: "idx_data_release_candidate_post_ref",
				keys: bson.D{
					{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)},
					{Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)},
					{Key: "postRef", Value: int32(1)},
				}, unique: true,
			},
		},
		candidateOutbox: {
			{
				name: "uq_data_release_candidate_outbox_event",
				keys: bson.D{
					{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)},
					{Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)},
					{Key: "postId", Value: int32(1)},
				}, unique: true,
			},
		},
		candidateMedia: {
			{
				name: "uq_data_release_candidate_media_asset",
				keys: bson.D{
					{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)},
					{Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)},
					{Key: "assetId", Value: int32(1)},
				}, unique: true,
			},
		},
	})
}

func requireCanonicalReleaseIndexes(
	ctx context.Context,
	expectations map[*mongo.Collection][]releaseControlIndexExpectation,
) error {
	for collection, expectedIndexes := range expectations {
		cursor, err := collection.Indexes().List(ctx)
		if err != nil {
			return fmt.Errorf("inspect verified candidate indexes: %w", err)
		}
		var indexes []struct {
			Name    string `bson:"name"`
			Key     bson.D `bson:"key"`
			Unique  bool   `bson:"unique"`
			Partial bson.D `bson:"partialFilterExpression"`
		}
		if err := cursor.All(ctx, &indexes); err != nil {
			return fmt.Errorf("decode verified candidate indexes: %w", err)
		}
		for _, expected := range expectedIndexes {
			found := false
			for _, actual := range indexes {
				if actual.Name != expected.name {
					continue
				}
				found = true
				if !bsonDocumentsEqual(actual.Key, expected.keys) ||
					actual.Unique != expected.unique ||
					!bsonDocumentsEqual(actual.Partial, expected.partial) {
					return fmt.Errorf(
						"%s: incompatible existing index %s.%s requires explicit migration",
						ReleaseLegacyStateMigrationRequiredCode, collection.Name(), expected.name,
					)
				}
			}
			if !found {
				return fmt.Errorf(
					"%s: required verified candidate index %s.%s is absent",
					ReleaseLegacyStateMigrationRequiredCode, collection.Name(), expected.name,
				)
			}
		}
	}
	return nil
}

// ReleaseControlCommand is the validated command input. All strings are
// trimmed and expected-current input is represented in one typed value.
type ReleaseControlCommand struct {
	Operation      string
	MongoURI       string
	PostsDB        string
	Environment    string
	SourceOwner    string
	ReportPath     string
	ReleaseID      string
	ManifestDigest string
	Expected       ExpectedActiveRelease
}

// ParseReleaseControlCommand rejects mixed, incomplete, and operation-foreign
// flags before any Mongo connection or report creation.
func ParseReleaseControlCommand(args []string) (ReleaseControlCommand, error) {
	set := flag.NewFlagSet("release-control", flag.ContinueOnError)
	set.SetOutput(io.Discard)
	var command ReleaseControlCommand
	var expectedEmpty bool
	var expectedReleaseID string
	var expectedManifestDigest string
	var expectedRevision int64
	set.StringVar(&command.Operation, "operation", "", "query-candidate|query-active|activate")
	set.StringVar(&command.MongoURI, "mongo-uri", "", "MongoDB connection URI")
	set.StringVar(&command.PostsDB, "posts-db", "quwoquan_content", "Content posts database")
	set.StringVar(&command.Environment, "env", "", "exact environment")
	set.StringVar(&command.SourceOwner, "source-owner", "qwq_data", "exact source owner")
	set.StringVar(&command.ReportPath, "report", "", "create-once canonical JSON report")
	set.StringVar(&command.ReleaseID, "release-id", "", "exact target release id")
	set.StringVar(&command.ManifestDigest, "manifest-digest", "", "exact target manifest digest")
	set.BoolVar(&expectedEmpty, "expected-active-empty", false, "expect no active release")
	set.StringVar(&expectedReleaseID, "expected-active-release-id", "", "expected active release id")
	set.StringVar(&expectedManifestDigest, "expected-active-manifest-digest", "", "expected active manifest digest")
	set.Int64Var(&expectedRevision, "expected-active-revision", 0, "expected active revision")
	if err := set.Parse(args); err != nil {
		return ReleaseControlCommand{}, fmt.Errorf("parse release-control flags: %w", err)
	}
	if set.NArg() != 0 {
		return ReleaseControlCommand{}, fmt.Errorf("release-control does not accept positional arguments")
	}
	provided := make(map[string]bool)
	set.Visit(func(item *flag.Flag) {
		provided[item.Name] = true
	})
	command.Operation = strings.TrimSpace(command.Operation)
	command.MongoURI = strings.TrimSpace(command.MongoURI)
	command.PostsDB = strings.TrimSpace(command.PostsDB)
	command.Environment = strings.TrimSpace(command.Environment)
	command.SourceOwner = strings.TrimSpace(command.SourceOwner)
	command.ReportPath = strings.TrimSpace(command.ReportPath)
	command.ReleaseID = strings.TrimSpace(command.ReleaseID)
	command.ManifestDigest = strings.TrimSpace(command.ManifestDigest)
	expectedReleaseID = strings.TrimSpace(expectedReleaseID)
	expectedManifestDigest = strings.TrimSpace(expectedManifestDigest)

	if command.MongoURI == "" || command.PostsDB == "" || command.Environment == "" ||
		command.SourceOwner == "" || command.ReportPath == "" {
		return ReleaseControlCommand{}, fmt.Errorf("--mongo-uri, --posts-db, --env, --source-owner, and --report must be non-empty")
	}
	hasExpectedEmptyFlag := provided["expected-active-empty"]
	expectedTupleFlags := []string{
		"expected-active-release-id", "expected-active-manifest-digest", "expected-active-revision",
	}
	hasAnyExpectedTupleFlag := false
	hasCompleteExpectedTupleFlags := true
	for _, name := range expectedTupleFlags {
		hasAnyExpectedTupleFlag = hasAnyExpectedTupleFlag || provided[name]
		hasCompleteExpectedTupleFlags = hasCompleteExpectedTupleFlags && provided[name]
	}
	switch command.Operation {
	case "query-candidate":
		if command.ReleaseID == "" || !sha256Pattern.MatchString(command.ManifestDigest) {
			return ReleaseControlCommand{}, fmt.Errorf("query-candidate requires --release-id and canonical --manifest-digest")
		}
		if hasExpectedEmptyFlag || hasAnyExpectedTupleFlag {
			return ReleaseControlCommand{}, fmt.Errorf("expected-current flags are valid only for activate")
		}
	case "query-active":
		if provided["release-id"] || provided["manifest-digest"] {
			return ReleaseControlCommand{}, fmt.Errorf("query-active does not accept target release flags")
		}
		if hasExpectedEmptyFlag || hasAnyExpectedTupleFlag {
			return ReleaseControlCommand{}, fmt.Errorf("expected-current flags are valid only for activate")
		}
	case "activate":
		if command.ReleaseID == "" || !sha256Pattern.MatchString(command.ManifestDigest) {
			return ReleaseControlCommand{}, fmt.Errorf("activate requires --release-id and canonical --manifest-digest")
		}
		if hasExpectedEmptyFlag == hasAnyExpectedTupleFlag ||
			(hasAnyExpectedTupleFlag && !hasCompleteExpectedTupleFlags) {
			return ReleaseControlCommand{}, fmt.Errorf("activate requires exactly one complete expected-current form")
		}
		if hasExpectedEmptyFlag && !expectedEmpty {
			return ReleaseControlCommand{}, fmt.Errorf("--expected-active-empty must be true when provided")
		}
		command.Expected = ExpectedActiveRelease{
			Empty: expectedEmpty, SourceOwner: command.SourceOwner,
			ReleaseID: expectedReleaseID, ManifestDigest: expectedManifestDigest,
			Revision: expectedRevision,
		}
		if err := validateExpectedActiveRelease(command.Expected); err != nil {
			return ReleaseControlCommand{}, err
		}
		if !expectedEmpty && !sha256Pattern.MatchString(expectedManifestDigest) {
			return ReleaseControlCommand{}, fmt.Errorf("expected active manifest digest must be canonical sha256")
		}
	default:
		return ReleaseControlCommand{}, fmt.Errorf("--operation must be query-candidate, query-active, or activate")
	}
	return command, nil
}

type ContentReleaseCandidateReceipt struct {
	Schema            string                                  `json:"schema"`
	Status            string                                  `json:"status"`
	Environment       string                                  `json:"environment"`
	SourceOwner       string                                  `json:"sourceOwner"`
	ReleaseID         string                                  `json:"releaseId"`
	ManifestDigest    string                                  `json:"manifestDigest"`
	GeneratedAt       time.Time                               `json:"generatedAt"`
	ReleaseClass      string                                  `json:"releaseClass,omitempty"`
	ReleaseKind       string                                  `json:"releaseKind,omitempty"`
	Mode              string                                  `json:"mode,omitempty"`
	DeletePolicy      string                                  `json:"deletePolicy,omitempty"`
	ProjectionVersion int64                                   `json:"projectionVersion,omitempty"`
	VerifiedAt        *time.Time                              `json:"verifiedAt,omitempty"`
	ClosureDigests    *ImportedReleaseCandidateClosureDigests `json:"closureDigests,omitempty"`
	Counts            *ImportedReleaseCandidateCounts         `json:"counts,omitempty"`
}

type ContentReleaseActiveReceipt struct {
	Schema            string     `json:"schema"`
	Status            string     `json:"status"`
	Environment       string     `json:"environment"`
	SourceOwner       string     `json:"sourceOwner"`
	GeneratedAt       time.Time  `json:"generatedAt"`
	ReleaseID         string     `json:"releaseId,omitempty"`
	ManifestDigest    string     `json:"manifestDigest,omitempty"`
	ReleaseClass      string     `json:"releaseClass,omitempty"`
	ProjectionVersion int64      `json:"projectionVersion,omitempty"`
	Revision          int64      `json:"revision,omitempty"`
	ActivatedAt       *time.Time `json:"activatedAt,omitempty"`
}

type ContentReleaseExpectedActive struct {
	Found          bool   `json:"found"`
	SourceOwner    string `json:"sourceOwner"`
	Revision       int64  `json:"revision"`
	ReleaseID      string `json:"releaseId,omitempty"`
	ManifestDigest string `json:"manifestDigest,omitempty"`
}

type ContentReleaseActivationTarget struct {
	ReleaseID      string `json:"releaseId"`
	ManifestDigest string `json:"manifestDigest"`
}

type ContentReleaseActivationActive struct {
	ReleaseID         string    `json:"releaseId"`
	ManifestDigest    string    `json:"manifestDigest"`
	ReleaseClass      string    `json:"releaseClass"`
	ProjectionVersion int64     `json:"projectionVersion"`
	Revision          int64     `json:"revision"`
	ActivatedAt       time.Time `json:"activatedAt"`
}

type ContentReleaseActivationCounts struct {
	PostsMaterialized       int   `json:"postsMaterialized"`
	PostsRemoved            int64 `json:"postsRemoved"`
	MediaAssetsMaterialized int   `json:"mediaAssetsMaterialized"`
	MediaAssetsRemoved      int64 `json:"mediaAssetsRemoved"`
	OutboxEventsReady       int   `json:"outboxEventsReady"`
	OutboxEventsAppended    int   `json:"outboxEventsAppended"`
}

type ContentReleaseActivationReceipt struct {
	Schema         string                         `json:"schema"`
	Status         string                         `json:"status"`
	Environment    string                         `json:"environment"`
	SourceOwner    string                         `json:"sourceOwner"`
	Target         ContentReleaseActivationTarget `json:"target"`
	ExpectedActive ContentReleaseExpectedActive   `json:"expectedActive"`
	PreviousActive ContentReleaseExpectedActive   `json:"previousActive"`
	Active         ContentReleaseActivationActive `json:"active"`
	Counts         ContentReleaseActivationCounts `json:"counts"`
	GeneratedAt    time.Time                      `json:"generatedAt"`
}

func BuildContentReleaseCandidateReceipt(
	candidate VerifiedImportedPostReleaseCandidate,
	generatedAt time.Time,
) (ContentReleaseCandidateReceipt, error) {
	generatedAt, err := canonicalReleaseControlTime(generatedAt, "candidate receipt generatedAt")
	if err != nil {
		return ContentReleaseCandidateReceipt{}, err
	}
	if candidate.Environment == "" || candidate.SourceOwner == "" || candidate.ReleaseID == "" ||
		!sha256Pattern.MatchString(candidate.ManifestDigest) {
		return ContentReleaseCandidateReceipt{}, fmt.Errorf("candidate receipt identity is incomplete")
	}
	receipt := ContentReleaseCandidateReceipt{
		Schema: ContentReleaseCandidateReceiptSchema, Status: "not_found",
		Environment: candidate.Environment, SourceOwner: candidate.SourceOwner,
		ReleaseID: candidate.ReleaseID, ManifestDigest: candidate.ManifestDigest,
		GeneratedAt: generatedAt,
	}
	if !candidate.Found {
		return receipt, nil
	}
	state := importedReleaseCandidateState{
		Kind: releaseCandidateKind, Environment: candidate.Environment,
		SourceOwner: candidate.SourceOwner, ReleaseID: candidate.ReleaseID,
		ManifestDigest: candidate.ManifestDigest, ReleaseClass: candidate.ReleaseClass,
		ReleaseKind: candidate.ReleaseKind, Mode: candidate.Mode,
		DeletePolicy: candidate.DeletePolicy, Status: "verified",
		ProjectionVersion: candidate.ProjectionVersion, VerifiedAt: candidate.VerifiedAt,
		PostClosureDigest:  candidate.ClosureDigests.Posts,
		FactClosureDigest:  candidate.ClosureDigests.Facts,
		MediaClosureDigest: candidate.ClosureDigests.Media,
		Counts: importedReleaseCandidateCounts{
			PostsExpected:   candidate.Counts.PostsExpected,
			PostsProjected:  candidate.Counts.PostsProjected,
			OutboxExpected:  candidate.Counts.OutboxExpected,
			OutboxProjected: candidate.Counts.OutboxProjected,
			MediaExpected:   candidate.Counts.MediaExpected,
			MediaProjected:  candidate.Counts.MediaProjected,
		},
	}
	if err := validateVerifiedCandidateState(
		state, candidate.Environment, candidate.SourceOwner,
		candidate.ReleaseID, candidate.ManifestDigest,
	); err != nil {
		return ContentReleaseCandidateReceipt{}, err
	}
	verifiedAt := candidate.VerifiedAt.UTC()
	digests := candidate.ClosureDigests
	counts := candidate.Counts
	receipt.Status = "found"
	receipt.ReleaseClass = candidate.ReleaseClass
	receipt.ReleaseKind = candidate.ReleaseKind
	receipt.Mode = candidate.Mode
	receipt.DeletePolicy = candidate.DeletePolicy
	receipt.ProjectionVersion = candidate.ProjectionVersion
	receipt.VerifiedAt = &verifiedAt
	receipt.ClosureDigests = &digests
	receipt.Counts = &counts
	return receipt, nil
}

func BuildContentReleaseActiveReceipt(
	binding ActiveReleaseBinding,
	generatedAt time.Time,
) (ContentReleaseActiveReceipt, error) {
	generatedAt, err := canonicalReleaseControlTime(generatedAt, "active receipt generatedAt")
	if err != nil {
		return ContentReleaseActiveReceipt{}, err
	}
	if binding.Environment == "" || binding.SourceOwner == "" {
		return ContentReleaseActiveReceipt{}, fmt.Errorf("active receipt query binding is incomplete")
	}
	receipt := ContentReleaseActiveReceipt{
		Schema: ContentReleaseActiveReceiptSchema, Status: "not_found",
		Environment: binding.Environment, SourceOwner: binding.SourceOwner,
		GeneratedAt: generatedAt,
	}
	if !binding.Found {
		return receipt, nil
	}
	pointer := importedReleasePointerDocument{
		Kind: releaseActivePointerKind, Status: "active",
		Environment: binding.Environment, SourceOwner: binding.SourceOwner,
		ActiveReleaseID: binding.ReleaseID, ManifestDigest: binding.ManifestDigest,
		ReleaseClass: binding.ReleaseClass, ProjectionVersion: binding.ProjectionVersion,
		Revision: binding.Revision, ActivatedAt: binding.ActivatedAt,
	}
	if err := validateStoredActivePointer(pointer, binding.Environment, binding.SourceOwner); err != nil {
		return ContentReleaseActiveReceipt{}, err
	}
	activatedAt := binding.ActivatedAt.UTC()
	receipt.Status = "found"
	receipt.ReleaseID = binding.ReleaseID
	receipt.ManifestDigest = binding.ManifestDigest
	receipt.ReleaseClass = binding.ReleaseClass
	receipt.ProjectionVersion = binding.ProjectionVersion
	receipt.Revision = binding.Revision
	receipt.ActivatedAt = &activatedAt
	return receipt, nil
}

func BuildContentReleaseActivationReceipt(
	environment string,
	sourceOwner string,
	target ImportedReleaseBinding,
	expected ExpectedActiveRelease,
	result ReleaseActivationResult,
	readback ActiveReleaseBinding,
	generatedAt time.Time,
) (ContentReleaseActivationReceipt, error) {
	environment = strings.TrimSpace(environment)
	sourceOwner = strings.TrimSpace(sourceOwner)
	target.SourceOwner = strings.TrimSpace(target.SourceOwner)
	target.ReleaseID = strings.TrimSpace(target.ReleaseID)
	target.ManifestDigest = strings.TrimSpace(target.ManifestDigest)
	if environment == "" || sourceOwner == "" || target.SourceOwner != sourceOwner ||
		target.ReleaseID == "" || !sha256Pattern.MatchString(target.ManifestDigest) {
		return ContentReleaseActivationReceipt{}, fmt.Errorf("activation receipt target binding is incomplete")
	}
	if err := validateExpectedActiveRelease(expected); err != nil {
		return ContentReleaseActivationReceipt{}, err
	}
	if expected.SourceOwner != sourceOwner {
		return ContentReleaseActivationReceipt{}, fmt.Errorf("activation receipt expected owner differs from target owner")
	}
	generatedAt, err := canonicalReleaseControlTime(generatedAt, "activation receipt generatedAt")
	if err != nil {
		return ContentReleaseActivationReceipt{}, err
	}
	pointer := importedReleasePointerDocument{
		Kind: releaseActivePointerKind, Status: "active",
		Environment: readback.Environment, SourceOwner: readback.SourceOwner,
		ActiveReleaseID: readback.ReleaseID, ManifestDigest: readback.ManifestDigest,
		ReleaseClass: readback.ReleaseClass, ProjectionVersion: readback.ProjectionVersion,
		Revision: readback.Revision, ActivatedAt: readback.ActivatedAt,
	}
	if err := validateStoredActivePointer(pointer, environment, sourceOwner); err != nil {
		return ContentReleaseActivationReceipt{}, err
	}
	if readback.ReleaseID != target.ReleaseID || readback.ManifestDigest != target.ManifestDigest ||
		!sameActiveReleaseBinding(result.Active, readback) {
		return ContentReleaseActivationReceipt{}, fmt.Errorf("GATE_BLOCK: activation result/readback differs from exact target")
	}
	if result.PostsMaterialized < 0 || result.PostsRemoved < 0 ||
		result.MediaAssetsMaterialized < 0 || result.MediaAssetsRemoved < 0 ||
		result.OutboxEventsReady < 0 || result.OutboxEventsAppended < 0 {
		return ContentReleaseActivationReceipt{}, fmt.Errorf("activation receipt counts are invalid")
	}
	expectedActive := contentReleaseExpectedActive(expected)
	status := "activated"
	if result.Replayed {
		status = "replayed"
	}
	return ContentReleaseActivationReceipt{
		Schema: ContentReleaseActivationReceiptSchema, Status: status,
		Environment: environment, SourceOwner: sourceOwner,
		Target: ContentReleaseActivationTarget{
			ReleaseID: target.ReleaseID, ManifestDigest: target.ManifestDigest,
		},
		ExpectedActive: expectedActive,
		// Successful CAS proves that the predecessor was the expected tuple. A
		// replay proves the same predecessor through its exact activation receipt.
		PreviousActive: expectedActive,
		Active: ContentReleaseActivationActive{
			ReleaseID: readback.ReleaseID, ManifestDigest: readback.ManifestDigest,
			ReleaseClass: readback.ReleaseClass, ProjectionVersion: readback.ProjectionVersion,
			Revision: readback.Revision, ActivatedAt: readback.ActivatedAt.UTC(),
		},
		Counts: ContentReleaseActivationCounts{
			PostsMaterialized:       result.PostsMaterialized,
			PostsRemoved:            result.PostsRemoved,
			MediaAssetsMaterialized: result.MediaAssetsMaterialized,
			MediaAssetsRemoved:      result.MediaAssetsRemoved,
			OutboxEventsReady:       result.OutboxEventsReady,
			OutboxEventsAppended:    result.OutboxEventsAppended,
		},
		GeneratedAt: generatedAt,
	}, nil
}

// ContentReleaseExpectedActiveFromExpectation maps the exact CAS predecessor
// without consulting or exposing mutable storage state.
func ContentReleaseExpectedActiveFromExpectation(expected ExpectedActiveRelease) (ContentReleaseExpectedActive, error) {
	expected.SourceOwner = strings.TrimSpace(expected.SourceOwner)
	expected.ReleaseID = strings.TrimSpace(expected.ReleaseID)
	expected.ManifestDigest = strings.TrimSpace(expected.ManifestDigest)
	if err := validateExpectedActiveRelease(expected); err != nil {
		return ContentReleaseExpectedActive{}, err
	}
	if !expected.Empty && !sha256Pattern.MatchString(expected.ManifestDigest) {
		return ContentReleaseExpectedActive{}, fmt.Errorf("expected active manifest digest must be canonical sha256")
	}
	return contentReleaseExpectedActive(expected), nil
}

func contentReleaseExpectedActive(expected ExpectedActiveRelease) ContentReleaseExpectedActive {
	if expected.Empty {
		return ContentReleaseExpectedActive{
			Found: false, SourceOwner: expected.SourceOwner, Revision: 0,
		}
	}
	return ContentReleaseExpectedActive{
		Found: true, SourceOwner: expected.SourceOwner, Revision: expected.Revision,
		ReleaseID: expected.ReleaseID, ManifestDigest: expected.ManifestDigest,
	}
}

func sameActiveReleaseBinding(left ActiveReleaseBinding, right ActiveReleaseBinding) bool {
	return left.Found == right.Found && left.Environment == right.Environment &&
		left.SourceOwner == right.SourceOwner && left.ReleaseID == right.ReleaseID &&
		left.ManifestDigest == right.ManifestDigest && left.ReleaseClass == right.ReleaseClass &&
		left.ProjectionVersion == right.ProjectionVersion && left.Revision == right.Revision &&
		left.ActivatedAt.Equal(right.ActivatedAt)
}

func canonicalReleaseControlTime(value time.Time, label string) (time.Time, error) {
	if value.IsZero() {
		return time.Time{}, fmt.Errorf("%s is required", label)
	}
	return value.UTC(), nil
}

// WriteReleaseControlReport writes one deterministic JSON receipt. O_EXCL
// rejects every existing path, including regular files and symlinks.
func WriteReleaseControlReport(path string, report any) error {
	resolved, err := validateReleaseControlReportDestination(path)
	if err != nil {
		return err
	}
	encoded, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return fmt.Errorf("encode release-control report: %w", err)
	}
	encoded = append(encoded, '\n')
	file, err := os.OpenFile(resolved, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return fmt.Errorf("create release-control report: %w", err)
	}
	if _, err := file.Write(encoded); err != nil {
		_ = file.Close()
		_ = os.Remove(resolved)
		return fmt.Errorf("write release-control report: %w", err)
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		_ = os.Remove(resolved)
		return fmt.Errorf("sync release-control report: %w", err)
	}
	if err := file.Close(); err != nil {
		_ = os.Remove(resolved)
		return fmt.Errorf("close release-control report: %w", err)
	}
	return nil
}

func validateReleaseControlReportDestination(path string) (string, error) {
	resolved := filepath.Clean(strings.TrimSpace(path))
	if resolved == "." || resolved == string(filepath.Separator) {
		return "", fmt.Errorf("release-control report path is invalid")
	}
	if _, err := os.Lstat(resolved); err == nil {
		return "", fmt.Errorf("release-control report already exists")
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", fmt.Errorf("inspect release-control report destination: %w", err)
	}
	parent := filepath.Dir(resolved)
	parentInfo, err := os.Lstat(parent)
	if err != nil {
		return "", fmt.Errorf("inspect release-control report directory: %w", err)
	}
	if parentInfo.Mode()&os.ModeSymlink != 0 || !parentInfo.IsDir() {
		return "", fmt.Errorf("release-control report directory must be a non-symlink directory")
	}
	return resolved, nil
}

// RunReleaseControl is the Content-owned CLI/query port used by Data. It does
// not create a report until the selected operation and activation readback pass.
func RunReleaseControl(ctx context.Context, args []string) error {
	if ctx == nil {
		return fmt.Errorf("release-control context is required")
	}
	command, err := ParseReleaseControlCommand(args)
	if err != nil {
		return err
	}
	if _, err := validateReleaseControlReportDestination(command.ReportPath); err != nil {
		return err
	}
	client, err := mongo.Connect(options.Client().ApplyURI(command.MongoURI))
	if err != nil {
		return fmt.Errorf("connect release-control MongoDB: %w", err)
	}
	defer client.Disconnect(context.Background())
	database := client.Database(command.PostsDB)
	generatedAt := time.Now().UTC().Truncate(time.Millisecond)

	switch command.Operation {
	case "query-candidate":
		candidate, err := ReadVerifiedImportedPostReleaseCandidate(
			ctx, database, command.Environment, command.SourceOwner,
			command.ReleaseID, command.ManifestDigest,
		)
		if err != nil {
			return fmt.Errorf("query verified Content release candidate: %w", err)
		}
		receipt, err := BuildContentReleaseCandidateReceipt(candidate, generatedAt)
		if err != nil {
			return err
		}
		return WriteReleaseControlReport(command.ReportPath, receipt)
	case "query-active":
		active, err := ReadActiveImportedPostRelease(
			ctx, database, command.Environment, command.SourceOwner,
		)
		if err != nil {
			return fmt.Errorf("query active Content release: %w", err)
		}
		receipt, err := BuildContentReleaseActiveReceipt(active, generatedAt)
		if err != nil {
			return err
		}
		return WriteReleaseControlReport(command.ReportPath, receipt)
	case "activate":
		target := ImportedReleaseBinding{
			SourceOwner: command.SourceOwner, ReleaseID: command.ReleaseID,
			ManifestDigest: command.ManifestDigest,
		}
		result, err := ActivateImportedPostRelease(
			ctx, database, command.Environment, target, command.Expected, generatedAt,
		)
		if err != nil {
			return fmt.Errorf("activate Content release: %w", err)
		}
		readback, err := ReadActiveImportedPostRelease(
			ctx, database, command.Environment, command.SourceOwner,
		)
		if err != nil {
			return fmt.Errorf("read back activated Content release: %w", err)
		}
		receipt, err := BuildContentReleaseActivationReceipt(
			command.Environment, command.SourceOwner, target, command.Expected,
			result, readback, generatedAt,
		)
		if err != nil {
			return err
		}
		return WriteReleaseControlReport(command.ReportPath, receipt)
	default:
		return fmt.Errorf("unsupported release-control operation %q", command.Operation)
	}
}
