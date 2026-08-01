// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package api_integration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/infrastructure/accountclosure"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/mediaobjectfence"
)

func TestUserAccountClosedCleanupConvergesAndRejectsEventIDReuse(t *testing.T) {
	ctx := t.Context()
	db := requireMongoDB(t)
	event := accountClosureIntegrationEvent("acct-close-integration-event")
	subjects := event.SubjectIDs()
	ownedPostID := "acct-close-owned-post"
	keptPostID := "acct-close-kept-post"
	ownedCommentID := "acct-close-owned-comment"
	replyCommentID := "acct-close-reply-comment"
	keptCommentID := "acct-close-kept-comment"
	ownedReactionID := "acct-close-owned-reaction"
	ownedTargetReactionID := "acct-close-owned-target-reaction"
	keptReactionID := "acct-close-kept-reaction"
	activityDocumentID := "acct-close-activity-document"
	readFactID := "acct-close-read-fact"
	shareFactID := "acct-close-share-fact"
	keptShareFactID := "acct-close-share-fact-kept"
	mediaSessionID := "acct-close-media-session"
	mediaAssetID := "acct-close-media-asset"
	replayDatasetID := "acct-close-replay-dataset"
	unrelatedReplayDatasetID := "acct-close-unrelated-replay-dataset"
	t.Cleanup(func() {
		cleanupAccountClosureIntegrationData(
			context.Background(),
			db,
			event,
			[]string{ownedPostID, keptPostID},
			[]string{ownedCommentID, replyCommentID, keptCommentID},
			[]string{ownedReactionID, ownedTargetReactionID, keptReactionID},
		)
	})

	now := time.Now().UTC()
	mustInsertAccountClosureDocuments(t, db.Collection("posts"), []any{
		bson.M{
			"_id": ownedPostID, "authorId": event.Payload.PersonaIDs[0],
			"status": "published", "commentCount": int64(0), "likeCount": int64(0),
		},
		bson.M{
			"_id": keptPostID, "authorId": "acct-close-other-persona",
			"status": "published", "commentCount": int64(3), "likeCount": int64(2),
			"shareCount": int64(2),
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("comments"), []any{
		bson.M{
			"_id": ownedCommentID, "postId": keptPostID,
			"authorId": event.Payload.PersonaIDs[0], "status": "active",
		},
		bson.M{
			"_id": replyCommentID, "postId": keptPostID,
			"authorId": "acct-close-other-persona", "status": "active",
			"parentCommentId":  ownedCommentID,
			"replyToCommentId": ownedCommentID,
			"replyToUserId":    event.Payload.PersonaIDs[0],
			"mentions": bson.A{
				bson.M{
					"subjectType": "persona",
					"subjectId":   event.Payload.PersonaIDs[0],
					"displayName": "closed",
				},
				bson.M{
					"subjectType": "persona",
					"subjectId":   "acct-close-other-persona",
					"displayName": "kept",
				},
			},
		},
		bson.M{
			"_id": keptCommentID, "postId": keptPostID,
			"authorId": "acct-close-other-persona", "status": "active",
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("content_reaction_aggregates"), []any{
		bson.M{
			"_id": ownedReactionID, "targetKind": "post", "targetId": keptPostID,
			"actorId": event.Payload.PersonaIDs[0], "reaction": "like",
		},
		bson.M{
			"_id": ownedTargetReactionID, "targetKind": "post", "targetId": ownedPostID,
			"actorId": "acct-close-other-persona", "reaction": "like",
		},
		bson.M{
			"_id": keptReactionID, "targetKind": "post", "targetId": keptPostID,
			"actorId": "acct-close-other-persona", "reaction": "like",
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("rm_discovery_feed"), []any{
		bson.M{
			"_id": "acct-close-feed-owned", "postId": ownedPostID,
			"authorId": event.Payload.PersonaIDs[0],
		},
		bson.M{
			"_id": "acct-close-feed-kept", "postId": keptPostID,
			"authorId":     "acct-close-other-persona",
			"commentCount": int64(3), "likeCount": int64(2),
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("profile_interaction_activity_views"), []any{
		bson.M{
			"_id": activityDocumentID, "activityId": "acct-close-activity",
			"ownerPersonaId": event.Payload.PersonaIDs[0],
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("profile_interaction_read_facts"), []any{
		bson.M{
			"_id": readFactID, "activityId": "acct-close-activity",
			"ownerPersonaId": event.Payload.PersonaIDs[0],
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("outbound_share_facts"), []any{
		bson.M{
			"_id": shareFactID, "postId": keptPostID,
			"actorId": event.Payload.PersonaIDs[0],
		},
		bson.M{
			"_id": keptShareFactID, "postId": keptPostID,
			"actorId": "acct-close-other-persona",
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("rm_behavior_events"), []any{
		bson.M{
			"_id": bson.NewObjectID(), "userId": event.Payload.UserID,
			"sessionId": "acct-close-session", "contentId": keptPostID,
			"clientEventId": "acct-close-client-event",
			"action":        "click", "occurredAt": now.Format(time.RFC3339Nano), "createdAt": now,
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("entity_wishlist_events"), []any{
		bson.M{"_id": "acct-close-wishlist", "userId": event.Payload.UserID, "entityId": "entity-1"},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("rec_learning_events"), []any{
		bson.M{"_id": "acct-close-learning", "userId": event.Payload.UserID, "targetId": keptPostID},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("rec_training_samples"), []any{
		bson.M{
			"_id": "acct-close-training", "scenario": "content_feed",
			"userId": event.Payload.UserID, "targetId": keptPostID, "ts": now,
		},
		bson.M{
			"_id": "acct-close-training-kept", "scenario": "content_feed",
			"userId": "acct-close-other-account", "targetId": keptPostID, "ts": now,
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("rec_replay_samples"), []any{
		bson.M{
			"_id": "acct-close-replay", "datasetId": replayDatasetID,
			"userId": event.Payload.UserID, "targetId": keptPostID, "ts": now,
		},
		bson.M{
			"_id": "acct-close-replay-kept", "datasetId": replayDatasetID,
			"userId": "acct-close-other-account", "targetId": keptPostID, "ts": now,
		},
		bson.M{
			"_id": "acct-close-replay-unrelated", "datasetId": unrelatedReplayDatasetID,
			"userId": "acct-close-other-account", "targetId": keptPostID, "ts": now,
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("rec_replay_datasets"), []any{
		bson.M{
			"_id": replayDatasetID, "scenario": "content_feed",
			"privacyStatus": "active", "sampleCount": int32(2), "frozenAt": now,
		},
		bson.M{
			"_id": unrelatedReplayDatasetID, "scenario": "content_feed",
			"privacyStatus": "active", "sampleCount": int32(1), "frozenAt": now,
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("rm_recommend_feature"), []any{
		bson.M{"_id": "acct-close-feature", "userId": event.Payload.UserID},
		bson.M{
			"_id":    "acct-close-feature-kept",
			"userId": "acct-close-feature-viewer",
			"userFeatures": bson.M{
				"authorInteraction": bson.M{
					event.Payload.PersonaIDs[0]: int32(4),
					"acct-close-other-persona":  int32(2),
				},
			},
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("rm_search_intent"), []any{
		bson.M{
			"_id":       event.Payload.UserID,
			"userId":    event.Payload.UserID,
			"expiresAt": now.Add(time.Hour),
		},
		bson.M{
			"_id":              "acct-close-search-intent-kept",
			"userId":           "acct-close-feature-viewer",
			"engagedObjectIds": []string{ownedPostID, keptPostID},
			"expiresAt":        now.Add(time.Hour),
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("rm_viewer_object_intersection"), []any{
		bson.M{
			"_id":         "acct-close-other-viewer",
			"reasonsJson": `{"relationObjectId":"` + event.Payload.PersonaIDs[0] + `"}`,
		},
		bson.M{
			"_id":         "acct-close-kept-viewer",
			"reasonsJson": `{"relationObjectId":"` + event.Payload.PersonaIDs[0] + `-suffix"}`,
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("rm_intersection_watermark"), []any{
		bson.M{"_id": event.Payload.UserID, "wm": bson.M{"content": int64(1)}},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("persona_follow_projection"), []any{
		bson.M{
			"_id": "acct-close-follow", "sourcePersonaId": event.Payload.PersonaIDs[0],
			"targetPersonaId": "acct-close-other-persona",
			"eventId":         "acct-close-relationship-event",
			"pairId":          "acct-close-relationship-pair",
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("persona_relationship_projection_inbox"), []any{
		bson.M{
			"_id":       "acct-close-relationship-inbox",
			"eventId":   "acct-close-relationship-event",
			"pairId":    "acct-close-relationship-pair",
			"eventName": "PersonaFollowStateChanged",
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("media_upload_sessions"), []any{
		bson.M{"_id": mediaSessionID, "ownerId": event.Payload.PersonaIDs[0]},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("media_assets"), []any{
		bson.M{"_id": mediaAssetID, "ownerId": event.Payload.PersonaIDs[0]},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("media_original_access_facts"), []any{
		bson.M{"_id": "acct-close-media-audit", "viewerId": event.Payload.UserID},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("post_moderation_case_audit"), []any{
		bson.M{"_id": "acct-close-moderation-audit", "reviewerId": event.Payload.UserID},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("content_user_account_restrictions"), []any{
		bson.M{
			"_id": event.AccountID, "subjects": subjects,
			"restricted": true, "accountVersion": int64(1),
		},
	})
	mustInsertAccountClosureDocuments(t, db.Collection("content_user_account_restriction_inbox"), []any{
		bson.M{
			"_id": "acct-close-suspend-event", "accountId": event.AccountID,
			"accountVersion": int64(1),
		},
	})

	store, err := accountclosure.NewMongoStore(
		db,
		accountClosureIntegrationDigestor(t),
		accountClosureIntegrationObjectFences(t, db),
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	search := &accountClosureSearchForIntegration{}
	cache := &accountClosureCacheForIntegration{}
	media := &accountClosureMediaReclaimerForIntegration{}
	processor, err := accountclosure.NewProcessor(
		store,
		cache,
		search,
		media,
	)
	if err != nil {
		t.Fatal(err)
	}

	result, err := processor.Apply(ctx, event)
	if err != nil {
		t.Fatalf("apply UserAccountClosed: %v", err)
	}
	if result.Replayed {
		t.Fatal("first UserAccountClosed application was reported as replay")
	}
	if count, err := db.Collection("content_user_account_restrictions").CountDocuments(
		ctx,
		bson.M{"_id": event.AccountID},
	); err != nil || count != 0 {
		t.Fatalf("closed Content restriction state count=%d err=%v", count, err)
	}
	if count, err := db.Collection("content_user_account_restriction_inbox").CountDocuments(
		ctx,
		bson.M{"accountId": event.AccountID},
	); err != nil || count != 0 {
		t.Fatalf("closed Content restriction inbox count=%d err=%v", count, err)
	}
	restrictionProjection, err := accountclosure.NewAccountRestrictionProjection(
		db,
		store,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := restrictionProjection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	lateRestore := contentAccountRestrictionEvent(
		"acct-close-late-restore-event",
		"UserRestored",
		event.AccountID,
		event.Payload.PersonaIDs[0],
		event.AccountVersion+1,
		event.AccountVersion+1,
		event.OccurredAt.Add(time.Minute),
	)
	lateResult, err := restrictionProjection.Apply(ctx, lateRestore)
	if err != nil || !lateResult.Replayed || !lateResult.Stale ||
		!lateResult.Terminal || lateResult.Affected != 0 {
		t.Fatalf("late restore after closure result=%+v err=%v", lateResult, err)
	}
	delayedSuspend := contentAccountRestrictionEvent(
		"acct-close-delayed-suspend-event",
		"UserSuspended",
		event.AccountID,
		event.Payload.PersonaIDs[0],
		event.AccountVersion,
		event.AccountVersion,
		event.OccurredAt.Add(-time.Minute),
	)
	delayedResult, err := restrictionProjection.Apply(ctx, delayedSuspend)
	if err != nil || !delayedResult.Replayed || !delayedResult.Stale ||
		!delayedResult.Terminal || delayedResult.Affected != 0 {
		t.Fatalf("delayed suspend after closure result=%+v err=%v", delayedResult, err)
	}
	assertAccountClosureCount(
		t,
		db,
		"content_user_account_restrictions",
		bson.M{},
		0,
	)
	assertAccountClosureCount(
		t,
		db,
		"content_user_account_restriction_inbox",
		bson.M{},
		0,
	)
	var terminalWatermark bson.M
	if err := db.Collection("content_user_account_restriction_watermarks").FindOne(
		ctx,
		bson.M{"terminal": true, "accountVersion": event.AccountVersion},
	).Decode(&terminalWatermark); err != nil {
		t.Fatalf("read Content terminal restriction watermark: %v", err)
	}
	encodedWatermark, err := bson.MarshalExtJSON(terminalWatermark, false, false)
	if err != nil {
		t.Fatal(err)
	}
	for _, rawID := range []string{event.AccountID, event.Payload.UserID, event.Payload.PersonaIDs[0]} {
		if strings.Contains(string(encodedWatermark), rawID) {
			t.Fatalf("Content terminal watermark retained raw identity %q: %s", rawID, encodedWatermark)
		}
	}
	if got := cache.blockedSubjects(); len(got) != len(subjects) {
		t.Fatalf("closed-subject guard received %v, want %v", got, subjects)
	}
	if got := search.canonicalIDs(); len(got) != 1 ||
		got[0] != "content.post:"+ownedPostID {
		t.Fatalf("canonical search deletes=%v", got)
	}
	for _, key := range []string{
		"rec:session_signals:{acct-close-account}:acct-close-session",
		"rec:event_dedup:{acct-close-account}:acct-close-client-event",
		"rec:imp_score:acct-close-account:" + keptPostID,
		"ix:watermark:{acct-close-account}",
	} {
		if !slicesContainsString(cache.keys(), key) {
			t.Fatalf("personal cache cleanup missed %q: %v", key, cache.keys())
		}
	}

	assertAccountClosureCount(t, db, "posts", bson.M{"_id": ownedPostID}, 0)
	assertAccountClosureCount(t, db, "posts", bson.M{"_id": keptPostID}, 1)
	assertAccountClosureCount(t, db, "comments", bson.M{"_id": ownedCommentID}, 0)
	assertAccountClosureCount(t, db, "comments", bson.M{
		"_id": bson.M{"$in": []string{replyCommentID, keptCommentID}},
	}, 2)
	assertAccountClosureCount(t, db, "content_reaction_aggregates", bson.M{
		"_id": bson.M{"$in": []string{ownedReactionID, ownedTargetReactionID}},
	}, 0)
	assertAccountClosureCount(t, db, "content_reaction_aggregates", bson.M{"_id": keptReactionID}, 1)
	assertAccountClosureCount(t, db, "outbound_share_facts", bson.M{"_id": keptShareFactID}, 1)
	for _, assertion := range []struct {
		collection string
		filter     bson.M
	}{
		{"profile_interaction_activity_views", bson.M{"_id": activityDocumentID}},
		{"profile_interaction_read_facts", bson.M{"_id": readFactID}},
		{"outbound_share_facts", bson.M{"_id": shareFactID}},
		{"rm_behavior_events", bson.M{"userId": bson.M{"$in": subjects}}},
		{"entity_wishlist_events", bson.M{"userId": bson.M{"$in": subjects}}},
		{"rec_learning_events", bson.M{"userId": bson.M{"$in": subjects}}},
		{"rec_training_samples", bson.M{"userId": bson.M{"$in": subjects}}},
		{"rec_replay_samples", bson.M{"userId": bson.M{"$in": subjects}}},
		{"rm_recommend_feature", bson.M{"userId": bson.M{"$in": subjects}}},
		{"rm_search_intent", bson.M{"userId": bson.M{"$in": subjects}}},
		{"rm_viewer_object_intersection", bson.M{"_id": "acct-close-other-viewer"}},
		{"rm_intersection_watermark", bson.M{"_id": event.Payload.UserID}},
		{"persona_follow_projection", bson.M{"_id": "acct-close-follow"}},
		{"persona_relationship_projection_inbox", bson.M{"_id": "acct-close-relationship-inbox"}},
		{"media_upload_sessions", bson.M{"_id": mediaSessionID}},
		{"media_assets", bson.M{"_id": mediaAssetID}},
	} {
		assertAccountClosureCount(t, db, assertion.collection, assertion.filter, 0)
	}
	assertAccountClosureCount(
		t,
		db,
		"rm_search_intent",
		bson.M{
			"_id":              "acct-close-search-intent-kept",
			"engagedObjectIds": ownedPostID,
		},
		0,
	)
	assertAccountClosureCount(
		t,
		db,
		"rec_training_samples",
		bson.M{"_id": "acct-close-training-kept"},
		1,
	)
	assertAccountClosureCount(
		t,
		db,
		"rec_replay_samples",
		bson.M{"_id": "acct-close-replay-kept"},
		1,
	)
	var replayDataset struct {
		PrivacyStatus             string     `bson:"privacyStatus"`
		PrivacyInvalidatedAt      *time.Time `bson:"privacyInvalidatedAt"`
		PrivacyInvalidationReason string     `bson:"privacyInvalidationReason"`
	}
	if err := db.Collection("rec_replay_datasets").FindOne(
		ctx,
		bson.M{"_id": replayDatasetID},
	).Decode(&replayDataset); err != nil {
		t.Fatal(err)
	}
	if replayDataset.PrivacyStatus != "privacy_invalidated" ||
		replayDataset.PrivacyInvalidatedAt == nil ||
		replayDataset.PrivacyInvalidationReason != "account_closed" {
		t.Fatalf("affected replay dataset remained usable: %+v", replayDataset)
	}
	assertAccountClosureCount(
		t,
		db,
		"rec_replay_datasets",
		bson.M{
			"_id":           unrelatedReplayDatasetID,
			"privacyStatus": "active",
		},
		1,
	)
	assertAccountClosureCount(
		t,
		db,
		"rm_viewer_object_intersection",
		bson.M{"_id": "acct-close-kept-viewer"},
		1,
	)
	var keptFeature struct {
		UserFeatures struct {
			AuthorInteraction map[string]int `bson:"authorInteraction"`
		} `bson:"userFeatures"`
	}
	if err := db.Collection("rm_recommend_feature").FindOne(
		ctx,
		bson.M{"_id": "acct-close-feature-kept"},
	).Decode(&keptFeature); err != nil {
		t.Fatal(err)
	}
	if _, leaked := keptFeature.UserFeatures.AuthorInteraction[event.Payload.PersonaIDs[0]]; leaked {
		t.Fatalf("closed persona leaked in recommendation feature: %+v", keptFeature)
	}
	if keptFeature.UserFeatures.AuthorInteraction["acct-close-other-persona"] != 2 {
		t.Fatalf("unrelated recommendation affinity was changed: %+v", keptFeature)
	}
	var keptSearchIntent struct {
		EngagedObjectIDs []string `bson:"engagedObjectIds"`
	}
	if err := db.Collection("rm_search_intent").FindOne(
		ctx,
		bson.M{"_id": "acct-close-search-intent-kept"},
	).Decode(&keptSearchIntent); err != nil {
		t.Fatal(err)
	}
	if len(keptSearchIntent.EngagedObjectIDs) != 1 ||
		keptSearchIntent.EngagedObjectIDs[0] != keptPostID {
		t.Fatalf("search intent cleanup changed unrelated affinity: %+v", keptSearchIntent)
	}
	var retainedReply struct {
		ParentCommentID  string `bson:"parentCommentId"`
		ReplyToCommentID string `bson:"replyToCommentId"`
		ReplyToUserID    string `bson:"replyToUserId"`
		Mentions         []struct {
			SubjectID string `bson:"subjectId"`
		} `bson:"mentions"`
	}
	if err := db.Collection("comments").FindOne(
		ctx,
		bson.M{"_id": replyCommentID},
	).Decode(&retainedReply); err != nil {
		t.Fatal(err)
	}
	if retainedReply.ParentCommentID != "" ||
		retainedReply.ReplyToCommentID != "" ||
		retainedReply.ReplyToUserID != "" ||
		len(retainedReply.Mentions) != 1 ||
		retainedReply.Mentions[0].SubjectID != "acct-close-other-persona" {
		t.Fatalf("retained reply leaked closed identity: %+v", retainedReply)
	}

	var keptPost struct {
		CommentCount int64 `bson:"commentCount"`
		LikeCount    int64 `bson:"likeCount"`
		ShareCount   int64 `bson:"shareCount"`
	}
	if err := db.Collection("posts").FindOne(ctx, bson.M{"_id": keptPostID}).Decode(&keptPost); err != nil {
		t.Fatal(err)
	}
	if keptPost.CommentCount != 2 || keptPost.LikeCount != 1 || keptPost.ShareCount != 1 {
		t.Fatalf("kept Post counters=%+v, want comment=2 like=1 share=1", keptPost)
	}
	var tombstone struct {
		AuthorID string `bson:"authorId"`
		Reason   string `bson:"reason"`
	}
	if err := db.Collection("deleted_post_tombstones").FindOne(
		ctx,
		bson.M{"_id": ownedPostID},
	).Decode(&tombstone); err != nil {
		t.Fatal(err)
	}
	if tombstone.AuthorID != "closed_account" || tombstone.Reason != "account_closed" {
		t.Fatalf("unsafe tombstone=%+v", tombstone)
	}
	var anonymousAudit bson.M
	if err := db.Collection(accountclosure.ClosedSubjectCollection).FindOne(
		ctx,
		bson.M{"_id": event.Digest()},
	).Decode(&anonymousAudit); err != nil {
		t.Fatal(err)
	}
	auditJSON, err := bson.MarshalExtJSON(anonymousAudit, false, false)
	if err != nil {
		t.Fatal(err)
	}
	for _, subjectID := range subjects {
		if strings.Contains(string(auditJSON), subjectID) {
			t.Fatalf("closure audit leaked subject %q: %s", subjectID, auditJSON)
		}
	}

	cacheDeleteCount := len(cache.keys())
	result, err = processor.Apply(ctx, event)
	if err != nil || !result.Replayed {
		t.Fatalf("idempotent replay result=%+v err=%v", result, err)
	}
	if len(search.canonicalIDs()) != 1 {
		t.Fatalf("replay repeated search deletion: %v", search.canonicalIDs())
	}
	if len(cache.keys()) != cacheDeleteCount {
		t.Fatalf("replay repeated cache deletion: %v", cache.keys())
	}

	reused := event
	reused.Payload.PersonaIDs = []string{"acct-close-different-persona"}
	if _, err := processor.Apply(ctx, reused); err == nil ||
		!strings.Contains(err.Error(), "eventId was reused") {
		t.Fatalf("eventId reuse was not rejected: %v", err)
	}
	if len(cache.keys()) != cacheDeleteCount {
		t.Fatalf("eventId reuse caused cache side effects: %v", cache.keys())
	}
}

// spec_ref: GWT-004
func TestUserAccountClosedMediaArtifactCleanupWaitsForReclamation(
	t *testing.T,
) {
	ctx := t.Context()
	db := requireMongoDB(t)
	event := accountClosureIntegrationEvent("acct-close-media-artifact-work")
	const (
		ownedAssetID    = "acct-close-media-owned"
		sharedAssetID   = "acct-close-media-shared"
		sharedObjectKey = "media/objects/sha256/aa/bb/shared-source.jpg"
	)
	t.Cleanup(func() {
		cleanupAccountClosureIntegrationData(
			context.Background(),
			db,
			event,
			nil,
			nil,
			nil,
		)
		_, _ = db.Collection("media_assets").DeleteOne(
			context.Background(),
			bson.M{"_id": sharedAssetID},
		)
	})
	mustInsertAccountClosureDocuments(t, db.Collection("media_assets"), []any{
		bson.M{
			"_id":                          ownedAssetID,
			"ownerId":                      event.Payload.PersonaIDs[0],
			"sourceSessionId":              "acct-close-media-owned-session",
			"objectKey":                    sharedObjectKey,
			"imageNormalizedObjectKey":     fmt.Sprintf("media/processed/image/%s/v1/source.jpg", ownedAssetID),
			"imagePublicSliceKey":          fmt.Sprintf("media/image/s/asset/%s/v1/source.jpg", ownedAssetID),
			"videoPublicSliceKey":          fmt.Sprintf("media/video/s/asset/%s/v1/source.mp4", ownedAssetID),
			"coverPublicSliceKey":          fmt.Sprintf("media/video/s/asset/%s/v1/cover.jpg", ownedAssetID),
			"previewTrackManifestSliceKey": fmt.Sprintf("media/video/s/asset/%s/v1/preview/manifest.json", ownedAssetID),
		},
		bson.M{
			"_id":             sharedAssetID,
			"ownerId":         "acct-close-other-persona",
			"sourceSessionId": "acct-close-media-shared-session",
			"objectKey":       sharedObjectKey,
		},
	})

	store, err := accountclosure.NewMongoStore(
		db,
		accountClosureIntegrationDigestor(t),
		accountClosureIntegrationObjectFences(t, db),
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	reclaimer := &accountClosureMediaReclaimerForIntegration{
		failuresRemaining: 1,
	}
	processor, err := accountclosure.NewProcessor(
		store,
		&accountClosureCacheForIntegration{},
		&accountClosureSearchForIntegration{},
		reclaimer,
	)
	if err != nil {
		t.Fatal(err)
	}

	if _, err := processor.Apply(ctx, event); err == nil {
		t.Fatal("media artifact deletion failure must keep account cleanup pending")
	}
	assertAccountClosureCount(
		t,
		db,
		"media_assets",
		bson.M{"_id": ownedAssetID},
		0,
	)
	assertAccountClosureCount(
		t,
		db,
		accountclosure.MediaArtifactWorkCollection,
		bson.M{
			"eventId": event.EventID,
			"doneAt":  bson.M{"$exists": false},
		},
		1,
	)
	var incompleteInbox struct {
		CompletedAt *time.Time `bson:"completedAt"`
	}
	if err := db.Collection(accountclosure.InboxCollection).FindOne(
		ctx,
		bson.M{"_id": event.EventID},
	).Decode(&incompleteInbox); err != nil {
		t.Fatal(err)
	}
	if incompleteInbox.CompletedAt != nil {
		t.Fatal("media artifact failure incorrectly completed account cleanup")
	}

	result, err := processor.Apply(ctx, event)
	if err != nil {
		t.Fatalf("retry media artifact cleanup: %v", err)
	}
	if !result.Replayed {
		t.Fatal("media artifact retry must resume Mongo-applied cleanup")
	}
	assertAccountClosureCount(
		t,
		db,
		accountclosure.MediaArtifactWorkCollection,
		bson.M{
			"eventId": event.EventID,
			"doneAt":  bson.M{"$exists": false},
		},
		0,
	)
	calls := reclaimer.calls()
	if len(calls) != 1 {
		t.Fatalf("media artifact cleanup calls=%+v", calls)
	}
	if !slicesContainsString(
		calls[0].PublicPrefixes,
		"media/video/s/asset/"+ownedAssetID+"/",
	) || !slicesContainsString(
		calls[0].PrivatePrefixes,
		"media/processed/image/"+ownedAssetID+"/",
	) {
		t.Fatalf("media artifact paths were not scheduled: %+v", calls[0])
	}
	if slicesContainsString(calls[0].PrivateObjectKeys, sharedObjectKey) {
		t.Fatalf(
			"shared CAS object was incorrectly scheduled for deletion: %+v",
			calls[0],
		)
	}
}

// spec_ref: GWT-004
func TestMediaObjectDeletionFenceRejectsConcurrentReferenceUntilDeletionCompletes(
	t *testing.T,
) {
	ctx := t.Context()
	db := requireMongoDB(t)
	manager, err := mediaobjectfence.New(db)
	if err != nil {
		t.Fatal(err)
	}
	const (
		objectKey = "media/objects/sha256/cc/dd/fenced-source.jpg"
		workID    = "account-close-fenced-cas-work"
	)
	t.Cleanup(func() {
		_, _ = db.Collection(mediaobjectfence.CollectionName).DeleteOne(
			context.Background(),
			bson.M{"_id": objectKey},
		)
	})

	claimed, err := manager.ClaimUnreferencedDeletion(ctx, objectKey, workID)
	if err != nil || !claimed {
		t.Fatalf("claim unreferenced CAS deletion: claimed=%t err=%v", claimed, err)
	}
	if err := manager.AllowReference(ctx, objectKey); !errors.Is(
		err,
		mediaobjectfence.ErrDeletionInProgress,
	) {
		t.Fatalf("new CAS reference during deletion: err=%v", err)
	}
	if err := manager.MarkWorkDeleted(ctx, workID); err != nil {
		t.Fatalf("complete CAS deletion fence: %v", err)
	}
	if err := manager.AllowReference(ctx, objectKey); err != nil {
		t.Fatalf("new CAS reference after deletion completion: %v", err)
	}
}

func TestUserAccountClosedSearchFailureLeavesInboxPendingAndRecovers(t *testing.T) {
	ctx := t.Context()
	db := requireMongoDB(t)
	event := accountClosureIntegrationEvent("acct-close-search-recovery-event")
	event.AccountID = "acct-close-search-account"
	event.Payload.UserID = event.AccountID
	event.Payload.PersonaIDs = []string{"acct-close-search-persona"}
	postID := "acct-close-search-recovery-post"
	t.Cleanup(func() {
		cleanupAccountClosureIntegrationData(
			context.Background(),
			db,
			event,
			[]string{postID},
			nil,
			nil,
		)
	})
	mustInsertAccountClosureDocuments(t, db.Collection("posts"), []any{
		bson.M{"_id": postID, "authorId": event.Payload.PersonaIDs[0], "status": "published"},
	})

	store, err := accountclosure.NewMongoStore(
		db,
		accountClosureIntegrationDigestor(t),
		accountClosureIntegrationObjectFences(t, db),
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	search := &accountClosureSearchForIntegration{failuresRemaining: 1}
	processor, err := accountclosure.NewProcessor(
		store,
		&accountClosureCacheForIntegration{},
		search,
		&accountClosureMediaReclaimerForIntegration{},
	)
	if err != nil {
		t.Fatal(err)
	}

	if _, err := processor.Apply(ctx, event); err == nil {
		t.Fatal("search deletion failure must leave event incomplete")
	}
	assertAccountClosureCount(t, db, "posts", bson.M{"_id": postID}, 0)
	var inbox struct {
		MongoAppliedAt *time.Time `bson:"mongoAppliedAt"`
		CompletedAt    *time.Time `bson:"completedAt"`
	}
	if err := db.Collection(accountclosure.InboxCollection).FindOne(
		ctx,
		bson.M{"_id": event.EventID},
	).Decode(&inbox); err != nil {
		t.Fatal(err)
	}
	if inbox.MongoAppliedAt == nil || inbox.CompletedAt != nil {
		t.Fatalf("search failure inbox state=%+v", inbox)
	}
	assertAccountClosureCount(t, db, accountclosure.SearchWorkCollection, bson.M{
		"eventId": event.EventID,
		"doneAt":  bson.M{"$exists": false},
	}, 1)

	result, err := processor.Apply(ctx, event)
	if err != nil {
		t.Fatalf("recover search deletion: %v", err)
	}
	if !result.Replayed {
		t.Fatal("search recovery must resume the Mongo-applied inbox")
	}
	if err := db.Collection(accountclosure.InboxCollection).FindOne(
		ctx,
		bson.M{"_id": event.EventID},
	).Decode(&inbox); err != nil {
		t.Fatal(err)
	}
	if inbox.CompletedAt == nil {
		t.Fatal("recovered search deletion did not complete inbox")
	}
}

type accountClosureSearchForIntegration struct {
	mu                sync.Mutex
	failuresRemaining int
	deleted           []string
}

type accountClosureCacheForIntegration struct {
	mu      sync.Mutex
	deleted []string
	blocked []string
}

type accountClosureMediaReclaimerForIntegration struct {
	mu                sync.Mutex
	failuresRemaining int
	work              []accountclosure.MediaArtifactCleanupWork
}

func (reclaimer *accountClosureMediaReclaimerForIntegration) ReclaimMediaArtifacts(
	_ context.Context,
	publicSliceKeys []string,
	publicPrefixes []string,
	privateObjectKeys []string,
	privatePrefixes []string,
) error {
	reclaimer.mu.Lock()
	defer reclaimer.mu.Unlock()
	if reclaimer.failuresRemaining > 0 {
		reclaimer.failuresRemaining--
		return errors.New("integration media object store unavailable")
	}
	reclaimer.work = append(
		reclaimer.work,
		accountclosure.MediaArtifactCleanupWork{
			PublicSliceKeys:   append([]string(nil), publicSliceKeys...),
			PublicPrefixes:    append([]string(nil), publicPrefixes...),
			PrivateObjectKeys: append([]string(nil), privateObjectKeys...),
			PrivatePrefixes:   append([]string(nil), privatePrefixes...),
		},
	)
	return nil
}

func (reclaimer *accountClosureMediaReclaimerForIntegration) calls() []accountclosure.MediaArtifactCleanupWork {
	reclaimer.mu.Lock()
	defer reclaimer.mu.Unlock()
	return append([]accountclosure.MediaArtifactCleanupWork(nil), reclaimer.work...)
}

func (cache *accountClosureCacheForIntegration) BlockClosedSubjects(
	_ context.Context,
	subjectIDs []string,
) error {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	cache.blocked = append(cache.blocked, subjectIDs...)
	return nil
}

func (cache *accountClosureCacheForIntegration) DeletePersonalCacheKeys(
	_ context.Context,
	keys []string,
) error {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	cache.deleted = append(cache.deleted, keys...)
	return nil
}

func (cache *accountClosureCacheForIntegration) VerifyNoPersonalDataResidual(
	_ context.Context,
	_ []string,
	_ []string,
) error {
	return nil
}

func (cache *accountClosureCacheForIntegration) keys() []string {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	return append([]string(nil), cache.deleted...)
}

func (cache *accountClosureCacheForIntegration) blockedSubjects() []string {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	return append([]string(nil), cache.blocked...)
}

func slicesContainsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func (search *accountClosureSearchForIntegration) DeleteSearchDocument(
	_ context.Context,
	document accountclosure.SearchDocumentID,
) error {
	search.mu.Lock()
	defer search.mu.Unlock()
	if search.failuresRemaining > 0 {
		search.failuresRemaining--
		return errors.New("integration search unavailable")
	}
	search.deleted = append(search.deleted, document.CanonicalID())
	return nil
}

func (search *accountClosureSearchForIntegration) canonicalIDs() []string {
	search.mu.Lock()
	defer search.mu.Unlock()
	return append([]string(nil), search.deleted...)
}

func accountClosureIntegrationEvent(eventID string) accountclosure.UserAccountClosedEvent {
	occurredAt := time.Now().UTC().Truncate(time.Millisecond)
	return accountclosure.UserAccountClosedEvent{
		EventID:        eventID,
		EventName:      accountclosure.UserAccountClosedName,
		AccountID:      "acct-close-account",
		AccountVersion: 1,
		Payload: accountclosure.UserAccountClosedPayload{
			UserID:       "acct-close-account",
			PersonaIDs:   []string{"acct-close-persona"},
			AccountState: "closed",
			UpdatedAt:    occurredAt,
		},
		OccurredAt: occurredAt,
	}
}

func accountClosureIntegrationDigestor(
	t *testing.T,
) accountclosure.SubjectDigestor {
	t.Helper()
	digestor, err := accountclosure.NewHMACSubjectDigestor(
		"content-account-closure-integration-secret",
	)
	if err != nil {
		t.Fatal(err)
	}
	return digestor
}

func accountClosureIntegrationObjectFences(
	t *testing.T,
	db *mongo.Database,
) *mediaobjectfence.Manager {
	t.Helper()
	manager, err := mediaobjectfence.New(db)
	if err != nil {
		t.Fatal(err)
	}
	return manager
}

func mustInsertAccountClosureDocuments(
	t *testing.T,
	collection *mongo.Collection,
	documents []any,
) {
	t.Helper()
	if len(documents) == 0 {
		return
	}
	if _, err := collection.InsertMany(t.Context(), documents); err != nil {
		t.Fatal(err)
	}
}

// spec_ref: GWT-004
func TestAccountClosureDeadLetterMarkerRetainsSourceRecoveryState(
	t *testing.T,
) {
	ctx := t.Context()
	db := requireMongoDB(t)
	store, err := accountclosure.NewMongoStore(
		db,
		accountClosureIntegrationDigestor(t),
		accountClosureIntegrationObjectFences(t, db),
	)
	if err != nil {
		t.Fatal(err)
	}
	const (
		stream    = accountclosure.UserAccountEventStream
		messageID = "account-closure-dlq-recovery-marker"
	)
	t.Cleanup(func() {
		if clearErr := store.ClearFailure(
			context.Background(),
			stream,
			messageID,
		); clearErr != nil {
			t.Errorf("clear account-closure failure marker: %v", clearErr)
		}
	})

	attempts, err := store.RecordFailure(
		ctx,
		stream,
		messageID,
		"account-closure-dlq-recovery-event",
		errors.New("scripted terminal failure"),
	)
	if err != nil || attempts != 1 {
		t.Fatalf("record failure: attempts=%d err=%v", attempts, err)
	}
	held, err := store.IsDeadLettered(ctx, stream, messageID)
	if err != nil || held {
		t.Fatalf("new failure marker: held=%t err=%v", held, err)
	}
	if err := store.MarkDeadLettered(ctx, stream, messageID); err != nil {
		t.Fatalf("mark held DLQ source: %v", err)
	}
	held, err = store.IsDeadLettered(ctx, stream, messageID)
	if err != nil || !held {
		t.Fatalf("held DLQ source marker: held=%t err=%v", held, err)
	}
	if _, err := store.RecordFailure(
		ctx,
		stream,
		messageID,
		"account-closure-dlq-recovery-event",
		errors.New("late concurrent failure"),
	); err == nil {
		t.Fatal(
			"late failure must not overwrite terminal marker or restore retry TTL",
		)
	}
	eventDigest := sha256.Sum256(
		[]byte("account-closure-dlq-recovery-event"),
	)
	var persisted struct {
		SourceStream   string     `bson:"sourceStream"`
		SourceStreamID string     `bson:"sourceStreamId"`
		ExpireAt       *time.Time `bson:"expireAt"`
	}
	if err := db.Collection(accountclosure.FailureCollection).FindOne(
		ctx,
		bson.M{
			"eventDigest": hex.EncodeToString(eventDigest[:]),
		},
	).Decode(&persisted); err != nil {
		t.Fatalf("read held DLQ source marker: %v", err)
	}
	if persisted.ExpireAt != nil {
		t.Fatalf(
			"held DLQ source marker must not use retry TTL: expireAt=%s",
			persisted.ExpireAt,
		)
	}
	if persisted.SourceStream != stream ||
		persisted.SourceStreamID != messageID {
		t.Fatalf(
			"held DLQ marker lost source PEL reference: stream=%q id=%q",
			persisted.SourceStream,
			persisted.SourceStreamID,
		)
	}
	if err := store.ClearFailure(ctx, stream, messageID); err != nil {
		t.Fatalf("release held DLQ source: %v", err)
	}
	held, err = store.IsDeadLettered(ctx, stream, messageID)
	if err != nil || held {
		t.Fatalf("released DLQ source marker: held=%t err=%v", held, err)
	}
}

func assertAccountClosureCount(
	t *testing.T,
	db *mongo.Database,
	collection string,
	filter bson.M,
	want int64,
) {
	t.Helper()
	count, err := db.Collection(collection).CountDocuments(t.Context(), filter)
	if err != nil {
		t.Fatal(err)
	}
	if count != want {
		t.Fatalf("%s count=%d, want %d filter=%v", collection, count, want, filter)
	}
}

func cleanupAccountClosureIntegrationData(
	ctx context.Context,
	db *mongo.Database,
	event accountclosure.UserAccountClosedEvent,
	postIDs []string,
	commentIDs []string,
	reactionIDs []string,
) {
	subjects := event.SubjectIDs()
	cleanups := []struct {
		collection string
		filter     bson.M
	}{
		{"posts", bson.M{"_id": bson.M{"$in": postIDs}}},
		{"comments", bson.M{"_id": bson.M{"$in": commentIDs}}},
		{"content_reaction_aggregates", bson.M{"_id": bson.M{"$in": reactionIDs}}},
		{"rm_discovery_feed", bson.M{"postId": bson.M{"$in": postIDs}}},
		{"profile_interaction_activity_views", bson.M{"ownerPersonaId": bson.M{"$in": subjects}}},
		{"profile_interaction_read_facts", bson.M{"ownerPersonaId": bson.M{"$in": subjects}}},
		{"outbound_share_facts", bson.M{"actorId": bson.M{"$in": subjects}}},
		{"outbound_share_facts", bson.M{"postId": bson.M{"$in": postIDs}}},
		{"rm_behavior_events", bson.M{"userId": bson.M{"$in": subjects}}},
		{"entity_wishlist_events", bson.M{"userId": bson.M{"$in": subjects}}},
		{"rec_learning_events", bson.M{"userId": bson.M{"$in": subjects}}},
		{"rec_training_samples", bson.M{"_id": bson.M{"$regex": "^acct-close-"}}},
		{"rec_replay_samples", bson.M{"_id": bson.M{"$regex": "^acct-close-"}}},
		{"rec_replay_datasets", bson.M{"_id": bson.M{"$regex": "^acct-close-"}}},
		{"rm_recommend_feature", bson.M{"userId": bson.M{"$in": subjects}}},
		{"rm_recommend_feature", bson.M{"_id": "acct-close-feature-kept"}},
		{"rm_viewer_object_intersection", bson.M{"_id": "acct-close-other-viewer"}},
		{"rm_viewer_object_intersection", bson.M{"_id": "acct-close-kept-viewer"}},
		{"rm_intersection_watermark", bson.M{"_id": bson.M{"$in": subjects}}},
		{"persona_follow_projection", bson.M{"sourcePersonaId": bson.M{"$in": subjects}}},
		{"persona_relationship_projection_inbox", bson.M{"_id": "acct-close-relationship-inbox"}},
		{"media_upload_sessions", bson.M{"ownerId": bson.M{"$in": subjects}}},
		{"media_assets", bson.M{"ownerId": bson.M{"$in": subjects}}},
		{"media_original_access_facts", bson.M{"_id": "acct-close-media-audit"}},
		{"post_moderation_case_audit", bson.M{"_id": "acct-close-moderation-audit"}},
		{"deleted_post_tombstones", bson.M{"_id": bson.M{"$in": postIDs}}},
		{accountclosure.InboxCollection, bson.M{"_id": event.EventID}},
		{accountclosure.FailureCollection, bson.M{"eventDigest": event.EventID}},
		{accountclosure.SearchWorkCollection, bson.M{"eventId": event.EventID}},
		{accountclosure.MediaArtifactWorkCollection, bson.M{"eventId": event.EventID}},
		{accountclosure.ClosedSubjectCollection, bson.M{"_id": event.Digest()}},
		{accountclosure.ClosedSubjectTombstoneCollection, bson.M{}},
		{"content_user_account_restrictions", bson.M{"_id": event.AccountID}},
		{"content_user_account_restriction_inbox", bson.M{"accountId": event.AccountID}},
		{"content_user_account_restriction_watermarks", bson.M{}},
	}
	for _, cleanup := range cleanups {
		_, _ = db.Collection(cleanup.collection).DeleteMany(ctx, cleanup.filter)
	}
}
