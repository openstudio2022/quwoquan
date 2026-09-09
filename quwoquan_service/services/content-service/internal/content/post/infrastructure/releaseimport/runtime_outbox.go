package releaseimport

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"regexp"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const (
	ReleaseActivationCASConflictCode = "CONTENT.RELEASE.ACTIVE_CAS_CONFLICT"
	releaseCandidateKind             = "candidate"
	releaseActivePointerKind         = "active_pointer"
)

// ImportedReleaseBinding is one exact immutable release tuple. Empty denotes
// the explicit no-current-release expectation for first activation.
type ImportedReleaseBinding struct {
	SourceOwner    string `bson:"sourceOwner" json:"sourceOwner"`
	ReleaseID      string `bson:"releaseId" json:"releaseId"`
	ManifestDigest string `bson:"manifestDigest" json:"manifestDigest"`
}

func (binding ImportedReleaseBinding) Empty() bool {
	return strings.TrimSpace(binding.ReleaseID) == "" &&
		strings.TrimSpace(binding.ManifestDigest) == ""
}

func ReleaseBindingFromImportOptions(opts ImportOptions) ImportedReleaseBinding {
	return ImportedReleaseBinding{
		SourceOwner:    strings.TrimSpace(opts.SourceOwner),
		ReleaseID:      strings.TrimSpace(opts.ReleaseID),
		ManifestDigest: strings.TrimSpace(opts.ManifestDigest),
	}
}

// ExpectedActiveRelease makes first activation and non-empty CAS expectations
// unambiguous. Revision starts at 1 after the first successful activation.
type ExpectedActiveRelease struct {
	Empty          bool
	SourceOwner    string
	ReleaseID      string
	ManifestDigest string
	Revision       int64
}

// ActiveReleaseBinding is the query result consumed by the future environment
// adapter. Found=false is the only representation of an empty pointer.
type ActiveReleaseBinding struct {
	Environment       string
	SourceOwner       string
	ReleaseID         string
	ManifestDigest    string
	ProjectionVersion int64
	Revision          int64
	ActivatedAt       time.Time
	Found             bool
}

// ReleaseActivationResult reports either one committed pointer advance or an
// exact idempotent replay. It never treats a stale expectation as success.
type ReleaseActivationResult struct {
	Active                  ActiveReleaseBinding
	Previous                ImportedReleaseBinding
	PostsMaterialized       int
	PostsRemoved            int64
	MediaAssetsMaterialized int
	MediaAssetsRemoved      int64
	TransitionEvents        []ImportedReleaseTransitionEvent
	OutboxEventsReady       int
	OutboxEventsAppended    int
	Replayed                bool
}

// ReleaseActivationCASConflictError is the stable typed conflict returned when
// expected-current no longer matches the Content-owned active pointer.
type ReleaseActivationCASConflictError struct {
	Expected ExpectedActiveRelease
	Actual   ActiveReleaseBinding
}

func (err *ReleaseActivationCASConflictError) Error() string {
	return fmt.Sprintf(
		"%s: expected owner=%q release=%q digest=%q revision=%d empty=%t; actual owner=%q release=%q digest=%q revision=%d found=%t",
		ReleaseActivationCASConflictCode,
		err.Expected.SourceOwner,
		err.Expected.ReleaseID,
		err.Expected.ManifestDigest,
		err.Expected.Revision,
		err.Expected.Empty,
		err.Actual.SourceOwner,
		err.Actual.ReleaseID,
		err.Actual.ManifestDigest,
		err.Actual.Revision,
		err.Actual.Found,
	)
}

func IsReleaseActivationCASConflict(err error) bool {
	var conflict *ReleaseActivationCASConflictError
	return errors.As(err, &conflict)
}

func ValidateImportOptions(opts ImportOptions) error {
	opts = NormalizeImportOptions(opts)
	if opts.Mode != "upsert" && opts.Mode != "sync" {
		return fmt.Errorf("content release mode must be upsert or sync")
	}
	if opts.DeletePolicy != "none" && opts.DeletePolicy != "tombstone" {
		return fmt.Errorf("content release deletePolicy must be none or tombstone")
	}
	if opts.Mode != "sync" && opts.DeletePolicy != "none" {
		return fmt.Errorf("content release tombstone cleanup requires mode=sync")
	}
	if opts.ReleaseKind != "content" && opts.ReleaseKind != "empty_baseline" {
		return fmt.Errorf("content release releaseKind must be content or empty_baseline")
	}
	return nil
}

// ImportedReleaseApplyResult is the Content-owned result of materializing one
// immutable Data release candidate. Posts, lifecycle facts, media projections
// and verified state are committed together; active selection is a later CAS.
type ImportedReleaseApplyResult struct {
	PostsExpected           int
	PostsUpserted           int
	PostsRemoved            int64
	PostDeletionEventsReady int
	OutboxEventsReady       int
	OutboxEventsAppended    int
	OutboxEventsRepaired    int
	OutboxRepairAudits      []ImportedPostOutboxRepairAudit
	MediaAssetsExpected     int
	MediaAssetsProjected    int
	ProjectionVersion       int64
	Replayed                bool
	RepairReplay            bool
	PreviousReleaseID       string
	PreviousManifestDigest  string
}

type ImportedReleaseTransitionEvent struct {
	EventID            string
	EventType          string
	SourceOwner        string
	ReleaseID          string
	ManifestDigest     string
	ActivationRevision int64
	AggregateID        string
	AggregateVersion   int64
}

type importedReleaseCandidateCounts struct {
	PostsExpected   int `bson:"postsExpected"`
	PostsProjected  int `bson:"postsProjected"`
	OutboxExpected  int `bson:"outboxExpected"`
	OutboxProjected int `bson:"outboxProjected"`
	MediaExpected   int `bson:"mediaExpected"`
	MediaProjected  int `bson:"mediaProjected"`
}

type importedReleaseCandidateState struct {
	Kind               string                         `bson:"kind"`
	Environment        string                         `bson:"environment"`
	SourceOwner        string                         `bson:"sourceOwner"`
	ReleaseID          string                         `bson:"releaseId"`
	ManifestDigest     string                         `bson:"manifestDigest"`
	ReleaseKind        string                         `bson:"releaseKind"`
	Mode               string                         `bson:"mode"`
	DeletePolicy       string                         `bson:"deletePolicy"`
	PostClosureDigest  string                         `bson:"postClosureDigest"`
	FactClosureDigest  string                         `bson:"factClosureDigest"`
	MediaClosureDigest string                         `bson:"mediaClosureDigest"`
	Status             string                         `bson:"status"`
	ProjectionVersion  int64                          `bson:"projectionVersion"`
	VerifiedAt         time.Time                      `bson:"verifiedAt"`
	Counts             importedReleaseCandidateCounts `bson:"counts"`
	Extra              bson.M                         `bson:",inline"`
}

type importedReleasePointerDocument struct {
	Kind              string    `bson:"kind"`
	Status            string    `bson:"status"`
	Environment       string    `bson:"environment"`
	SourceOwner       string    `bson:"sourceOwner"`
	ActiveReleaseID   string    `bson:"activeReleaseId"`
	ManifestDigest    string    `bson:"manifestDigest"`
	ProjectionVersion int64     `bson:"projectionVersion"`
	Revision          int64     `bson:"revision"`
	ActivatedAt       time.Time `bson:"activatedAt"`
	Extra             bson.M    `bson:",inline"`
}

type importedOutboxDocument struct {
	ID                 string          `bson:"_id"`
	SourceOwner        string          `bson:"sourceOwner,omitempty"`
	ReleaseID          string          `bson:"releaseId,omitempty"`
	ManifestDigest     string          `bson:"manifestDigest,omitempty"`
	OutboxSequence     int64           `bson:"outboxSequence"`
	EventType          string          `bson:"eventType"`
	AggregateType      string          `bson:"aggregateType"`
	AggregateID        string          `bson:"aggregateId"`
	AggregateVersion   int64           `bson:"aggregateVersion"`
	PayloadJSON        json.RawMessage `bson:"payloadJson"`
	ActivationRevision int64           `bson:"activationRevision,omitempty"`
	OccurredAt         time.Time       `bson:"occurredAt"`
}

// ImportedPostOutboxEventSnapshot is the immutable CAS identity used to
// repair one prior Data-release PostDeleted payload without replacing its
// durable outbox envelope or sequence.
type ImportedPostOutboxEventSnapshot struct {
	EventID            string
	OutboxSequence     int64
	EventType          string
	AggregateType      string
	AggregateID        string
	AggregateVersion   int64
	PayloadJSON        json.RawMessage
	ActivationRevision int64
	OccurredAt         time.Time
}

// ImportedPostOutboxRepairAudit is the bounded, payload-free repair receipt.
type ImportedPostOutboxRepairAudit struct {
	EventID      string
	BeforeSHA256 string
	AfterSHA256  string
}

// ImportedPostOutboxPayloadCAS updates only payloadJson when every immutable
// envelope field and the old payload still match the frozen replay snapshot.
type ImportedPostOutboxPayloadCAS interface {
	CompareAndSwapImportedPostOutboxPayload(
		ctx context.Context,
		existing ImportedPostOutboxEventSnapshot,
		replacement json.RawMessage,
	) (bool, error)
}

type importedPostOutboxApplyResult struct {
	Appended int
	Repairs  []ImportedPostOutboxRepairAudit
}

// ApplyImportedPostRelease is a compatibility name for in-process callers.
// It hard-selects stage-only and never activates; the CLI has no implicit
// default and requires an explicit --activation-mode.
func ApplyImportedPostRelease(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	posts []PostDoc,
	requestedAt time.Time,
	opts ImportOptions,
) (ImportedReleaseApplyResult, error) {
	if opts.RequireReplay {
		opts.ActivationMode = "repair-active"
		return StageImportedPostRelease(ctx, database, environment, posts, nil, requestedAt, opts)
	}
	opts.ActivationMode = "stage-only"
	return StageImportedPostRelease(ctx, database, environment, posts, nil, requestedAt, opts)
}

// StageImportedPostRelease writes one isolated candidate closure. Missing-item
// cleanup is deliberately deferred: staging must not mutate the active release.
func StageImportedPostRelease(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	posts []PostDoc,
	mediaAssets map[string]ReleaseMediaAsset,
	requestedAt time.Time,
	opts ImportOptions,
) (ImportedReleaseApplyResult, error) {
	if database == nil {
		return ImportedReleaseApplyResult{}, fmt.Errorf("content release import database is required")
	}
	environment = strings.TrimSpace(environment)
	if environment == "" {
		return ImportedReleaseApplyResult{}, fmt.Errorf("content release import environment is required")
	}
	opts = NormalizeImportOptions(opts)
	if err := ValidateImportOptions(opts); err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	if opts.ActivationMode == "" {
		opts.ActivationMode = "stage-only"
	}
	if opts.ActivationMode != "stage-only" && opts.ActivationMode != "repair-active" {
		return ImportedReleaseApplyResult{}, fmt.Errorf("content release stage requires activationMode=stage-only")
	}
	if strings.TrimSpace(opts.ManifestDigest) == "" {
		return ImportedReleaseApplyResult{}, fmt.Errorf("content release import manifestDigest is required")
	}
	if opts.RequireReplay {
		if opts.ActivationMode != "repair-active" {
			return ImportedReleaseApplyResult{}, fmt.Errorf("active repair requires the explicit repair-active rail")
		}
		return stageImportedPostReleaseRepair(
			ctx, database, environment, posts, requestedAt, opts,
		)
	}
	requestedAt = requestedAt.UTC().Truncate(time.Millisecond)
	if requestedAt.IsZero() {
		requestedAt = time.Now().UTC().Truncate(time.Millisecond)
	}

	candidatePosts := database.Collection("data_release_candidate_posts")
	candidateOutbox := database.Collection("data_release_candidate_outbox")
	candidateMedia := database.Collection("data_release_candidate_media_assets")
	releaseSequences := database.Collection("data_release_sequences")
	stateColl := database.Collection("data_release_state")
	receiptColl := database.Collection("data_release_stage_receipts")
	if err := ensureImportedReleaseIndexes(
		ctx, candidatePosts, candidateOutbox, candidateMedia, stateColl, receiptColl,
	); err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	if err := rejectPriorReleaseStateShape(ctx, stateColl, environment, opts.SourceOwner); err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	attemptID := releaseAttemptID(environment, opts, requestedAt)
	stageStarted := time.Now()

	session, err := database.Client().StartSession()
	if err != nil {
		return ImportedReleaseApplyResult{}, fmt.Errorf("start content release import session: %w", err)
	}
	defer session.EndSession(ctx)

	var result ImportedReleaseApplyResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		existing, replayed, err := readVerifiedCandidateState(
			txCtx, stateColl, environment, opts,
		)
		if err != nil {
			return nil, err
		}
		if replayed {
			opts.ProjectionVersion = existing.ProjectionVersion
			candidateResult, err := validateImmutableCandidateClosure(
				txCtx, candidatePosts, candidateOutbox, candidateMedia,
				existing, posts, mediaAssets, requestedAt, opts,
			)
			if err != nil {
				return nil, err
			}
			postDigest, err := collectionClosureDigest(txCtx, candidatePosts, releaseCandidateFilter(existing))
			if err != nil || postDigest != existing.PostClosureDigest {
				return nil, fmt.Errorf("GATE_BLOCK: candidate Post closure digest drift")
			}
			factDigest, err := collectionClosureDigest(txCtx, candidateOutbox, releaseCandidateFilter(existing))
			if err != nil || factDigest != existing.FactClosureDigest {
				return nil, fmt.Errorf("GATE_BLOCK: candidate fact closure digest drift")
			}
			mediaDigest, err := collectionClosureDigest(txCtx, candidateMedia, releaseCandidateFilter(existing))
			if err != nil || mediaDigest != existing.MediaClosureDigest {
				return nil, fmt.Errorf("GATE_BLOCK: candidate media closure digest drift")
			}
			candidateResult.Replayed = true
			result = candidateResult
			return nil, nil
		}
		resolved, err := allocateReleaseProjectionVersion(txCtx, releaseSequences)
		if err != nil {
			return nil, err
		}
		opts.ProjectionVersion = resolved
		insertedPosts, err := insertCandidatePosts(
			txCtx, candidatePosts, environment, posts, requestedAt, opts,
		)
		if err != nil {
			return nil, fmt.Errorf("insert imported candidate Posts: %w", err)
		}
		insertedEvents, err := insertCandidatePostFacts(
			txCtx, candidateOutbox, environment, posts, requestedAt, opts,
		)
		if err != nil {
			return nil, err
		}
		projectedMedia, err := InsertReleaseMediaAssetProjections(
			txCtx, candidateMedia, mediaAssets, environment, opts.SourceOwner,
			opts.ReleaseID, opts.ManifestDigest, requestedAt,
		)
		if err != nil {
			return nil, err
		}
		candidateResult := ImportedReleaseApplyResult{
			PostsExpected: len(posts), PostsUpserted: insertedPosts,
			OutboxEventsReady: len(posts), OutboxEventsAppended: insertedEvents,
			MediaAssetsExpected: len(mediaAssets), MediaAssetsProjected: projectedMedia,
			ProjectionVersion: resolved,
		}
		if err := ValidateImportedReleaseApplyResult(candidateResult, len(posts)); err != nil {
			return nil, err
		}
		if err := insertVerifiedCandidateState(
			txCtx, stateColl, candidatePosts, candidateOutbox, candidateMedia,
			environment, opts, requestedAt, candidateResult,
		); err != nil {
			return nil, err
		}
		for _, stage := range []struct{ name, checkpoint string }{
			{name: "prepared", checkpoint: "canonical-input-validated"},
			{name: "imported", checkpoint: "candidate-posts-materialized"},
			{name: "projected", checkpoint: "candidate-facts-and-media-projected"},
			{name: "verified", checkpoint: "candidate-owner-local-closure-validated"},
		} {
			if err := appendReleaseStageReceipt(txCtx, receiptColl, releaseStageReceipt{
				Environment: environment, SourceOwner: opts.SourceOwner,
				ReleaseID: opts.ReleaseID, ManifestDigest: opts.ManifestDigest,
				Stage: stage.name, AttemptID: attemptID, Status: "passed",
				RecordedAt: requestedAt, DurationMs: releaseStageDurationMs(stageStarted),
				AttemptedCount: len(posts), SuccessCount: insertedPosts,
				Checkpoint: stage.checkpoint,
			}); err != nil {
				return nil, err
			}
		}
		result = candidateResult
		return nil, nil
	})
	if err != nil {
		if receiptErr := appendReleaseStageReceipt(ctx, receiptColl, releaseStageReceipt{
			Environment: environment, SourceOwner: opts.SourceOwner,
			ReleaseID: opts.ReleaseID, ManifestDigest: opts.ManifestDigest, Stage: "imported",
			AttemptID: attemptID, Status: "failed", RecordedAt: time.Now().UTC(),
			DurationMs: releaseStageDurationMs(stageStarted), AttemptedCount: len(posts),
			Checkpoint: "transaction-aborted", FirstTypedBlocker: releaseImportFailedBlocker,
		}); receiptErr != nil {
			return ImportedReleaseApplyResult{}, fmt.Errorf("%w; persist failure receipt: %v", err, receiptErr)
		}
		return ImportedReleaseApplyResult{}, err
	}
	return result, nil
}

func stageImportedPostReleaseRepair(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	posts []PostDoc,
	requestedAt time.Time,
	opts ImportOptions,
) (ImportedReleaseApplyResult, error) {
	active, err := ReadActiveImportedPostRelease(ctx, database, environment, opts.SourceOwner)
	if err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	if !active.Found || active.ReleaseID != opts.ReleaseID || active.ManifestDigest != opts.ManifestDigest {
		return ImportedReleaseApplyResult{}, fmt.Errorf(
			"GATE_BLOCK: content release repair requires exact active release %q (%s)",
			opts.ReleaseID, opts.ManifestDigest,
		)
	}
	if active.ProjectionVersion <= 0 {
		return ImportedReleaseApplyResult{}, fmt.Errorf("GATE_BLOCK: active release repair projectionVersion is invalid")
	}
	opts.ProjectionVersion = active.ProjectionVersion
	postsColl := database.Collection("posts")
	outboxColl := database.Collection("content_outbox")
	sequenceColl := database.Collection("content_outbox_sequences")
	receiptColl := database.Collection("data_release_stage_receipts")
	stateColl := database.Collection("data_release_state")
	if err := ensurePublishedRepairIndexes(ctx, postsColl, outboxColl, stateColl, receiptColl); err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	attemptID := releaseAttemptID(environment, opts, requestedAt)
	started := time.Now()
	if err := appendReleaseStageReceipt(ctx, receiptColl, releaseStageReceipt{
		Environment: environment, SourceOwner: opts.SourceOwner,
		ReleaseID: opts.ReleaseID, ManifestDigest: opts.ManifestDigest,
		Stage: "prepared", AttemptID: attemptID, Status: "passed", RecordedAt: requestedAt,
		AttemptedCount: len(posts), SuccessCount: len(posts),
		Checkpoint: "active-repair-input-validated",
	}); err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	session, err := database.Client().StartSession()
	if err != nil {
		return ImportedReleaseApplyResult{}, fmt.Errorf("start active release repair session: %w", err)
	}
	defer session.EndSession(ctx)
	var result ImportedReleaseApplyResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		current, err := readActivePointerInTransaction(txCtx, stateColl, environment, opts.SourceOwner)
		if err != nil {
			return nil, err
		}
		if !activeBindingMatches(current, ReleaseBindingFromImportOptions(opts)) ||
			current.Revision != active.Revision {
			return nil, &ReleaseActivationCASConflictError{
				Expected: ExpectedActiveRelease{
					SourceOwner: active.SourceOwner, ReleaseID: active.ReleaseID,
					ManifestDigest: active.ManifestDigest, Revision: active.Revision,
				},
				Actual: current,
			}
		}
		upserted, err := ValidateImportedPostsForReplay(
			txCtx, postsColl, posts, opts.ReplayPostBindings, opts,
		)
		if err != nil {
			return nil, err
		}
		deletedPosts, err := MissingImportedPostSnapshots(
			txCtx, postsColl, posts, opts, true, current.ActivatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("resolve active repair tombstone snapshots: %w", err)
		}
		events, err := BuildImportedPostDeletionLifecycleEvents(deletedPosts, opts, current.ActivatedAt)
		if err != nil {
			return nil, err
		}
		outboxResult, err := appendImportedPostOutbox(
			txCtx, outboxColl, sequenceColl, events, opts, true,
		)
		if err != nil {
			return nil, err
		}
		candidate := ImportedReleaseApplyResult{
			PostsExpected: len(posts), PostsUpserted: upserted,
			PostDeletionEventsReady: len(deletedPosts), OutboxEventsReady: len(events),
			OutboxEventsAppended: outboxResult.Appended,
			OutboxEventsRepaired: len(outboxResult.Repairs), OutboxRepairAudits: outboxResult.Repairs,
			ProjectionVersion: opts.ProjectionVersion, Replayed: true, RepairReplay: true,
		}
		if err := ValidateImportedReleaseApplyResult(candidate, len(posts)); err != nil {
			return nil, err
		}
		if err := ValidateExpectedOutboxRepairCount(opts, candidate); err != nil {
			return nil, err
		}
		result = candidate
		return nil, nil
	})
	if err != nil {
		if receiptErr := appendReleaseStageReceipt(ctx, receiptColl, releaseStageReceipt{
			Environment: environment, SourceOwner: opts.SourceOwner,
			ReleaseID: opts.ReleaseID, ManifestDigest: opts.ManifestDigest,
			Stage: "imported", AttemptID: attemptID, Status: "failed",
			RecordedAt: time.Now().UTC(), DurationMs: releaseStageDurationMs(started),
			AttemptedCount: len(posts), Checkpoint: "repair-transaction-aborted",
			FirstTypedBlocker: releaseImportFailedBlocker,
		}); receiptErr != nil {
			return ImportedReleaseApplyResult{}, fmt.Errorf("%w; persist failure receipt: %v", err, receiptErr)
		}
		return ImportedReleaseApplyResult{}, err
	}
	return result, nil
}

func ensurePublishedRepairIndexes(
	ctx context.Context,
	posts *mongo.Collection,
	outbox *mongo.Collection,
	state *mongo.Collection,
	receipts *mongo.Collection,
) error {
	if _, err := posts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "postRef", Value: 1}},
		Options: options.Index().SetName("idx_post_ref").SetUnique(true).SetSparse(true),
	}); err != nil {
		return fmt.Errorf("ensure imported Post identity index: %w", err)
	}
	if _, err := outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_content_outbox_sequence").SetUnique(true)},
		{Keys: bson.D{{Key: "aggregateType", Value: 1}, {Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("idx_content_outbox_aggregate_version").SetUnique(true)},
	}); err != nil {
		return fmt.Errorf("ensure imported Post outbox indexes: %w", err)
	}
	return ensureReleaseControlIndexes(ctx, state, receipts)
}

// ReadActiveImportedPostRelease returns only the explicit active_pointer shape.
// Any old single-document active shape is rejected instead of dual-read.
func ReadActiveImportedPostRelease(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	sourceOwner string,
) (ActiveReleaseBinding, error) {
	if database == nil {
		return ActiveReleaseBinding{}, fmt.Errorf("content release database is required")
	}
	environment = strings.TrimSpace(environment)
	sourceOwner = strings.TrimSpace(sourceOwner)
	if environment == "" || sourceOwner == "" {
		return ActiveReleaseBinding{}, fmt.Errorf("active release query binding is incomplete")
	}
	state := database.Collection("data_release_state")
	if err := inspectReleaseControlIndexes(ctx, state, database.Collection("data_release_stage_receipts")); err != nil {
		return ActiveReleaseBinding{}, err
	}
	if err := rejectPriorReleaseStateShape(ctx, state, environment, sourceOwner); err != nil {
		return ActiveReleaseBinding{}, err
	}
	var pointer importedReleasePointerDocument
	err := state.FindOne(ctx, bson.M{
		"environment": environment, "sourceOwner": sourceOwner,
		"kind": releaseActivePointerKind, "status": "active",
	}).Decode(&pointer)
	if err == mongo.ErrNoDocuments {
		return ActiveReleaseBinding{Environment: environment, SourceOwner: sourceOwner}, nil
	}
	if err != nil {
		return ActiveReleaseBinding{}, fmt.Errorf("read active Content release pointer: %w", err)
	}
	if err := validateStoredActivePointer(pointer, environment, sourceOwner); err != nil {
		return ActiveReleaseBinding{}, err
	}
	return activeReleaseBindingFromPointer(pointer), nil
}

// ActivateImportedPostRelease materializes one verified candidate into the
// existing live collections and advances the unique pointer in the same Mongo
// transaction. Rollback calls this command with a previous verified candidate.
func ActivateImportedPostRelease(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	target ImportedReleaseBinding,
	expected ExpectedActiveRelease,
	activatedAt time.Time,
) (ReleaseActivationResult, error) {
	if database == nil {
		return ReleaseActivationResult{}, fmt.Errorf("content release database is required")
	}
	environment = strings.TrimSpace(environment)
	target.SourceOwner = strings.TrimSpace(target.SourceOwner)
	target.ReleaseID = strings.TrimSpace(target.ReleaseID)
	target.ManifestDigest = strings.TrimSpace(target.ManifestDigest)
	if environment == "" || target.SourceOwner == "" || target.Empty() ||
		target.ReleaseID == "" || target.ManifestDigest == "" {
		return ReleaseActivationResult{}, fmt.Errorf("release activation target binding is incomplete")
	}
	expected.SourceOwner = strings.TrimSpace(expected.SourceOwner)
	expected.ReleaseID = strings.TrimSpace(expected.ReleaseID)
	expected.ManifestDigest = strings.TrimSpace(expected.ManifestDigest)
	if err := validateExpectedActiveRelease(expected); err != nil {
		return ReleaseActivationResult{}, err
	}
	activatedAt = activatedAt.UTC().Truncate(time.Millisecond)
	if activatedAt.IsZero() {
		activatedAt = time.Now().UTC().Truncate(time.Millisecond)
	}

	state := database.Collection("data_release_state")
	receipts := database.Collection("data_release_stage_receipts")
	candidatePosts := database.Collection("data_release_candidate_posts")
	candidateOutbox := database.Collection("data_release_candidate_outbox")
	candidateMedia := database.Collection("data_release_candidate_media_assets")
	livePosts := database.Collection("posts")
	liveOutbox := database.Collection("content_outbox")
	liveSequences := database.Collection("content_outbox_sequences")
	releaseSequences := database.Collection("data_release_sequences")
	liveMedia := database.Collection("media_assets")
	if err := ensureReleaseActivationIndexes(
		ctx, candidatePosts, candidateOutbox, candidateMedia,
		livePosts, liveOutbox, liveMedia, state, receipts,
	); err != nil {
		return ReleaseActivationResult{}, err
	}
	if err := rejectPriorReleaseStateShape(ctx, state, environment, target.SourceOwner); err != nil {
		return ReleaseActivationResult{}, err
	}

	session, err := database.Client().StartSession()
	if err != nil {
		return ReleaseActivationResult{}, fmt.Errorf("start release activation session: %w", err)
	}
	defer session.EndSession(ctx)
	var result ReleaseActivationResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var candidate importedReleaseCandidateState
		if err := state.FindOne(txCtx, bson.M{
			"kind": releaseCandidateKind, "environment": environment,
			"sourceOwner": target.SourceOwner, "releaseId": target.ReleaseID,
			"manifestDigest": target.ManifestDigest, "status": "verified",
		}).Decode(&candidate); err != nil {
			if err == mongo.ErrNoDocuments {
				return nil, fmt.Errorf("GATE_BLOCK: activation target is not an exact verified candidate")
			}
			return nil, fmt.Errorf("read verified activation target: %w", err)
		}
		if err := validateVerifiedCandidateState(
			candidate, environment, target.SourceOwner,
			target.ReleaseID, target.ManifestDigest,
		); err != nil {
			return nil, err
		}
		if err := validateStoredCandidateClosure(
			txCtx, candidatePosts, candidateOutbox, candidateMedia, candidate,
		); err != nil {
			return nil, err
		}
		current, err := readActivePointerInTransaction(txCtx, state, environment, candidate.SourceOwner)
		if err != nil {
			return nil, err
		}
		if activeBindingMatches(current, target) {
			if sameActivationReplayExpectation(current, expected) {
				if err := validateActivationReplayReceipt(
					txCtx, receipts, environment, target, expected,
				); err != nil {
					return nil, err
				}
				if err := validateLiveReleaseClosure(
					txCtx, livePosts, liveOutbox, liveMedia, candidate, current.ProjectionVersion,
					candidate.Mode == "sync" && candidate.DeletePolicy == "tombstone",
				); err != nil {
					return nil, err
				}
				result = ReleaseActivationResult{Active: current, Replayed: true}
				return nil, nil
			}
			return nil, &ReleaseActivationCASConflictError{Expected: expected, Actual: current}
		}

		if !expectedActiveMatches(current, expected) {
			return nil, &ReleaseActivationCASConflictError{Expected: expected, Actual: current}
		}

		activationVersion, err := allocateReleaseProjectionVersion(txCtx, releaseSequences)
		if err != nil {
			return nil, err
		}
		if err := detectLivePostIdentityConflicts(
			txCtx, candidatePosts, livePosts, candidate,
		); err != nil {
			return nil, err
		}
		materializedPosts, targetPosts, err := materializeCandidatePosts(
			txCtx, candidatePosts, livePosts, candidate, activationVersion,
		)
		if err != nil {
			return nil, err
		}
		removedSnapshots := []ImportedPostDeletionSnapshot(nil)
		if candidate.Mode == "sync" && candidate.DeletePolicy == "tombstone" {
			removedSnapshots, err = tombstoneMissingLivePosts(
				txCtx, livePosts, candidate, activatedAt,
			)
		}
		if err != nil {
			return nil, err
		}
		materializedMedia, err := materializeCandidateMedia(
			txCtx, candidateMedia, liveMedia, candidate,
		)
		if err != nil {
			return nil, err
		}
		removedMedia := int64(0)
		if candidate.Mode == "sync" && candidate.DeletePolicy == "tombstone" {
			removedMedia, err = tombstoneMissingLiveMedia(
				txCtx, liveMedia, candidate, activatedAt,
			)
			if err != nil {
				return nil, err
			}
		}
		transitionOpts := ImportOptions{
			ReleaseID: candidate.ReleaseID, ManifestDigest: candidate.ManifestDigest,
			ReleaseKind: candidate.ReleaseKind,
			SourceOwner: candidate.SourceOwner, Mode: candidate.Mode,
			DeletePolicy: candidate.DeletePolicy, ProjectionVersion: activationVersion,
		}
		candidateEvents, err := BuildActivationPostLifecycleEvents(
			targetPosts, removedSnapshots, transitionOpts, activatedAt,
			current, current.Revision+1,
		)
		if err != nil {
			return nil, err
		}

		allEvents := candidateEvents
		if err := validateActivationOutboxClosure(
			txCtx, liveOutbox, candidate, allEvents,
		); err != nil {
			return nil, err
		}
		sort.Slice(allEvents, func(left, right int) bool {
			if allEvents[left].AggregateID != allEvents[right].AggregateID {
				return allEvents[left].AggregateID < allEvents[right].AggregateID
			}
			return allEvents[left].EventType < allEvents[right].EventType
		})
		outboxResult, err := appendImportedPostOutbox(
			txCtx, liveOutbox, liveSequences, allEvents,
			ImportOptions{
				ReleaseID: candidate.ReleaseID, ManifestDigest: candidate.ManifestDigest,
				SourceOwner:       candidate.SourceOwner,
				ProjectionVersion: activationVersion,
			},
			false, current.Revision+1,
		)
		if err != nil {
			return nil, err
		}
		if err := validateLiveReleaseClosure(
			txCtx, livePosts, liveOutbox, liveMedia, candidate, activationVersion,
			candidate.Mode == "sync" && candidate.DeletePolicy == "tombstone",
		); err != nil {
			return nil, err
		}

		pointer := importedReleasePointerDocument{
			Kind: releaseActivePointerKind, Status: "active", Environment: environment,
			SourceOwner: candidate.SourceOwner, ActiveReleaseID: candidate.ReleaseID,
			ManifestDigest:    candidate.ManifestDigest,
			ProjectionVersion: activationVersion, Revision: current.Revision + 1,
			ActivatedAt: activatedAt,
		}
		matched, err := compareAndSwapActivePointer(txCtx, state, pointer, expected)
		if err != nil {
			return nil, err
		}
		if !matched {
			return nil, &ReleaseActivationCASConflictError{Expected: expected, Actual: current}
		}
		visiblePointer, err := readActivePointerInTransaction(
			txCtx, state, environment, candidate.SourceOwner,
		)
		if err != nil {
			return nil, err
		}
		if !activeBindingMatches(visiblePointer, target) || visiblePointer.Revision != pointer.Revision {
			return nil, fmt.Errorf("GATE_BLOCK: active pointer CAS was not visible inside activation transaction")
		}
		attemptID := releaseActivationAttemptID(environment, candidate.SourceOwner, target, expected)
		if err := appendReleaseStageReceipt(txCtx, receipts, releaseStageReceipt{
			Environment: environment, SourceOwner: candidate.SourceOwner,
			ReleaseID: candidate.ReleaseID, ManifestDigest: candidate.ManifestDigest,
			Stage: "active", AttemptID: attemptID, Status: "passed", RecordedAt: activatedAt,
			AttemptedCount: candidate.Counts.PostsExpected,
			SuccessCount:   materializedPosts,
			Checkpoint:     "live-closure-and-active-pointer-cas-committed",
			ExpectedEmpty:  expected.Empty, ExpectedSourceOwner: expected.SourceOwner,
			ExpectedReleaseID:      expected.ReleaseID,
			ExpectedManifestDigest: expected.ManifestDigest,
			ExpectedRevision:       expected.Revision,
		}); err != nil {
			return nil, err
		}
		transitionEvents := make([]ImportedReleaseTransitionEvent, 0, len(allEvents))
		for _, event := range allEvents {
			transitionEvents = append(transitionEvents, ImportedReleaseTransitionEvent{
				EventID: event.EventID, EventType: event.EventType,
				SourceOwner: candidate.SourceOwner, ReleaseID: candidate.ReleaseID,
				ManifestDigest:     candidate.ManifestDigest,
				ActivationRevision: pointer.Revision,
				AggregateID:        event.AggregateID, AggregateVersion: event.AggregateVersion,
			})
		}
		result = ReleaseActivationResult{
			Active: activeReleaseBindingFromPointer(pointer),
			Previous: ImportedReleaseBinding{
				SourceOwner: current.SourceOwner, ReleaseID: current.ReleaseID,
				ManifestDigest: current.ManifestDigest,
			},
			PostsMaterialized: materializedPosts, PostsRemoved: int64(len(removedSnapshots)),
			MediaAssetsMaterialized: materializedMedia, MediaAssetsRemoved: removedMedia,
			TransitionEvents:  transitionEvents,
			OutboxEventsReady: len(allEvents), OutboxEventsAppended: outboxResult.Appended,
		}
		return nil, nil
	})
	if err != nil {
		return ReleaseActivationResult{}, err
	}
	return result, nil
}

func insertCandidatePosts(
	ctx context.Context,
	coll *mongo.Collection,
	environment string,
	posts []PostDoc,
	now time.Time,
	opts ImportOptions,
) (int, error) {
	inserted := 0
	for _, post := range posts {
		document, err := BuildCanonicalImportedPostDocument(post, now, opts, "candidate")
		if err != nil {
			return inserted, err
		}
		postID, _ := document["_id"].(string)
		document["_id"] = candidatePostDocumentID(environment, opts.SourceOwner, opts.ReleaseID, opts.ManifestDigest, postID)
		document["environment"] = environment
		digest, err := canonicalDocumentDigest(document, "documentDigest")
		if err != nil {
			return inserted, fmt.Errorf("digest candidate Post %q: %w", postID, err)
		}
		document["documentDigest"] = digest
		if _, err := coll.InsertOne(ctx, document); err != nil {
			return inserted, fmt.Errorf("insert candidate Post %q: %w", postID, err)
		}
		inserted++
	}
	return inserted, nil
}

func insertCandidatePostFacts(
	ctx context.Context,
	coll *mongo.Collection,
	environment string,
	posts []PostDoc,
	now time.Time,
	opts ImportOptions,
) (int, error) {
	inserted := 0
	for _, post := range posts {
		postID := RuntimePostID(post.ContentID)
		document := bson.M{
			"_id":         candidateOutboxDocumentID(environment, opts.SourceOwner, opts.ReleaseID, opts.ManifestDigest, postID),
			"environment": environment, "sourceOwner": opts.SourceOwner,
			"releaseId": opts.ReleaseID, "manifestDigest": opts.ManifestDigest,
			"postId": postID, "occurredAt": now,
		}
		digest, err := canonicalDocumentDigest(document, "documentDigest")
		if err != nil {
			return inserted, fmt.Errorf("digest candidate Post fact %q: %w", postID, err)
		}
		document["documentDigest"] = digest
		if _, err := coll.InsertOne(ctx, document); err != nil {
			return inserted, fmt.Errorf("insert candidate Post fact %q: %w", postID, err)
		}
		inserted++
	}
	return inserted, nil
}

func validateImmutableCandidateClosure(
	ctx context.Context,
	candidatePosts *mongo.Collection,
	candidateFacts *mongo.Collection,
	candidateMedia *mongo.Collection,
	candidate importedReleaseCandidateState,
	posts []PostDoc,
	mediaAssets map[string]ReleaseMediaAsset,
	requestedAt time.Time,
	opts ImportOptions,
) (ImportedReleaseApplyResult, error) {
	if candidate.Counts.PostsProjected != len(posts) || candidate.Counts.OutboxProjected != len(posts) ||
		candidate.Counts.MediaProjected != len(mediaAssets) {
		return ImportedReleaseApplyResult{}, fmt.Errorf("GATE_BLOCK: verified candidate closure count differs")
	}
	for _, post := range posts {
		document, err := BuildCanonicalImportedPostDocument(post, candidate.VerifiedAt, opts, "candidate")
		if err != nil {
			return ImportedReleaseApplyResult{}, err
		}
		postID := document["_id"].(string)
		document["_id"] = candidatePostDocumentID(candidate.Environment, candidate.SourceOwner, candidate.ReleaseID, candidate.ManifestDigest, postID)
		document["environment"] = candidate.Environment
		if err := verifyCandidateDocument(ctx, candidatePosts, document); err != nil {
			return ImportedReleaseApplyResult{}, fmt.Errorf("verify candidate Post %q: %w", postID, err)
		}
		fact := bson.M{
			"_id":         candidateOutboxDocumentID(candidate.Environment, candidate.SourceOwner, candidate.ReleaseID, candidate.ManifestDigest, postID),
			"environment": candidate.Environment, "sourceOwner": candidate.SourceOwner,
			"releaseId": candidate.ReleaseID, "manifestDigest": candidate.ManifestDigest,
			"postId": postID, "occurredAt": candidate.VerifiedAt,
		}
		if err := verifyCandidateDocument(ctx, candidateFacts, fact); err != nil {
			return ImportedReleaseApplyResult{}, fmt.Errorf("verify candidate Post fact %q: %w", postID, err)
		}
	}
	if err := ValidateReleaseMediaAssetProjectionClosure(
		ctx, candidateMedia, mediaAssets, candidate.Environment, candidate.SourceOwner,
		candidate.ReleaseID, candidate.ManifestDigest, candidate.VerifiedAt,
	); err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	return ImportedReleaseApplyResult{
		PostsExpected: len(posts), PostsUpserted: len(posts),
		OutboxEventsReady: len(posts), MediaAssetsExpected: len(mediaAssets),
		MediaAssetsProjected: len(mediaAssets), ProjectionVersion: candidate.ProjectionVersion,
	}, nil
}

func verifyCandidateDocument(ctx context.Context, collection *mongo.Collection, expected bson.M) error {
	id := expected["_id"]
	var actual bson.M
	if err := collection.FindOne(ctx, bson.M{"_id": id}).Decode(&actual); err != nil {
		return err
	}
	storedDigest, _ := actual["documentDigest"].(string)
	expectedDigest, err := canonicalDocumentDigest(expected, "documentDigest")
	if err != nil {
		return err
	}
	actualDigest, err := canonicalDocumentDigest(actual, "documentDigest")
	if err != nil {
		return err
	}
	if storedDigest == "" || storedDigest != expectedDigest || actualDigest != storedDigest {
		return fmt.Errorf("GATE_BLOCK: immutable candidate document digest drift")
	}
	return nil
}

func canonicalDocumentDigest(document bson.M, excludedFields ...string) (string, error) {
	copy := bson.M{}
	for key, value := range document {
		copy[key] = value
	}
	for _, field := range excludedFields {
		delete(copy, field)
	}
	raw, err := bson.MarshalExtJSON(copy, true, false)
	if err != nil {
		return "", err
	}
	var normalized any
	if err := json.Unmarshal(raw, &normalized); err != nil {
		return "", err
	}
	canonicalJSON, err := json.Marshal(normalized)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(canonicalJSON)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

func collectionClosureDigest(ctx context.Context, collection *mongo.Collection, filter bson.M) (string, error) {
	cursor, err := collection.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}).SetProjection(bson.M{"_id": 1, "documentDigest": 1}))
	if err != nil {
		return "", err
	}
	defer cursor.Close(ctx)
	parts := []string{}
	for cursor.Next(ctx) {
		var row struct {
			ID     any    `bson:"_id"`
			Digest string `bson:"documentDigest"`
		}
		if err := cursor.Decode(&row); err != nil {
			return "", err
		}
		if row.Digest == "" {
			return "", fmt.Errorf("candidate closure item has no document digest")
		}
		parts = append(parts, fmt.Sprint(row.ID)+"="+row.Digest)
	}
	if err := cursor.Err(); err != nil {
		return "", err
	}
	sum := sha256.Sum256([]byte(strings.Join(parts, "\n")))
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

func insertVerifiedCandidateState(
	ctx context.Context,
	state *mongo.Collection,
	candidatePosts *mongo.Collection,
	candidateFacts *mongo.Collection,
	candidateMedia *mongo.Collection,
	environment string,
	opts ImportOptions,
	verifiedAt time.Time,
	result ImportedReleaseApplyResult,
) error {
	filter := bson.M{"environment": environment, "sourceOwner": opts.SourceOwner, "releaseId": opts.ReleaseID, "manifestDigest": opts.ManifestDigest}
	postClosureDigest, err := collectionClosureDigest(ctx, candidatePosts, filter)
	if err != nil {
		return err
	}
	factClosureDigest, err := collectionClosureDigest(ctx, candidateFacts, filter)
	if err != nil {
		return err
	}
	mediaClosureDigest, err := collectionClosureDigest(ctx, candidateMedia, filter)
	if err != nil {
		return err
	}
	counts := importedReleaseCandidateCounts{
		PostsExpected: result.PostsExpected, PostsProjected: result.PostsUpserted,
		OutboxExpected: result.OutboxEventsReady, OutboxProjected: result.OutboxEventsReady,
		MediaExpected: result.MediaAssetsExpected, MediaProjected: result.MediaAssetsProjected,
	}
	document := bson.M{
		"_id":  candidateStateDocumentID(environment, opts.SourceOwner, opts.ReleaseID, opts.ManifestDigest),
		"kind": releaseCandidateKind, "environment": environment,
		"sourceOwner": opts.SourceOwner, "releaseId": opts.ReleaseID,
		"manifestDigest": opts.ManifestDigest,
		"releaseKind":    opts.ReleaseKind, "mode": opts.Mode, "deletePolicy": opts.DeletePolicy,
		"postClosureDigest": postClosureDigest, "factClosureDigest": factClosureDigest,
		"mediaClosureDigest": mediaClosureDigest, "status": "verified", "projectionVersion": opts.ProjectionVersion,
		"verifiedAt": verifiedAt, "counts": counts, "createdAt": verifiedAt,
	}
	if _, err := state.InsertOne(ctx, document); err != nil {
		return fmt.Errorf("insert verified release candidate: %w", err)
	}
	return nil
}

func candidateStateDocumentID(environment, owner, releaseID, digest string) string {
	return scopedReleaseDocumentID("candidate-state", environment, owner, releaseID, digest, "")
}
func candidatePostDocumentID(environment, owner, releaseID, digest, postID string) string {
	return scopedReleaseDocumentID("candidate-post", environment, owner, releaseID, digest, postID)
}
func candidateOutboxDocumentID(environment, owner, releaseID, digest, eventID string) string {
	return scopedReleaseDocumentID("candidate-outbox", environment, owner, releaseID, digest, eventID)
}
func candidateMediaAssetDocumentID(environment, owner, releaseID, digest, assetID string) string {
	return scopedReleaseDocumentID("candidate-media", environment, owner, releaseID, digest, assetID)
}
func scopedReleaseDocumentID(kind, environment, owner, releaseID, digest, itemID string) string {
	sum := sha256.Sum256([]byte(strings.Join([]string{kind, environment, owner, releaseID, digest, itemID}, "\x00")))
	return kind + ":" + hex.EncodeToString(sum[:])
}

func releaseActivationAttemptID(
	environment string,
	sourceOwner string,
	target ImportedReleaseBinding,
	expected ExpectedActiveRelease,
) string {
	identity := strings.Join([]string{
		environment, sourceOwner, target.ReleaseID, target.ManifestDigest,
		expected.SourceOwner, expected.ReleaseID, expected.ManifestDigest, fmt.Sprint(expected.Revision), fmt.Sprint(expected.Empty),
	}, "\x00")
	sum := sha256.Sum256([]byte(identity))
	return "activate:" + hex.EncodeToString(sum[:])
}

// ValidateReplayRepairBinding is retained for bounded pure-function tests. New
// candidate staging rejects repair replay before entering Mongo.
func ValidateReplayRepairBinding(opts ImportOptions, replayed bool) error {
	if opts.RequireReplay && !replayed {
		return fmt.Errorf(
			"GATE_BLOCK: content release repair requires exact active release %q (%s)",
			opts.ReleaseID,
			opts.ManifestDigest,
		)
	}
	return nil
}

func ValidateExpectedOutboxRepairCount(
	opts ImportOptions,
	result ImportedReleaseApplyResult,
) error {
	if opts.ExpectedOutboxRepairCount != nil &&
		result.OutboxEventsRepaired != *opts.ExpectedOutboxRepairCount {
		return fmt.Errorf(
			"GATE_BLOCK: imported outbox repair count mismatch: expected=%d repaired=%d",
			*opts.ExpectedOutboxRepairCount,
			result.OutboxEventsRepaired,
		)
	}
	return nil
}

// ValidateImportedReleaseApplyResult requires exact Post/outbox/media counts.
// The prior repair-only shape remains valid for the bounded repair helpers,
// while StageImportedPostRelease itself forbids entering that rail.
func ValidateImportedReleaseApplyResult(
	result ImportedReleaseApplyResult,
	expectedPosts int,
) error {
	if expectedPosts < 0 {
		return fmt.Errorf("expected imported Post count must be non-negative")
	}
	if result.PostsUpserted != expectedPosts {
		return fmt.Errorf("Manifest/import Post count mismatch: expected=%d upserted=%d", expectedPosts, result.PostsUpserted)
	}
	if result.MediaAssetsExpected < 0 || result.MediaAssetsProjected < 0 ||
		result.MediaAssetsProjected != result.MediaAssetsExpected {
		return fmt.Errorf(
			"Manifest/media projection count mismatch: expected=%d projected=%d",
			result.MediaAssetsExpected, result.MediaAssetsProjected,
		)
	}
	if result.PostDeletionEventsReady < 0 || result.OutboxEventsRepaired < 0 ||
		result.OutboxEventsRepaired > result.PostDeletionEventsReady {
		return fmt.Errorf("imported Post deletion repair counts are invalid")
	}
	if result.RepairReplay && !result.Replayed {
		return fmt.Errorf("repair replay result does not bind the active release")
	}
	if result.Replayed {
		if result.PostsRemoved != 0 {
			return fmt.Errorf("replayed release mutated missing Posts: %d", result.PostsRemoved)
		}
	} else if int64(result.PostDeletionEventsReady) != result.PostsRemoved {
		return fmt.Errorf(
			"Post deletion event/removal count mismatch: ready=%d removed=%d",
			result.PostDeletionEventsReady, result.PostsRemoved,
		)
	}
	if !result.RepairReplay && result.OutboxEventsRepaired != 0 {
		return fmt.Errorf("non-repair release repaired existing outbox events")
	}
	expectedEvents := expectedPosts + result.PostDeletionEventsReady
	if result.RepairReplay {
		expectedEvents = result.PostDeletionEventsReady
	}
	if result.OutboxEventsReady != expectedEvents {
		return fmt.Errorf("Manifest/outbox event count mismatch: expected=%d ready=%d", expectedEvents, result.OutboxEventsReady)
	}
	if result.Replayed {
		if result.OutboxEventsAppended != 0 {
			return fmt.Errorf("replayed release appended duplicate outbox events: %d", result.OutboxEventsAppended)
		}
	} else if result.OutboxEventsAppended != result.OutboxEventsReady {
		return fmt.Errorf(
			"Manifest/outbox append count mismatch: ready=%d appended=%d",
			result.OutboxEventsReady, result.OutboxEventsAppended,
		)
	}
	return nil
}

func ensureImportedReleaseIndexes(
	ctx context.Context,
	posts *mongo.Collection,
	outbox *mongo.Collection,
	media *mongo.Collection,
	state *mongo.Collection,
	receipts *mongo.Collection,
) error {
	if _, err := posts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}, {Key: "postId", Value: 1}}, Options: options.Index().SetName("uq_data_release_candidate_post").SetUnique(true)},
		{Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}, {Key: "postRef", Value: 1}}, Options: options.Index().SetName("idx_data_release_candidate_post_ref").SetUnique(true)},
	}); err != nil {
		return fmt.Errorf("ensure candidate Post indexes: %w", err)
	}
	if _, err := outbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}, {Key: "postId", Value: 1}},
		Options: options.Index().SetName("uq_data_release_candidate_outbox_event").SetUnique(true),
	}); err != nil {
		return fmt.Errorf("ensure candidate Post outbox index: %w", err)
	}
	if _, err := media.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}, {Key: "assetId", Value: 1}},
		Options: options.Index().SetName("uq_data_release_candidate_media_asset").SetUnique(true),
	}); err != nil {
		return fmt.Errorf("ensure candidate media projection index: %w", err)
	}
	return ensureReleaseControlIndexes(ctx, state, receipts)
}

// BuildImportedPostLifecycleEvents creates the only lifecycle facts for a
// Data import. The same release binding and projection version produce the
// same event identities and payloads.
func BuildImportedPostLifecycleEvents(
	posts []PostDoc,
	deletedPosts []ImportedPostDeletionSnapshot,
	opts ImportOptions,
	occurredAt time.Time,
) ([]postports.OutboxEvent, error) {
	opts = NormalizeImportOptions(opts)
	if opts.ProjectionVersion <= 0 {
		return nil, fmt.Errorf("imported Post lifecycle projectionVersion must be positive")
	}
	occurredAt = occurredAt.UTC().Truncate(time.Millisecond)
	if occurredAt.IsZero() {
		return nil, fmt.Errorf("imported Post lifecycle occurredAt is required")
	}
	events := make([]postports.OutboxEvent, 0, len(posts)+len(deletedPosts))
	for _, post := range posts {
		contentIdentity, err := canonicalImportedContentIdentity(post.ContentIdentity)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", post.PostRef, err)
		}
		entityRefs := post.NormalizedEntityRefs
		if len(entityRefs) == 0 {
			entityRefs = post.EntityRefs
		}
		// lifecycle payload 只消费 summary 字段，不含 mediaItems；accessMode
		// 传映射值不影响既有 payload 字节（replay byte-for-byte 依赖）。
		media := ImportedMediaFields(
			importedPostAssets(post),
			MediaDeliveryAccessModePublic,
		)
		body := post.ArticleMarkdown
		summary := ProjectImportedArticleSummary(post.ArticleMarkdown)
		if post.ContentType == "image" {
			body = post.Body
			summary = post.Body
		}
		postID := RuntimePostID(post.ContentID)
		if postID == "" {
			return nil, fmt.Errorf("imported Post postRef is required")
		}
		payload, err := json.Marshal(bson.M{
			"postId":                    postID,
			"contentId":                 post.ContentID,
			"contentVersion":            post.ContentVersion,
			"variantPurpose":            post.VariantPurpose,
			"usageScope":                post.Admission.UsageScope,
			"status":                    "published",
			"visibility":                "public",
			"moderationStatus":          importedModerationStatus,
			"contentType":               post.ContentType,
			"contentIdentity":           contentIdentity,
			"authorId":                  post.AuthorID,
			"authorDisplayNameSnapshot": post.AuthorDisplayName,
			"authorAvatarUrlSnapshot":   post.AuthorAvatarURL,
			"title":                     post.Title,
			"body":                      body,
			"summary":                   summary,
			"mediaUrls":                 media.MediaURLs,
			"coverUrl":                  media.CoverURL,
			"thumbnailUrl":              media.ThumbnailURL,
			"videoUrl":                  media.VideoURL,
			"width":                     media.Width,
			"height":                    media.Height,
			"durationMs":                media.DurationMs,
			"tagRefs":                   post.TagRefs,
			"entityRefs":                entityRefs,
			"contentVertical":           post.Angle,
			"createdAt":                 post.CreatedAt,
			"publishedAt":               post.PublishedAt,
			"updatedAt":                 post.UpdatedAt,
			"sourceOwner":               opts.SourceOwner,
			"releaseId":                 opts.ReleaseID,
			"releaseDigest":             opts.ManifestDigest,
		})
		if err != nil {
			return nil, fmt.Errorf("encode imported Post lifecycle %s: %w", post.PostRef, err)
		}
		events = append(events, postports.OutboxEvent{
			EventID: fmt.Sprintf(
				"data-release:%d:%s:%s:PostPublished",
				opts.ProjectionVersion,
				opts.ReleaseID,
				postID,
			),
			EventType:        "PostPublished",
			AggregateType:    "Post",
			AggregateID:      postID,
			AggregateVersion: opts.ProjectionVersion,
			Payload:          payload,
			OccurredAt:       occurredAt,
		})
	}
	for _, snapshot := range deletedPosts {
		postID := strings.TrimSpace(snapshot.PostID)
		authorID := strings.TrimSpace(snapshot.AuthorID)
		contentType := strings.TrimSpace(snapshot.ContentType)
		status := strings.TrimSpace(snapshot.Status)
		contentIdentity, err := canonicalImportedContentIdentity(
			snapshot.ContentIdentity,
		)
		if err != nil {
			return nil, fmt.Errorf("deleted Post %q: %w", postID, err)
		}
		if postID == "" || authorID == "" || contentType == "" || status == "" {
			return nil, fmt.Errorf(
				"deleted Post lifecycle snapshot lacks canonical fields",
			)
		}
		payload, err := json.Marshal(bson.M{
			"postId":          postID,
			"authorId":        authorID,
			"contentType":     contentType,
			"contentIdentity": contentIdentity,
			"status":          status,
			"deletedAt":       occurredAt,
		})
		if err != nil {
			return nil, fmt.Errorf("encode imported Post deletion %s: %w", postID, err)
		}
		events = append(events, postports.OutboxEvent{
			EventID: fmt.Sprintf(
				"data-release:%d:%s:%s:PostDeleted",
				opts.ProjectionVersion,
				opts.ReleaseID,
				postID,
			),
			EventType:        "PostDeleted",
			AggregateType:    "Post",
			AggregateID:      postID,
			AggregateVersion: opts.ProjectionVersion,
			Payload:          payload,
			OccurredAt:       occurredAt,
		})
	}
	sort.Slice(events, func(left, right int) bool {
		if events[left].AggregateID != events[right].AggregateID {
			return events[left].AggregateID < events[right].AggregateID
		}
		return events[left].EventType < events[right].EventType
	})
	return events, nil
}

// BuildImportedPostDeletionLifecycleEvents projects only PostDeleted facts.
// Activation uses it for full-sync tombstones; the bounded repair rail also
// reuses it without rewriting historical PostPublished facts.
func BuildImportedPostDeletionLifecycleEvents(
	deletedPosts []ImportedPostDeletionSnapshot,
	opts ImportOptions,
	occurredAt time.Time,
) ([]postports.OutboxEvent, error) {
	return BuildImportedPostLifecycleEvents(nil, deletedPosts, opts, occurredAt)
}

func appendImportedPostOutbox(
	ctx context.Context,
	outbox *mongo.Collection,
	sequences *mongo.Collection,
	events []postports.OutboxEvent,
	opts ImportOptions,
	replayed bool,
	activationRevision ...int64,
) (importedPostOutboxApplyResult, error) {
	revision := int64(0)
	if len(activationRevision) > 0 {
		revision = activationRevision[0]
	}
	if !replayed && len(events) > 0 {
		if revision <= 0 {
			return importedPostOutboxApplyResult{}, fmt.Errorf("activation outbox requires positive activationRevision")
		}
		if strings.TrimSpace(opts.SourceOwner) == "" ||
			strings.TrimSpace(opts.ReleaseID) == "" ||
			!sha256Pattern.MatchString(strings.TrimSpace(opts.ManifestDigest)) {
			return importedPostOutboxApplyResult{}, fmt.Errorf("activation outbox release tuple is incomplete")
		}
	}
	if replayed {
		existingDeletions, err := loadImportedPostDeletionReplayEvents(
			ctx,
			outbox,
			opts,
		)
		if err != nil {
			return importedPostOutboxApplyResult{}, err
		}
		if err := ValidateImportedPostDeletionReplayClosure(
			existingDeletions,
			events,
			opts,
		); err != nil {
			return importedPostOutboxApplyResult{}, err
		}
	}
	missing := make([]postports.OutboxEvent, 0, len(events))
	repairs := make([]ImportedPostOutboxRepairAudit, 0)
	cas := mongoImportedPostOutboxPayloadCAS{collection: outbox}
	for _, event := range events {
		var existing importedOutboxDocument
		err := outbox.FindOne(ctx, bson.M{"_id": event.EventID}).Decode(&existing)
		if err == mongo.ErrNoDocuments {
			missing = append(missing, event)
			continue
		}
		if err != nil {
			return importedPostOutboxApplyResult{}, fmt.Errorf("read imported Post outbox event %q: %w", event.EventID, err)
		}
		snapshot := importedPostOutboxEventSnapshot(existing)
		if !replayed && !bytes.Equal(snapshot.PayloadJSON, event.Payload) {
			return importedPostOutboxApplyResult{}, fmt.Errorf(
				"GATE_BLOCK CONTENT.CONFLICT.DATA_RELEASE_EVENT_DIGEST: event %q was replayed with different facts",
				event.EventID,
			)
		}
		repair, err := RepairImportedPostOutboxEvent(
			ctx,
			cas,
			snapshot,
			event,
			opts,
		)
		if err != nil {
			return importedPostOutboxApplyResult{}, err
		}
		if repair != nil {
			repairs = append(repairs, *repair)
		}
	}
	if len(missing) == 0 {
		return importedPostOutboxApplyResult{Repairs: repairs}, nil
	}
	var sequenceCounter struct {
		Value int64 `bson:"value"`
	}
	if err := sequences.FindOneAndUpdate(
		ctx,
		bson.M{"_id": "Post"},
		bson.M{"$inc": bson.M{"value": int64(len(missing))}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&sequenceCounter); err != nil {
		return importedPostOutboxApplyResult{}, fmt.Errorf("allocate imported Post outbox sequence: %w", err)
	}
	firstSequence := sequenceCounter.Value - int64(len(missing)) + 1
	documents := make([]any, 0, len(missing))
	for index, event := range missing {
		documents = append(documents, importedOutboxDocument{
			ID: event.EventID, SourceOwner: opts.SourceOwner,
			ReleaseID: opts.ReleaseID, ManifestDigest: opts.ManifestDigest,
			OutboxSequence:     firstSequence + int64(index),
			EventType:          event.EventType,
			AggregateType:      event.AggregateType,
			AggregateID:        event.AggregateID,
			AggregateVersion:   event.AggregateVersion,
			PayloadJSON:        event.Payload,
			ActivationRevision: revision,
			OccurredAt:         event.OccurredAt,
		})
	}
	if _, err := outbox.InsertMany(ctx, documents); err != nil {
		return importedPostOutboxApplyResult{}, fmt.Errorf("append imported Post outbox: %w", err)
	}
	return importedPostOutboxApplyResult{
		Appended: len(missing),
		Repairs:  repairs,
	}, nil
}

func importedPostOutboxEventSnapshot(
	document importedOutboxDocument,
) ImportedPostOutboxEventSnapshot {
	return ImportedPostOutboxEventSnapshot{
		EventID: document.ID, OutboxSequence: document.OutboxSequence,
		EventType: document.EventType, AggregateType: document.AggregateType,
		AggregateID: document.AggregateID, AggregateVersion: document.AggregateVersion,
		PayloadJSON:        append([]byte(nil), document.PayloadJSON...),
		ActivationRevision: document.ActivationRevision,
		OccurredAt:         document.OccurredAt,
	}
}

type mongoImportedPostOutboxPayloadCAS struct {
	collection *mongo.Collection
}

func (cas mongoImportedPostOutboxPayloadCAS) CompareAndSwapImportedPostOutboxPayload(
	ctx context.Context,
	existing ImportedPostOutboxEventSnapshot,
	replacement json.RawMessage,
) (bool, error) {
	result, err := cas.collection.UpdateOne(ctx, bson.M{
		"_id": existing.EventID, "outboxSequence": existing.OutboxSequence,
		"eventType": existing.EventType, "aggregateType": existing.AggregateType,
		"aggregateId": existing.AggregateID, "aggregateVersion": existing.AggregateVersion,
		"activationRevision": existing.ActivationRevision,
		"occurredAt":         existing.OccurredAt, "payloadJson": existing.PayloadJSON,
	}, bson.M{"$set": bson.M{"payloadJson": replacement}})
	if err != nil {
		return false, err
	}
	return result.MatchedCount == 1 && result.ModifiedCount == 1, nil
}

// RepairImportedPostOutboxEvent recognizes only the one historical malformed
// PostDeleted shape and replaces only payloadJson through an exact CAS.
func RepairImportedPostOutboxEvent(
	ctx context.Context,
	cas ImportedPostOutboxPayloadCAS,
	existing ImportedPostOutboxEventSnapshot,
	expected postports.OutboxEvent,
	opts ImportOptions,
) (*ImportedPostOutboxRepairAudit, error) {
	if existing.EventID != expected.EventID || existing.OutboxSequence <= 0 ||
		existing.EventType != expected.EventType ||
		existing.AggregateType != expected.AggregateType ||
		existing.AggregateID != expected.AggregateID ||
		existing.AggregateVersion != expected.AggregateVersion ||
		!existing.OccurredAt.Equal(expected.OccurredAt) {
		return nil, fmt.Errorf(
			"GATE_BLOCK CONTENT.CONFLICT.DATA_RELEASE_EVENT_DIGEST: event %q envelope drift",
			expected.EventID,
		)
	}
	if bytes.Equal(existing.PayloadJSON, expected.Payload) {
		return nil, nil
	}
	if existing.EventType != "PostDeleted" || expected.EventType != "PostDeleted" {
		return nil, fmt.Errorf(
			"GATE_BLOCK CONTENT.CONFLICT.DATA_RELEASE_EVENT_DIGEST: event %q is not a repairable PostDeleted",
			expected.EventID,
		)
	}
	if err := validateRepairableImportedPostDeletedPayload(existing, expected, opts); err != nil {
		return nil, err
	}
	if cas == nil {
		return nil, fmt.Errorf("GATE_BLOCK: imported PostDeleted repair CAS is unavailable")
	}
	audit := ImportedPostOutboxRepairAudit{
		EventID: expected.EventID, BeforeSHA256: importedPayloadSHA256(existing.PayloadJSON),
		AfterSHA256: importedPayloadSHA256(expected.Payload),
	}
	matched, err := cas.CompareAndSwapImportedPostOutboxPayload(
		ctx,
		existing,
		expected.Payload,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"GATE_BLOCK: repair imported PostDeleted %q: %w",
			expected.EventID,
			err,
		)
	}
	if !matched {
		return nil, fmt.Errorf(
			"GATE_BLOCK: imported PostDeleted repair CAS mismatch for event %q",
			expected.EventID,
		)
	}
	return &audit, nil
}

type releaseScopedImportedPostDeletedPayload struct {
	PostID        string `json:"postId"`
	ReleaseID     string `json:"releaseId"`
	ReleaseDigest string `json:"releaseDigest"`
	SourceOwner   string `json:"sourceOwner"`
	DeletedAt     string `json:"deletedAt"`
}

type intermediateImportedPostDeletedPayload struct {
	PostID          string `json:"postId"`
	AuthorID        string `json:"authorId"`
	ContentType     string `json:"contentType"`
	ContentIdentity string `json:"contentIdentity"`
	Status          string `json:"status"`
	DeletedAt       string `json:"deletedAt"`
}

func validateRepairableImportedPostDeletedPayload(
	existing ImportedPostOutboxEventSnapshot,
	expected postports.OutboxEvent,
	opts ImportOptions,
) error {
	var keyset map[string]json.RawMessage
	if err := json.Unmarshal(existing.PayloadJSON, &keyset); err != nil {
		return fmt.Errorf("GATE_BLOCK: repairable PostDeleted payload is not JSON")
	}
	gotKeys := make([]string, 0, len(keyset))
	for key := range keyset {
		gotKeys = append(gotKeys, key)
	}
	sort.Strings(gotKeys)
	releaseScopedKeys := []string{"deletedAt", "postId", "releaseDigest", "releaseId", "sourceOwner"}
	intermediateKeys := []string{"authorId", "contentIdentity", "contentType", "deletedAt", "postId", "status"}
	switch {
	case slicesEqualStrings(gotKeys, releaseScopedKeys):
		return validateReleaseScopedImportedPostDeletedPayload(existing, expected, opts)
	case slicesEqualStrings(gotKeys, intermediateKeys):
		return validateIntermediateImportedPostDeletedPayload(existing, expected)
	default:
		return fmt.Errorf("GATE_BLOCK: PostDeleted payload keyset is not repairable")
	}
}

func validateReleaseScopedImportedPostDeletedPayload(
	existing ImportedPostOutboxEventSnapshot,
	expected postports.OutboxEvent,
	opts ImportOptions,
) error {
	var keyset map[string]json.RawMessage
	if err := json.Unmarshal(existing.PayloadJSON, &keyset); err != nil {
		return fmt.Errorf("GATE_BLOCK: release-scoped PostDeleted payload is not JSON")
	}
	wantKeys := []string{"deletedAt", "postId", "releaseDigest", "releaseId", "sourceOwner"}
	gotKeys := make([]string, 0, len(keyset))
	for key := range keyset {
		gotKeys = append(gotKeys, key)
	}
	sort.Strings(gotKeys)
	if !slicesEqualStrings(gotKeys, wantKeys) {
		return fmt.Errorf("GATE_BLOCK: release-scoped PostDeleted payload keyset is not repairable")
	}
	var payload releaseScopedImportedPostDeletedPayload
	decoder := json.NewDecoder(bytes.NewReader(existing.PayloadJSON))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return fmt.Errorf("GATE_BLOCK: decode release-scoped PostDeleted payload: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return fmt.Errorf("GATE_BLOCK: release-scoped PostDeleted payload contains trailing JSON")
	}
	deletedAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(payload.DeletedAt))
	if err != nil || payload.PostID != expected.AggregateID ||
		payload.ReleaseID != opts.ReleaseID ||
		payload.ReleaseDigest != opts.ManifestDigest ||
		payload.SourceOwner != opts.SourceOwner ||
		!deletedAt.Equal(expected.OccurredAt) {
		return fmt.Errorf("GATE_BLOCK: release-scoped PostDeleted payload binding drift")
	}
	return nil
}

func validateIntermediateImportedPostDeletedPayload(
	existing ImportedPostOutboxEventSnapshot,
	expected postports.OutboxEvent,
) error {
	decode := func(raw []byte, label string) (intermediateImportedPostDeletedPayload, error) {
		var payload intermediateImportedPostDeletedPayload
		decoder := json.NewDecoder(bytes.NewReader(raw))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&payload); err != nil {
			return intermediateImportedPostDeletedPayload{}, fmt.Errorf(
				"GATE_BLOCK: decode %s PostDeleted payload: %w",
				label,
				err,
			)
		}
		var trailing any
		if err := decoder.Decode(&trailing); err != io.EOF {
			return intermediateImportedPostDeletedPayload{}, fmt.Errorf(
				"GATE_BLOCK: %s PostDeleted payload contains trailing JSON",
				label,
			)
		}
		return payload, nil
	}
	current, err := decode(existing.PayloadJSON, "intermediate")
	if err != nil {
		return err
	}
	want, err := decode(expected.Payload, "canonical")
	if err != nil {
		return err
	}
	currentDeletedAt, currentTimeErr := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(current.DeletedAt),
	)
	wantDeletedAt, wantTimeErr := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(want.DeletedAt),
	)
	if currentTimeErr != nil || wantTimeErr != nil ||
		current.PostID != want.PostID ||
		current.AuthorID != want.AuthorID ||
		current.ContentType != want.ContentType ||
		current.ContentIdentity != want.ContentIdentity ||
		current.Status != "deleted" || want.Status != "published" ||
		!currentDeletedAt.Equal(wantDeletedAt) ||
		!wantDeletedAt.Equal(expected.OccurredAt) {
		return fmt.Errorf("GATE_BLOCK: intermediate PostDeleted payload binding drift")
	}
	return nil
}

func slicesEqualStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func importedPayloadSHA256(payload []byte) string {
	digest := sha256.Sum256(payload)
	return fmt.Sprintf("sha256:%x", digest)
}

func loadImportedPostDeletionReplayEvents(
	ctx context.Context,
	outbox *mongo.Collection,
	opts ImportOptions,
) ([]ImportedPostOutboxEventSnapshot, error) {
	prefix := fmt.Sprintf(
		"data-release:%d:%s:",
		opts.ProjectionVersion,
		opts.ReleaseID,
	)
	cursor, err := outbox.Find(ctx, bson.M{
		"_id": bson.M{"$regex": "^" + regexp.QuoteMeta(prefix) + ".+:PostDeleted$"},
	}, options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}))
	if err != nil {
		return nil, fmt.Errorf("load replay PostDeleted outbox closure: %w", err)
	}
	defer cursor.Close(ctx)
	result := make([]ImportedPostOutboxEventSnapshot, 0)
	for cursor.Next(ctx) {
		var document importedOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode replay PostDeleted outbox closure: %w", err)
		}
		result = append(result, importedPostOutboxEventSnapshot(document))
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("scan replay PostDeleted outbox closure: %w", err)
	}
	return result, nil
}

// ValidateImportedPostDeletionReplayClosure requires an exact one-to-one set
// between replay-frozen tombstone snapshots and durable PostDeleted events.
func ValidateImportedPostDeletionReplayClosure(
	existing []ImportedPostOutboxEventSnapshot,
	expected []postports.OutboxEvent,
	opts ImportOptions,
) error {
	want := make(map[string]struct{})
	for _, event := range expected {
		if event.EventType == "PostDeleted" {
			want[event.EventID] = struct{}{}
		}
	}
	seen := make(map[string]struct{}, len(existing))
	for _, event := range existing {
		if _, ok := want[event.EventID]; !ok {
			return fmt.Errorf(
				"GATE_BLOCK: active release %q has PostDeleted event %q without a canonical tombstone snapshot",
				opts.ReleaseID,
				event.EventID,
			)
		}
		if _, duplicate := seen[event.EventID]; duplicate {
			return fmt.Errorf("GATE_BLOCK: duplicate replay PostDeleted event %q", event.EventID)
		}
		seen[event.EventID] = struct{}{}
	}
	for eventID := range want {
		if _, ok := seen[eventID]; !ok {
			return fmt.Errorf(
				"GATE_BLOCK: canonical tombstone snapshot %q has no durable PostDeleted event",
				eventID,
			)
		}
	}
	return nil
}

func validateActivationReplayReceipt(
	ctx context.Context,
	receipts *mongo.Collection,
	environment string,
	target ImportedReleaseBinding,
	expected ExpectedActiveRelease,
) error {
	attemptID := releaseActivationAttemptID(environment, target.SourceOwner, target, expected)
	var receipt releaseStageReceipt
	if err := receipts.FindOne(ctx, bson.M{
		"environment": environment, "sourceOwner": target.SourceOwner,
		"releaseId": target.ReleaseID, "manifestDigest": target.ManifestDigest,
		"stage": "active", "attemptId": attemptID,
	}).Decode(&receipt); err != nil {
		return fmt.Errorf("GATE_BLOCK: read exact activation replay receipt: %w", err)
	}
	if receipt.ExpectedEmpty != expected.Empty ||
		receipt.ExpectedSourceOwner != expected.SourceOwner ||
		receipt.ExpectedReleaseID != expected.ReleaseID ||
		receipt.ExpectedManifestDigest != expected.ManifestDigest ||
		receipt.ExpectedRevision != expected.Revision {
		return fmt.Errorf("GATE_BLOCK: activation replay predecessor receipt differs")
	}
	return nil
}
