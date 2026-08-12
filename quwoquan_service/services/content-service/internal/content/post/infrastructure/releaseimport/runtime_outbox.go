package releaseimport

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
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

// ImportedReleaseApplyResult is the Content-owned result of materializing one
// immutable Data release. Post rows, lifecycle outbox facts and the active
// release pointer are committed together; Recommendation and Search only
// derive from those durable Post facts.
type ImportedReleaseApplyResult struct {
	PostsUpserted           int
	PostsRemoved            int64
	PostDeletionEventsReady int
	OutboxEventsReady       int
	OutboxEventsAppended    int
	OutboxEventsRepaired    int
	OutboxRepairAudits      []ImportedPostOutboxRepairAudit
	ProjectionVersion       int64
	Replayed                bool
	RepairReplay            bool
	PreviousReleaseID       string
	PreviousManifestDigest  string
}

type importedReleaseState struct {
	ActiveReleaseID   string    `bson:"activeReleaseId"`
	ManifestDigest    string    `bson:"manifestDigest"`
	Status            string    `bson:"status"`
	ProjectionVersion int64     `bson:"projectionVersion"`
	ActivatedAt       time.Time `bson:"activatedAt"`
}

type importedOutboxDocument struct {
	ID               string          `bson:"_id"`
	OutboxSequence   int64           `bson:"outboxSequence"`
	EventType        string          `bson:"eventType"`
	AggregateType    string          `bson:"aggregateType"`
	AggregateID      string          `bson:"aggregateId"`
	AggregateVersion int64           `bson:"aggregateVersion"`
	PayloadJSON      json.RawMessage `bson:"payloadJson"`
	OccurredAt       time.Time       `bson:"occurredAt"`
}

// ImportedPostOutboxEventSnapshot is the immutable CAS identity used to
// repair one legacy Data-release PostDeleted payload without replacing its
// durable outbox envelope or sequence.
type ImportedPostOutboxEventSnapshot struct {
	EventID          string
	OutboxSequence   int64
	EventType        string
	AggregateType    string
	AggregateID      string
	AggregateVersion int64
	PayloadJSON      json.RawMessage
	OccurredAt       time.Time
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

// ApplyImportedPostRelease is the formal Content write command used by the
// Data release importer. It deliberately has no Redis dependency: Redis is an
// outbox relay transport, never an import write owner.
func ApplyImportedPostRelease(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	posts []PostDoc,
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
	if strings.TrimSpace(opts.ManifestDigest) == "" {
		return ImportedReleaseApplyResult{}, fmt.Errorf("content release import manifestDigest is required")
	}
	requestedAt = requestedAt.UTC().Truncate(time.Millisecond)
	if requestedAt.IsZero() {
		requestedAt = time.Now().UTC().Truncate(time.Millisecond)
	}

	postsColl := database.Collection("posts")
	outboxColl := database.Collection("content_outbox")
	sequenceColl := database.Collection("content_outbox_sequences")
	stateColl := database.Collection("data_release_state")
	receiptColl := database.Collection("data_release_stage_receipts")
	if err := ensureImportedReleaseIndexes(
		ctx,
		postsColl,
		outboxColl,
		stateColl,
		receiptColl,
	); err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	attemptID := releaseAttemptID(environment, opts, requestedAt)
	stageStarted := time.Now()
	if err := appendReleaseStageReceipt(ctx, receiptColl, releaseStageReceipt{
		Environment: environment, ReleaseID: opts.ReleaseID,
		ManifestDigest: opts.ManifestDigest, Stage: "prepared",
		AttemptID: attemptID, Status: "passed", RecordedAt: requestedAt,
		AttemptedCount: len(posts), SuccessCount: len(posts),
		Checkpoint: "canonical-input-validated",
	}); err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	latestPrepared, err := readLatestReleaseStageReceipt(
		ctx,
		receiptColl,
		environment,
		opts.ReleaseID,
		requestedAt,
	)
	if err != nil {
		return ImportedReleaseApplyResult{}, fmt.Errorf(
			"attest prepared Data release receipt: %w",
			err,
		)
	}
	if latestPrepared.AttemptID != attemptID || latestPrepared.Stage != "prepared" {
		return ImportedReleaseApplyResult{}, fmt.Errorf(
			"attest prepared Data release receipt: latest receipt identity mismatch",
		)
	}

	session, err := database.Client().StartSession()
	if err != nil {
		return ImportedReleaseApplyResult{}, fmt.Errorf("start content release import session: %w", err)
	}
	defer session.EndSession(ctx)

	var result ImportedReleaseApplyResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		resolved, activatedAt, replayed, previousReleaseID, previousManifestDigest, err := resolveImportedProjectionVersion(
			txCtx,
			stateColl,
			environment,
			opts,
			requestedAt,
		)
		if err != nil {
			return nil, err
		}
		if err := ValidateReplayRepairBinding(opts, replayed); err != nil {
			return nil, err
		}
		opts.ProjectionVersion = resolved
		deletedPosts, err := MissingImportedPostSnapshots(
			txCtx,
			postsColl,
			posts,
			opts,
			replayed,
			activatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("resolve missing imported Posts: %w", err)
		}
		var upserted int
		var removed int64
		if opts.RequireReplay {
			upserted, err = ValidateImportedPostsForReplay(
				txCtx,
				postsColl,
				posts,
				opts.ReplayPostBindings,
				opts,
			)
			if err != nil {
				return nil, err
			}
		} else {
			upserted, err = UpsertPostsWithOptions(
				txCtx,
				postsColl,
				posts,
				activatedAt,
				opts,
			)
			if err != nil {
				return nil, fmt.Errorf("upsert imported Posts: %w", err)
			}
			removed, err = ApplyMissingPostPolicy(
				txCtx,
				postsColl,
				posts,
				activatedAt,
				opts,
			)
			if err != nil {
				return nil, fmt.Errorf("apply imported Post removal policy: %w", err)
			}
		}
		var events []postports.OutboxEvent
		if opts.RequireReplay {
			events, err = BuildImportedPostDeletionLifecycleEvents(
				deletedPosts,
				opts,
				activatedAt,
			)
		} else {
			events, err = BuildImportedPostLifecycleEvents(
				posts,
				deletedPosts,
				opts,
				activatedAt,
			)
		}
		if err != nil {
			return nil, err
		}
		outboxResult, err := appendImportedPostOutbox(
			txCtx,
			outboxColl,
			sequenceColl,
			events,
			opts,
			replayed,
		)
		if err != nil {
			return nil, err
		}
		candidateResult := ImportedReleaseApplyResult{
			PostsUpserted:           upserted,
			PostsRemoved:            removed,
			PostDeletionEventsReady: len(deletedPosts),
			OutboxEventsReady:       len(events),
			OutboxEventsAppended:    outboxResult.Appended,
			OutboxEventsRepaired:    len(outboxResult.Repairs),
			OutboxRepairAudits:      outboxResult.Repairs,
			ProjectionVersion:       resolved,
			Replayed:                replayed,
			RepairReplay:            opts.RequireReplay,
			PreviousReleaseID:       previousReleaseID,
			PreviousManifestDigest:  previousManifestDigest,
		}
		if err := ValidateImportedReleaseApplyResult(
			candidateResult,
			len(posts),
		); err != nil {
			return nil, err
		}
		if err := ValidateExpectedOutboxRepairCount(opts, candidateResult); err != nil {
			return nil, err
		}
		if !opts.RequireReplay {
			for _, stage := range []struct {
				name       string
				checkpoint string
			}{
				{name: "imported", checkpoint: "posts-materialized"},
				{name: "projected", checkpoint: "lifecycle-outbox-appended"},
				{name: "verified", checkpoint: "counts-and-readback-validated"},
			} {
				if err := appendReleaseStageReceipt(txCtx, receiptColl, releaseStageReceipt{
					Environment: environment, ReleaseID: opts.ReleaseID,
					ManifestDigest: opts.ManifestDigest, Stage: stage.name,
					AttemptID: attemptID, Status: "passed", RecordedAt: requestedAt,
					DurationMs:     releaseStageDurationMs(stageStarted),
					AttemptedCount: len(posts), SuccessCount: upserted,
					Checkpoint: stage.checkpoint,
				}); err != nil {
					return nil, err
				}
			}
			if err := UpsertReleaseState(txCtx, stateColl, environment, opts, activatedAt, bson.M{
				"postsUpserted": upserted,
				"postsRemoved":  removed,
			}); err != nil {
				return nil, fmt.Errorf("activate imported Data release: %w", err)
			}
			if err := appendReleaseStageReceipt(txCtx, receiptColl, releaseStageReceipt{
				Environment: environment, ReleaseID: opts.ReleaseID,
				ManifestDigest: opts.ManifestDigest, Stage: "active",
				AttemptID: attemptID, Status: "passed", RecordedAt: activatedAt,
				DurationMs:     releaseStageDurationMs(stageStarted),
				AttemptedCount: len(posts), SuccessCount: upserted,
				Checkpoint: "active-pointer-committed",
			}); err != nil {
				return nil, err
			}
		}
		result = candidateResult
		return nil, nil
	})
	if err != nil {
		if receiptErr := appendReleaseStageReceipt(ctx, receiptColl, releaseStageReceipt{
			Environment: environment, ReleaseID: opts.ReleaseID,
			ManifestDigest: opts.ManifestDigest, Stage: "imported",
			AttemptID: attemptID, Status: "failed", RecordedAt: time.Now().UTC(),
			DurationMs:     releaseStageDurationMs(stageStarted),
			AttemptedCount: len(posts), SuccessCount: 0,
			Checkpoint:        "transaction-aborted",
			FirstTypedBlocker: releaseImportFailedBlocker,
		}); receiptErr != nil {
			return ImportedReleaseApplyResult{}, fmt.Errorf(
				"%w; persist failure receipt: %v",
				err,
				receiptErr,
			)
		}
		return ImportedReleaseApplyResult{}, err
	}
	return result, nil
}

// ValidateReplayRepairBinding prevents the repair rail from activating or
// replaying any release other than the exact active release.
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

// ValidateExpectedOutboxRepairCount executes before the transaction writes the
// release pointer, so a stale expectation aborts the payload CAS with the whole
// Mongo transaction.
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

// ValidateImportedReleaseApplyResult keeps activation behind one exact
// Manifest/Post/outbox closure. The active pointer is written only after this
// check, so any partial import leaves the previous verified release untouched.
func ValidateImportedReleaseApplyResult(
	result ImportedReleaseApplyResult,
	expectedPosts int,
) error {
	if expectedPosts < 0 {
		return fmt.Errorf("expected imported Post count must be non-negative")
	}
	if result.PostsUpserted != expectedPosts {
		return fmt.Errorf(
			"Manifest/import Post count mismatch: expected=%d upserted=%d",
			expectedPosts,
			result.PostsUpserted,
		)
	}
	if result.PostDeletionEventsReady < 0 ||
		result.OutboxEventsRepaired < 0 ||
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
	} else {
		if int64(result.PostDeletionEventsReady) != result.PostsRemoved {
			return fmt.Errorf(
				"Post deletion event/removal count mismatch: ready=%d removed=%d",
				result.PostDeletionEventsReady,
				result.PostsRemoved,
			)
		}
	}
	if !result.RepairReplay && result.OutboxEventsRepaired != 0 {
		return fmt.Errorf("non-repair release repaired existing outbox events")
	}
	expectedEvents := expectedPosts + result.PostDeletionEventsReady
	if result.RepairReplay {
		expectedEvents = result.PostDeletionEventsReady
	}
	if result.OutboxEventsReady != expectedEvents {
		return fmt.Errorf(
			"Manifest/outbox event count mismatch: expected=%d ready=%d",
			expectedEvents,
			result.OutboxEventsReady,
		)
	}
	if result.Replayed {
		if result.OutboxEventsAppended != 0 {
			return fmt.Errorf(
				"replayed release appended duplicate outbox events: %d",
				result.OutboxEventsAppended,
			)
		}
	} else if result.OutboxEventsAppended != result.OutboxEventsReady {
		return fmt.Errorf(
			"Manifest/outbox append count mismatch: ready=%d appended=%d",
			result.OutboxEventsReady,
			result.OutboxEventsAppended,
		)
	}
	return nil
}

func ensureImportedReleaseIndexes(
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
		{
			Keys:    bson.D{{Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("idx_content_outbox_sequence").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "aggregateType", Value: 1},
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: 1},
			},
			Options: options.Index().SetName("idx_content_outbox_aggregate_version").SetUnique(true),
		},
	}); err != nil {
		return fmt.Errorf("ensure imported Post outbox indexes: %w", err)
	}
	return ensureReleaseControlIndexes(ctx, state, receipts)
}

func resolveImportedProjectionVersion(
	ctx context.Context,
	state *mongo.Collection,
	environment string,
	opts ImportOptions,
	requestedAt time.Time,
) (int64, time.Time, bool, string, string, error) {
	var current importedReleaseState
	err := state.FindOne(ctx, bson.M{
		"environment": environment,
		"sourceOwner": opts.SourceOwner,
	}).Decode(&current)
	if err != nil && err != mongo.ErrNoDocuments {
		return 0, time.Time{}, false, "", "", fmt.Errorf("read active Data release: %w", err)
	}
	if err == nil && current.Status == "active" &&
		strings.TrimSpace(current.ActiveReleaseID) == opts.ReleaseID &&
		strings.TrimSpace(current.ManifestDigest) == opts.ManifestDigest &&
		current.ProjectionVersion > 0 {
		activatedAt := current.ActivatedAt.UTC()
		if activatedAt.IsZero() {
			activatedAt = requestedAt
		}
		return current.ProjectionVersion, activatedAt, true, "", "", nil
	}
	version := opts.ProjectionVersion
	if version <= 0 {
		version = requestedAt.UnixMilli()
	}
	if current.ProjectionVersion >= version {
		version = current.ProjectionVersion + 1
	}
	if version <= 0 {
		return 0, time.Time{}, false, "", "", fmt.Errorf("content release projectionVersion must be positive")
	}
	previousReleaseID := ""
	previousManifestDigest := ""
	if err == nil && current.Status == "active" {
		previousReleaseID = strings.TrimSpace(current.ActiveReleaseID)
		previousManifestDigest = strings.TrimSpace(current.ManifestDigest)
	}
	return version, requestedAt, false, previousReleaseID, previousManifestDigest, nil
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
		media := ImportedMediaFields(importedPostAssets(post))
		body := post.ArticleMarkdown
		summary := ProjectImportedArticleSummary(post.ArticleMarkdown)
		if post.ContentType == "image" {
			body = post.Body
			summary = post.Body
		}
		postID := RuntimePostID(post.ContentID, post.PostRef)
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

// BuildImportedPostDeletionLifecycleEvents is the repair-only projection. It
// deliberately excludes PostPublished so historical Post IDs and already
// consumed Search/Recommendation facts cannot be rewritten by an outbox fix.
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
) (importedPostOutboxApplyResult, error) {
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
			ID:               event.EventID,
			OutboxSequence:   firstSequence + int64(index),
			EventType:        event.EventType,
			AggregateType:    event.AggregateType,
			AggregateID:      event.AggregateID,
			AggregateVersion: event.AggregateVersion,
			PayloadJSON:      event.Payload,
			OccurredAt:       event.OccurredAt,
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
		PayloadJSON: append([]byte(nil), document.PayloadJSON...),
		OccurredAt:  document.OccurredAt,
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
		"occurredAt": existing.OccurredAt, "payloadJson": existing.PayloadJSON,
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

type legacyImportedPostDeletedPayload struct {
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
	legacyKeys := []string{"deletedAt", "postId", "releaseDigest", "releaseId", "sourceOwner"}
	intermediateKeys := []string{"authorId", "contentIdentity", "contentType", "deletedAt", "postId", "status"}
	switch {
	case slicesEqualStrings(gotKeys, legacyKeys):
		return validateLegacyImportedPostDeletedPayload(existing, expected, opts)
	case slicesEqualStrings(gotKeys, intermediateKeys):
		return validateIntermediateImportedPostDeletedPayload(existing, expected)
	default:
		return fmt.Errorf("GATE_BLOCK: PostDeleted payload keyset is not repairable")
	}
}

func validateLegacyImportedPostDeletedPayload(
	existing ImportedPostOutboxEventSnapshot,
	expected postports.OutboxEvent,
	opts ImportOptions,
) error {
	var keyset map[string]json.RawMessage
	if err := json.Unmarshal(existing.PayloadJSON, &keyset); err != nil {
		return fmt.Errorf("GATE_BLOCK: legacy PostDeleted payload is not JSON")
	}
	wantKeys := []string{"deletedAt", "postId", "releaseDigest", "releaseId", "sourceOwner"}
	gotKeys := make([]string, 0, len(keyset))
	for key := range keyset {
		gotKeys = append(gotKeys, key)
	}
	sort.Strings(gotKeys)
	if !slicesEqualStrings(gotKeys, wantKeys) {
		return fmt.Errorf("GATE_BLOCK: legacy PostDeleted payload keyset is not repairable")
	}
	var legacy legacyImportedPostDeletedPayload
	decoder := json.NewDecoder(bytes.NewReader(existing.PayloadJSON))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&legacy); err != nil {
		return fmt.Errorf("GATE_BLOCK: decode legacy PostDeleted payload: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return fmt.Errorf("GATE_BLOCK: legacy PostDeleted payload contains trailing JSON")
	}
	deletedAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(legacy.DeletedAt))
	if err != nil || legacy.PostID != expected.AggregateID ||
		legacy.ReleaseID != opts.ReleaseID ||
		legacy.ReleaseDigest != opts.ManifestDigest ||
		legacy.SourceOwner != opts.SourceOwner ||
		!deletedAt.Equal(expected.OccurredAt) {
		return fmt.Errorf("GATE_BLOCK: legacy PostDeleted payload binding drift")
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
