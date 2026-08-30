package releaseimport

import (
	"context"
	"fmt"
	"strings"

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
