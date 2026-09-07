package releaseimport

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// ValidateImportedPostsForReplay proves that the exact active release Posts
// are already materialized. The repair rail is therefore read-only for Post
// and release-state documents and can write only the bounded outbox payload
// CAS inside the surrounding transaction.
func ValidateImportedPostsForReplay(
	ctx context.Context,
	posts *mongo.Collection,
	desired []PostDoc,
	bindings []ImportedPostBinding,
	opts ImportOptions,
) (int, error) {
	if posts == nil {
		return 0, fmt.Errorf("GATE_BLOCK: imported Post replay collection is unavailable")
	}
	if err := ValidateImportedPostReplayBindings(desired, bindings); err != nil {
		return 0, err
	}
	desiredByReportRef := make(map[string]PostDoc, len(desired))
	for _, post := range desired {
		reportRef, err := CanonicalImportReportPostRef(post.PostRef)
		if err != nil {
			return 0, fmt.Errorf("GATE_BLOCK: %w", err)
		}
		desiredByReportRef[reportRef] = post
	}
	for _, binding := range bindings {
		post := desiredByReportRef[binding.PostRef]
		filter := bson.M{
			"_id": binding.PostID, "postId": binding.PostID,
			"postRef": post.PostRef, "contentId": binding.ContentID,
			"contentVersion": binding.ContentVersion,
			"contentType":    binding.ContentType, "authorId": binding.AuthorID,
			"admission.usageScope": binding.UsageScope,
			"sourceOwner":          opts.SourceOwner, "releaseId": opts.ReleaseID,
			"manifestDigest": opts.ManifestDigest, "version": opts.ProjectionVersion,
			"lifecycleStatus": "active",
		}
		if err := posts.FindOne(
			ctx,
			filter,
			options.FindOne().SetProjection(bson.M{"_id": 1}),
		).Err(); err != nil {
			if err == mongo.ErrNoDocuments {
				return 0, fmt.Errorf(
					"GATE_BLOCK: active release Post %q differs from source import binding",
					binding.PostRef,
				)
			}
			return 0, fmt.Errorf(
				"read active release Post %q for replay: %w",
				binding.PostRef,
				err,
			)
		}
	}
	count, err := posts.CountDocuments(ctx, bson.M{
		"sourceOwner": opts.SourceOwner, "releaseId": opts.ReleaseID,
		"manifestDigest": opts.ManifestDigest, "version": opts.ProjectionVersion,
		"lifecycleStatus": "active",
	})
	if err != nil {
		return 0, fmt.Errorf("read active release Post replay closure: %w", err)
	}
	if count != int64(len(bindings)) {
		return 0, fmt.Errorf(
			"GATE_BLOCK: active release Post closure mismatch: bound=%d active=%d",
			len(bindings), count,
		)
	}
	return len(bindings), nil
}

// ValidateImportedPostReplayBindings proves that a source import receipt
// describes exactly today's immutable desired Post set. Runtime identity is
// always derived from admitted contentId; producer object paths are audit refs.
func ValidateImportedPostReplayBindings(
	desired []PostDoc,
	bindings []ImportedPostBinding,
) error {
	if len(bindings) != len(desired) {
		return fmt.Errorf(
			"GATE_BLOCK: replay Post binding count mismatch: desired=%d bound=%d",
			len(desired), len(bindings),
		)
	}
	desiredByRef := make(map[string]PostDoc, len(desired))
	for _, post := range desired {
		reportRef, err := CanonicalImportReportPostRef(post.PostRef)
		if err != nil {
			return fmt.Errorf("GATE_BLOCK: %w", err)
		}
		if _, exists := desiredByRef[reportRef]; exists {
			return fmt.Errorf("GATE_BLOCK: duplicate desired replay postRef %q", reportRef)
		}
		desiredByRef[reportRef] = post
	}
	seenRefs := make(map[string]struct{}, len(bindings))
	seenIDs := make(map[string]struct{}, len(bindings))
	for _, binding := range bindings {
		post, exists := desiredByRef[strings.TrimSpace(binding.PostRef)]
		if !exists {
			return fmt.Errorf("GATE_BLOCK: replay Post binding %q is not desired", binding.PostRef)
		}
		if _, duplicate := seenRefs[binding.PostRef]; duplicate {
			return fmt.Errorf("GATE_BLOCK: duplicate replay postRef %q", binding.PostRef)
		}
		if _, duplicate := seenIDs[binding.PostID]; duplicate {
			return fmt.Errorf("GATE_BLOCK: duplicate replay postId %q", binding.PostID)
		}
		currentID := RuntimePostID(post.ContentID)
		if strings.TrimSpace(binding.PostID) == "" || binding.PostID != currentID ||
			binding.ContentID != post.ContentID ||
			binding.ContentVersion != post.ContentVersion ||
			binding.UsageScope != post.Admission.UsageScope ||
			binding.ContentType != post.ContentType ||
			binding.AuthorID != post.AuthorID {
			return fmt.Errorf(
				"GATE_BLOCK: replay Post binding %q differs from immutable desired input",
				binding.PostRef,
			)
		}
		seenRefs[binding.PostRef] = struct{}{}
		seenIDs[binding.PostID] = struct{}{}
	}
	return nil
}

var importedLifecycleEventIDPattern = regexp.MustCompile(`^data-release:[0-9]+:.+:.+:Post(?:Published|Deleted)$`)

// ImportedReleaseConsistencyError is the typed fail-closed result for an exact
// release replay whose authoritative Post/outbox closure is missing or drifted.
type ImportedReleaseConsistencyError struct {
	ReleaseID      string
	ManifestDigest string
	Fact           string
	Cause          error
}

func (err *ImportedReleaseConsistencyError) Error() string {
	if err == nil {
		return "Data release replay consistency failure"
	}
	message := fmt.Sprintf(
		"GATE_BLOCK Data release replay consistency failure: releaseId=%q manifestDigest=%q fact=%q",
		err.ReleaseID,
		err.ManifestDigest,
		err.Fact,
	)
	if err.Cause != nil {
		return message + ": " + err.Cause.Error()
	}
	return message
}

func (err *ImportedReleaseConsistencyError) Unwrap() error {
	if err == nil {
		return nil
	}
	return err.Cause
}

func newImportedReleaseConsistencyError(opts ImportOptions, fact string, cause error) error {
	return &ImportedReleaseConsistencyError{
		ReleaseID:      strings.TrimSpace(opts.ReleaseID),
		ManifestDigest: strings.TrimSpace(opts.ManifestDigest),
		Fact:           fact,
		Cause:          cause,
	}
}

// ValidateImportedReleaseReplayClosure performs the ordinary replay proof. It
// is strictly read-only and validates the complete authoritative active/tombstone
// Post set and every lifecycle outbox envelope/payload for this source version.
func ValidateImportedReleaseReplayClosure(
	ctx context.Context,
	posts *mongo.Collection,
	outbox *mongo.Collection,
	desired []PostDoc,
	opts ImportOptions,
	activatedAt time.Time,
) (ImportedReleaseApplyResult, error) {
	if posts == nil || outbox == nil {
		return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(
			opts,
			"storage",
			errors.New("authoritative replay collections are unavailable"),
		)
	}
	seenPostIDs := make(map[string]struct{}, len(desired))
	for _, post := range desired {
		postID := RuntimePostID(post.ContentID)
		if postID == "" {
			return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(
				opts, "active_posts", errors.New("desired Post has no stable contentId"),
			)
		}
		if _, duplicate := seenPostIDs[postID]; duplicate {
			return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(
				opts, "active_posts", fmt.Errorf("duplicate stable postId %q", postID),
			)
		}
		seenPostIDs[postID] = struct{}{}
		filter := bson.M{
			"_id":             postID,
			"postId":          postID,
			"postRef":         post.PostRef,
			"contentId":       post.ContentID,
			"contentVersion":  post.ContentVersion,
			"releaseId":       opts.ReleaseID,
			"manifestDigest":  opts.ManifestDigest,
			"version":         opts.ProjectionVersion,
			"sourceHash":      sourceHash(post),
			"sourceOwner":     opts.SourceOwner,
			"lifecycleStatus": "active",
		}
		if err := posts.FindOne(ctx, filter, options.FindOne().SetProjection(bson.M{"_id": 1})).Err(); err != nil {
			return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(
				opts,
				"post_source_hash:"+postID,
				err,
			)
		}
	}
	activeCount, err := posts.CountDocuments(ctx, bson.M{
		"sourceOwner":     opts.SourceOwner,
		"releaseId":       opts.ReleaseID,
		"manifestDigest":  opts.ManifestDigest,
		"version":         opts.ProjectionVersion,
		"lifecycleStatus": "active",
	})
	if err != nil {
		return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(opts, "active_posts", err)
	}
	if activeCount != int64(len(desired)) {
		return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(
			opts,
			"active_posts",
			fmt.Errorf("active Post closure mismatch: expected=%d actual=%d", len(desired), activeCount),
		)
	}

	deletedPosts, err := MissingImportedPostSnapshots(
		ctx,
		posts,
		desired,
		opts,
		true,
		activatedAt,
	)
	if err != nil {
		return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(opts, "tombstone_posts", err)
	}
	if missingPolicyEnabled(opts) && opts.DeletePolicy != "none" {
		extraCount, err := posts.CountDocuments(ctx, bson.M{
			"sourceOwner": opts.SourceOwner,
			"_id":         bson.M{"$nin": desiredRuntimePostIDs(desired)},
		})
		if err != nil {
			return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(opts, "tombstone_posts", err)
		}
		wantExtras := int64(len(deletedPosts))
		if opts.DeletePolicy == "hard-delete" {
			wantExtras = 0
		}
		if extraCount != wantExtras {
			return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(
				opts,
				"tombstone_posts",
				fmt.Errorf("post tombstone closure mismatch: expected=%d actual=%d", wantExtras, extraCount),
			)
		}
	}
	expected, err := BuildImportedPostLifecycleEvents(desired, deletedPosts, opts, activatedAt)
	if err != nil {
		return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(opts, "lifecycle_expected", err)
	}
	existing, err := loadImportedPostLifecycleReplayEvents(ctx, outbox, opts)
	if err != nil {
		return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(opts, "lifecycle_outbox", err)
	}
	if err := ValidateImportedPostLifecycleReplayClosure(existing, expected, opts); err != nil {
		return ImportedReleaseApplyResult{}, newImportedReleaseConsistencyError(opts, "lifecycle_outbox", err)
	}
	return ImportedReleaseApplyResult{
		PostsUpserted:           len(desired),
		PostDeletionEventsReady: len(deletedPosts),
		OutboxEventsReady:       len(expected),
		ProjectionVersion:       opts.ProjectionVersion,
		Replayed:                true,
	}, nil
}

func loadImportedPostLifecycleReplayEvents(
	ctx context.Context,
	outbox *mongo.Collection,
	opts ImportOptions,
) ([]ImportedPostOutboxEventSnapshot, error) {
	prefix := fmt.Sprintf("data-release:%d:%s:", opts.ProjectionVersion, opts.ReleaseID)
	cursor, err := outbox.Find(ctx, bson.M{
		"_id": bson.M{"$regex": "^" + regexp.QuoteMeta(prefix)},
	}, options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}))
	if err != nil {
		return nil, fmt.Errorf("load replay lifecycle outbox closure: %w", err)
	}
	defer cursor.Close(ctx)
	result := make([]ImportedPostOutboxEventSnapshot, 0)
	for cursor.Next(ctx) {
		var document importedOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode replay lifecycle outbox closure: %w", err)
		}
		result = append(result, importedPostOutboxEventSnapshot(document))
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("scan replay lifecycle outbox closure: %w", err)
	}
	return result, nil
}

// ValidateImportedPostLifecycleReplayClosure reuses the immutable snapshot shape
// also used by the repair rail, but never invokes its mutation CAS.
func ValidateImportedPostLifecycleReplayClosure(
	existing []ImportedPostOutboxEventSnapshot,
	expected []postports.OutboxEvent,
	opts ImportOptions,
) error {
	want := make(map[string]postports.OutboxEvent, len(expected))
	for _, event := range expected {
		if _, duplicate := want[event.EventID]; duplicate {
			return fmt.Errorf("duplicate expected lifecycle event %q", event.EventID)
		}
		want[event.EventID] = event
	}
	seen := make(map[string]struct{}, len(existing))
	for _, current := range existing {
		if !importedLifecycleEventIDPattern.MatchString(current.EventID) {
			return fmt.Errorf("lifecycle event id %q is malformed", current.EventID)
		}
		expectedEvent, ok := want[current.EventID]
		if !ok {
			return fmt.Errorf("unexpected lifecycle event %q", current.EventID)
		}
		if _, duplicate := seen[current.EventID]; duplicate {
			return fmt.Errorf("duplicate lifecycle event %q", current.EventID)
		}
		if current.OutboxSequence <= 0 ||
			current.EventType != expectedEvent.EventType ||
			current.AggregateType != expectedEvent.AggregateType ||
			current.AggregateID != expectedEvent.AggregateID ||
			current.AggregateVersion != expectedEvent.AggregateVersion ||
			!current.OccurredAt.Equal(expectedEvent.OccurredAt) ||
			!bytes.Equal(current.PayloadJSON, expectedEvent.Payload) {
			return fmt.Errorf("lifecycle event %q envelope or payload drift", current.EventID)
		}
		seen[current.EventID] = struct{}{}
	}
	if len(seen) != len(want) {
		for eventID := range want {
			if _, ok := seen[eventID]; !ok {
				return fmt.Errorf("lifecycle event %q is missing", eventID)
			}
		}
	}
	return nil
}
