// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package api_integration

import (
	"errors"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	accountrestriction "quwoquan_service/runtime/accountrestriction"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	accountclosureapp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/application"
	"quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/infrastructure/accountclosure"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

func TestContentAccountRestrictionProjectionIsReversibleMonotonicAndHidesPublicReads(
	t *testing.T,
) {
	db := requireMongoDB(t)
	ctx := t.Context()
	const (
		accountID   = "account_content_restriction_it"
		personaID   = "persona_content_restriction_it"
		postID      = "post_content_restriction_it"
		terminalID  = "post_content_restriction_terminal_it"
		commentID   = "comment_content_restriction_it"
		unrelatedID = "post_content_restriction_unrelated_it"
	)
	eventIDs := []string{
		"event_content_suspend",
		"event_content_suspend_conflict",
		"event_content_restore",
		"event_content_stale",
	}
	cleanup := func() {
		_, _ = db.Collection("posts").DeleteMany(ctx, bson.M{"_id": bson.M{"$in": []string{
			postID, terminalID, unrelatedID,
		}}})
		_, _ = db.Collection("comments").DeleteMany(ctx, bson.M{"_id": commentID})
		_, _ = db.Collection("rm_discovery_feed").DeleteMany(ctx, bson.M{"postId": postID})
		_, _ = db.Collection("content_user_account_restrictions").DeleteMany(ctx, bson.M{})
		_, _ = db.Collection("content_user_account_restriction_inbox").DeleteMany(ctx, bson.M{"_id": bson.M{"$in": eventIDs}})
		_, _ = db.Collection("content_user_account_restriction_watermarks").DeleteMany(ctx, bson.M{})
	}
	cleanup()
	t.Cleanup(cleanup)

	baseTime := time.Date(2026, 7, 29, 5, 0, 0, 0, time.UTC)
	if _, err := db.Collection("posts").InsertMany(ctx, []any{
		bson.M{
			"_id": postID, "authorId": personaID,
			"status": "published", "visibility": "public",
			"moderationStatus": "approved", "contentType": "article",
			"createdAt": baseTime, "publishedAt": baseTime,
		},
		bson.M{
			"_id": terminalID, "authorId": personaID,
			"status": "deleted", "visibility": "public",
			"moderationStatus": "approved", "contentType": "article",
			"createdAt": baseTime, "publishedAt": baseTime,
		},
		bson.M{
			"_id": unrelatedID, "authorId": "persona_content_unrelated_it",
			"status": "published", "visibility": "public",
			"moderationStatus": "approved", "contentType": "article",
			"createdAt": baseTime, "publishedAt": baseTime,
		},
	}); err != nil {
		t.Fatalf("seed restriction posts: %v", err)
	}
	if _, err := db.Collection("comments").InsertOne(ctx, bson.M{
		"_id": commentID, "version": int64(1), "postId": unrelatedID,
		"authorId": personaID, "parentCommentId": "", "status": "active",
		"content": "temporarily hidden", "createdAt": baseTime, "updatedAt": baseTime,
	}); err != nil {
		t.Fatalf("seed restriction comment: %v", err)
	}
	if _, err := db.Collection("rm_discovery_feed").InsertOne(ctx, bson.M{
		"postId": postID, "authorId": personaID, "status": "published",
		"visibility": "public", "contentType": "article", "publishedAt": baseTime,
	}); err != nil {
		t.Fatalf("seed restriction recommendation candidate: %v", err)
	}

	closureStore, err := accountclosure.NewMongoStore(
		db,
		accountClosureIntegrationDigestor(t),
		accountClosureIntegrationObjectFences(t, db),
	)
	if err != nil {
		t.Fatalf("assemble content account closure authority: %v", err)
	}
	projection, err := accountclosure.NewAccountRestrictionProjection(
		db,
		closureStore,
	)
	if err != nil {
		t.Fatalf("assemble content account restriction projection: %v", err)
	}
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure content account restriction indexes: %v", err)
	}

	suspension := contentAccountRestrictionEvent(
		"event_content_suspend",
		accountrestriction.UserSuspendedEventName,
		accountID,
		personaID,
		5,
		9,
		baseTime,
	)
	result, err := projection.Apply(ctx, suspension)
	if err != nil || result.Replayed || result.Stale || result.Affected != 4 {
		t.Fatalf("apply content suspension: result=%+v err=%v", result, err)
	}
	replay, err := projection.Apply(ctx, suspension)
	if err != nil || !replay.Replayed || replay.Stale || replay.Affected != 4 {
		t.Fatalf("replay content suspension: result=%+v err=%v", replay, err)
	}
	conflict := suspension
	conflict.EventID = "event_content_suspend_conflict"
	conflict.DecisionRef = "decision_content_conflict"
	if _, err := projection.Apply(ctx, conflict); !errors.Is(
		err,
		accountclosureapp.ErrUserAccountRestrictionProjectionConflict,
	) {
		t.Fatalf("same-version conflict error=%v", err)
	}

	postReader := persistence.NewMongoPostQueryReader(db.Collection("posts"))
	if _, found, err := postReader.FindPublishedFeedPost(ctx, postports.NewPostID(postID)); err != nil || found {
		t.Fatalf("restricted Post remained in public feed: found=%v err=%v", found, err)
	}
	if _, found, err := postReader.FindPostDetail(ctx, postports.NewPostID(postID)); err != nil || found {
		t.Fatalf("restricted Post remained in public detail: found=%v err=%v", found, err)
	}
	commentReader := persistence.NewMongoCommentDataAdapter(db)
	page, err := commentReader.ListByPost(ctx, unrelatedID, commentports.PageRequest{Limit: 20})
	if err != nil || len(page.Items) != 0 || page.Total != 0 {
		t.Fatalf("restricted Comment remained public: page=%+v err=%v", page, err)
	}
	assertAccountRestrictedProjectionField(t, db, "rm_discovery_feed", bson.M{"postId": postID}, true)

	restoration := contentAccountRestrictionEvent(
		"event_content_restore",
		accountrestriction.UserRestoredEventName,
		accountID,
		personaID,
		6,
		10,
		baseTime.Add(time.Minute),
	)
	result, err = projection.Apply(ctx, restoration)
	if err != nil || result.Replayed || result.Stale || result.Affected != 4 {
		t.Fatalf("apply content restoration: result=%+v err=%v", result, err)
	}
	if _, found, err := postReader.FindPublishedFeedPost(ctx, postports.NewPostID(postID)); err != nil || !found {
		t.Fatalf("restored Post did not return to public feed: found=%v err=%v", found, err)
	}
	page, err = commentReader.ListByPost(ctx, unrelatedID, commentports.PageRequest{Limit: 20})
	if err != nil || len(page.Items) != 1 || page.Items[0].ID != commentID || page.Total != 1 {
		t.Fatalf("restored Comment did not return: page=%+v err=%v", page, err)
	}
	var terminal struct {
		Status            string `bson:"status"`
		AccountRestricted bool   `bson:"accountRestricted"`
	}
	if err := db.Collection("posts").FindOne(ctx, bson.M{"_id": terminalID}).Decode(&terminal); err != nil {
		t.Fatalf("read terminal Post after restore: %v", err)
	}
	if terminal.Status != "deleted" || terminal.AccountRestricted {
		t.Fatalf("restore revived terminal Post: %+v", terminal)
	}

	stale := contentAccountRestrictionEvent(
		"event_content_stale",
		accountrestriction.UserSuspendedEventName,
		accountID,
		personaID,
		4,
		8,
		baseTime.Add(-time.Minute),
	)
	result, err = projection.Apply(ctx, stale)
	if err != nil || !result.Replayed || !result.Stale || result.Affected != 0 {
		t.Fatalf("apply stale content restriction: result=%+v err=%v", result, err)
	}
	if _, found, err := postReader.FindPublishedFeedPost(ctx, postports.NewPostID(postID)); err != nil || !found {
		t.Fatalf("stale suspension reverted restored visibility: found=%v err=%v", found, err)
	}
	assertAccountRestrictedProjectionField(t, db, "rm_discovery_feed", bson.M{"postId": postID}, false)
}

func contentAccountRestrictionEvent(
	eventID string,
	eventName string,
	accountID string,
	personaID string,
	accountVersion int64,
	authEpoch int64,
	occurredAt time.Time,
) accountrestriction.Event {
	state := "suspended"
	if eventName == accountrestriction.UserRestoredEventName {
		state = "active"
	}
	return accountrestriction.Event{
		EventID: eventID, EventName: eventName, AccountID: accountID,
		AccountVersion: accountVersion, UserID: accountID,
		PersonaIDs: []string{personaID}, AccountState: state,
		AuthEpoch: authEpoch, DecisionRef: "decision_" + eventID,
		OccurredAt: occurredAt.UTC(),
	}
}

func assertAccountRestrictedProjectionField(
	t *testing.T,
	db *mongo.Database,
	collection string,
	filter bson.M,
	want bool,
) {
	t.Helper()
	var document struct {
		AccountRestricted bool `bson:"accountRestricted"`
	}
	if err := db.Collection(collection).FindOne(t.Context(), filter).Decode(&document); err != nil {
		t.Fatalf("read %s restriction projection: %v", collection, err)
	}
	if document.AccountRestricted != want {
		t.Fatalf(
			"%s accountRestricted=%v, want %v",
			collection,
			document.AccountRestricted,
			want,
		)
	}
}
