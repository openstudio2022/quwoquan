// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
// readiness_case: apply-search-request-account-closure-api
// readiness_case: recover-search-account-closure-dead-letter-api
package api_integration

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/accountrestriction"
	rterr "quwoquan_service/runtime/errors"
	runtimemessaging "quwoquan_service/runtime/messaging"
	recentsearchstore "quwoquan_service/services/search-service/internal/search/recent_search_state/infrastructure/persistence"
	feedbackstore "quwoquan_service/services/search-service/internal/search/search_feedback_fact/infrastructure/feedbackstore"
	accountrestrictioninfra "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/accountrestriction"
	mqadapter "quwoquan_service/services/search-service/internal/search/search_request_fact/adapters/inbound/mq"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/infrastructure/accountclosure"
)

func TestRecoverSearchAccountClosureDeadLetterHTTPReleasesMongoTerminalMarker(
	t *testing.T,
) {
	cleanSearchCollections(t)
	ctx := t.Context()
	restrictionProjection, err :=
		accountrestrictioninfra.NewMongoAccountRestrictionProjection(mongoDB)
	if err != nil {
		t.Fatal(err)
	}
	projection, err := accountclosure.NewMongoProjection(
		mongoDB,
		restrictionProjection,
		newClosureRecentSearchStore(t),
		newClosureFeedbackStore(t),
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	const sourceStreamID = "1710000000000-73"
	if _, err := projection.RecordUserAccountClosedFailure(
		ctx,
		mqadapter.UserAccountEventStream,
		sourceStreamID,
		"search-account-closure-event-73",
		errors.New("scripted cleanup dependency failure"),
	); err != nil {
		t.Fatalf("record terminal failure: %v", err)
	}
	if err := projection.MarkUserAccountClosedDeadLettered(
		ctx,
		mqadapter.UserAccountEventStream,
		sourceStreamID,
	); err != nil {
		t.Fatal(err)
	}

	transport, err := runtimemessaging.NewRedisMessageTransport(
		realRedisClient,
		realRedisClient,
	)
	if err != nil {
		t.Fatal(err)
	}
	consumer, err := mqadapter.NewUserAccountClosedConsumer(
		transport,
		projection,
		projection,
		"search-account-closure-api-contract",
		nil,
		mqadapter.UserAccountClosedConsumerConfig{
			BatchSize: 10, MaxAttempts: 2, MinIdle: 0,
			PollInterval: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	recoveryFacet, err :=
		application.NewSearchRequestAccountClosureRecoveryCommandFacet(consumer)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		http.NotFoundHandler(),
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/search/account-closure/dead-letters:recover",
			Module:   rterr.ModuleSearch,
			Releaser: recoveryFacet,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/search/account-closure/dead-letters:recover",
		bytes.NewBufferString(`{"sourceStreamId":"1710000000000-73"}`),
	)
	request.Header.Set("Idempotency-Key", "recover-search-account-closure-73")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusAccepted {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), `"sourceStreamId":"1710000000000-73"`) ||
		!strings.Contains(response.Body.String(), `"recoveryAccepted":true`) {
		t.Fatalf("typed recovery receipt=%s", response.Body.String())
	}
	deadLettered, err := projection.IsUserAccountClosedDeadLettered(
		ctx,
		mqadapter.UserAccountEventStream,
		sourceStreamID,
	)
	if err != nil {
		t.Fatal(err)
	}
	if deadLettered {
		t.Fatal("HTTP recovery must clear the canonical Mongo terminal marker")
	}
}

func TestUserAccountClosedTerminalMarkerRetainsSourcePELReference(
	t *testing.T,
) {
	cleanSearchCollections(t)
	ctx := t.Context()
	restrictionProjection, err :=
		accountrestrictioninfra.NewMongoAccountRestrictionProjection(mongoDB)
	if err != nil {
		t.Fatal(err)
	}
	projection, err := accountclosure.NewMongoProjection(
		mongoDB,
		restrictionProjection,
		newClosureRecentSearchStore(t),
		newClosureFeedbackStore(t),
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	const (
		sourceStream   = "events.user.account"
		sourceStreamID = "1710000000000-73"
	)
	if attempts, err := projection.RecordUserAccountClosedFailure(
		ctx,
		sourceStream,
		sourceStreamID,
		"search-account-closure-event-73",
		errors.New("scripted cleanup dependency failure"),
	); err != nil || attempts != 1 {
		t.Fatalf("record failure: attempts=%d err=%v", attempts, err)
	}
	if err := projection.MarkUserAccountClosedDeadLettered(
		ctx,
		sourceStream,
		sourceStreamID,
	); err != nil {
		t.Fatal(err)
	}
	var marker bson.M
	if err := mongoDB.Collection("search_user_account_closed_failures").FindOne(
		ctx,
		bson.M{
			"sourceStream":   sourceStream,
			"sourceStreamId": sourceStreamID,
		},
	).Decode(&marker); err != nil {
		t.Fatalf("read terminal marker by source reference: %v", err)
	}
	if marker["deadLetteredAt"] == nil {
		t.Fatalf("terminal marker lacks dead-letter state: %v", marker)
	}
	if _, exists := marker["expireAt"]; exists {
		t.Fatalf("terminal marker retained transient TTL: %v", marker)
	}
}

func TestUserAccountClosedProjectionDeletesPrivateSearchStateAndRejectsConflict(
	t *testing.T,
) {
	cleanSearchCollections(t)
	ctx := context.Background()
	restrictionProjection, err :=
		accountrestrictioninfra.NewMongoAccountRestrictionProjection(mongoDB)
	if err != nil {
		t.Fatal(err)
	}
	if err := restrictionProjection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	projection, err := accountclosure.NewMongoProjection(
		mongoDB,
		restrictionProjection,
		newClosureRecentSearchStore(t),
		newClosureFeedbackStore(t),
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, time.July, 20, 12, 0, 0, 0, time.UTC)
	insertSearchClosureFixtures(t, now)
	suspension := accountrestriction.Event{
		EventID:        "search-account-suspended-event",
		EventName:      accountrestriction.UserSuspendedEventName,
		AccountID:      "account-closed",
		AccountVersion: 6,
		UserID:         "account-closed",
		PersonaIDs:     []string{"persona-closed"},
		AccountState:   "suspended",
		AuthEpoch:      6,
		DecisionRef:    "decision-suspend-before-close",
		OccurredAt:     now.Add(-time.Minute),
	}
	if _, err := restrictionProjection.Apply(ctx, suspension); err != nil {
		t.Fatalf("seed reversible account restriction: %v", err)
	}
	event := application.UserAccountClosedEvent{
		EventID:        "search-account-closed-event",
		AccountVersion: 7,
		UserID:         "account-closed",
		PersonaIDs:     []string{"persona-closed"},
		AccountState:   "closed",
		UpdatedAt:      now,
		OccurredAt:     now,
	}

	result, err := projection.ApplyUserAccountClosed(ctx, event)
	if err != nil {
		t.Fatalf("apply UserAccountClosed: %v", err)
	}
	if result.Replayed {
		t.Fatal("first UserAccountClosed apply must not be replayed")
	}
	for _, assertion := range []struct {
		collection string
		filter     bson.M
		want       int64
	}{
		{"recent_search_states", bson.M{"personaId": "persona-closed"}, 0},
		{"recent_search_receipts", bson.M{"personaId": "persona-closed"}, 0},
		{"search_queries", bson.M{"viewerId": bson.M{"$in": bson.A{"account-closed", "persona-closed"}}}, 0},
		{"search_feedback_events", bson.M{"viewerId": "persona-closed"}, 0},
		{"search_feedback_events", bson.M{"searchRequestId": "request-closed"}, 0},
		{"search_feedback_command_receipts", bson.M{"viewerId": "persona-closed"}, 0},
		{"search_feedback_command_receipts", bson.M{"searchRequestId": "request-closed"}, 0},
		{"rm_search_term_heat", bson.M{"normalizedTerm": "私密检索词"}, 0},
		{"search_user_account_restrictions", bson.M{}, 0},
		{"search_user_account_restriction_inbox", bson.M{}, 0},
		{"recent_search_states", bson.M{"personaId": "persona-active"}, 1},
		{"recent_search_receipts", bson.M{"personaId": "persona-active"}, 1},
		{"search_queries", bson.M{"viewerId": "persona-active"}, 1},
		{"search_feedback_events", bson.M{"viewerId": "persona-active"}, 1},
		{"search_feedback_command_receipts", bson.M{"viewerId": "persona-active"}, 1},
		{"rm_search_term_heat", bson.M{"normalizedTerm": "保留热词"}, 1},
	} {
		if got := countSearchClosureDocuments(
			t,
			assertion.collection,
			assertion.filter,
		); got != assertion.want {
			t.Fatalf(
				"%s filter=%v count=%d want=%d",
				assertion.collection,
				assertion.filter,
				got,
				assertion.want,
			)
		}
	}
	lateRestore := suspension
	lateRestore.EventID = "search-account-restore-after-close-event"
	lateRestore.EventName = accountrestriction.UserRestoredEventName
	lateRestore.AccountVersion = 8
	lateRestore.AccountState = "active"
	lateRestore.AuthEpoch = 8
	lateRestore.DecisionRef = "decision-restore-after-close"
	lateRestore.OccurredAt = now.Add(time.Minute)
	if late, err := restrictionProjection.Apply(ctx, lateRestore); err != nil ||
		!late.Replayed || !late.Stale || !late.Terminal || late.Affected != 0 {
		t.Fatalf("late Search restore after closure: result=%+v err=%v", late, err)
	}
	delayedSuspend := suspension
	delayedSuspend.EventID = "search-account-delayed-suspend-event"
	delayedSuspend.AccountVersion = 5
	delayedSuspend.AuthEpoch = 5
	delayedSuspend.DecisionRef = "decision-delayed-suspend-after-close"
	delayedSuspend.OccurredAt = now.Add(-2 * time.Minute)
	if late, err := restrictionProjection.Apply(ctx, delayedSuspend); err != nil ||
		!late.Replayed || !late.Stale || !late.Terminal || late.Affected != 0 {
		t.Fatalf("delayed Search suspend after closure: result=%+v err=%v", late, err)
	}
	if count := countSearchClosureDocuments(
		t,
		"search_user_account_restrictions",
		bson.M{},
	); count != 0 {
		t.Fatalf("late events recreated Search restriction state=%d", count)
	}
	if count := countSearchClosureDocuments(
		t,
		"search_user_account_restriction_inbox",
		bson.M{},
	); count != 0 {
		t.Fatalf("late events recreated Search restriction inbox=%d", count)
	}
	var terminalWatermark bson.M
	if err := mongoDB.Collection("search_user_account_restriction_watermarks").FindOne(
		ctx,
		bson.M{"terminal": true, "accountVersion": int64(7)},
	).Decode(&terminalWatermark); err != nil {
		t.Fatalf("read Search terminal restriction watermark: %v", err)
	}
	encodedWatermark, err := bson.MarshalExtJSON(terminalWatermark, false, false)
	if err != nil {
		t.Fatal(err)
	}
	for _, rawID := range []string{"account-closed", "persona-closed"} {
		if strings.Contains(string(encodedWatermark), rawID) {
			t.Fatalf("Search terminal watermark retained raw identity %q: %s", rawID, encodedWatermark)
		}
	}
	var inbox bson.M
	if err := mongoDB.Collection(accountclosure.InboxCollection).FindOne(
		ctx,
		bson.M{"_id": event.EventID},
	).Decode(&inbox); err != nil {
		t.Fatalf("read UserAccountClosed inbox: %v", err)
	}
	if inbox["eventDigest"] == "" {
		t.Fatal("UserAccountClosed inbox must retain digest")
	}
	for _, forbidden := range []string{"userId", "personaIds", "payload"} {
		if _, exists := inbox[forbidden]; exists {
			t.Fatalf("UserAccountClosed inbox retained %s: %v", forbidden, inbox)
		}
	}

	replay, err := projection.ApplyUserAccountClosed(ctx, event)
	if err != nil || !replay.Replayed {
		t.Fatalf("replay=%+v err=%v", replay, err)
	}
	conflict := event
	conflict.UserID = "account-conflict"
	if _, err := projection.ApplyUserAccountClosed(
		ctx,
		conflict,
	); !errors.Is(err, application.ErrUserAccountClosedEventIDConflict) {
		t.Fatalf("eventId conflict err=%v", err)
	}
}

func newClosureRecentSearchStore(t *testing.T) *recentsearchstore.Store {
	t.Helper()
	store := recentsearchstore.NewStore(mongoDB)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure RecentSearchState indexes: %v", err)
	}
	return store
}

func newClosureFeedbackStore(t *testing.T) *feedbackstore.Store {
	t.Helper()
	store := feedbackstore.NewStore(mongoDB)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure SearchFeedbackFact indexes: %v", err)
	}
	return store
}

func insertSearchClosureFixtures(t *testing.T, now time.Time) {
	t.Helper()
	ctx := context.Background()
	fixtures := map[string][]any{
		"recent_search_states": {
			bson.M{
				"_id": "state-closed", "personaId": "persona-closed",
				"scope": "all", "entries": bson.A{bson.M{
					"entryId": "entry-closed", "query": "私密检索词",
					"scope": "all", "updatedAt": now,
				}}, "version": int64(1), "updatedAt": now,
			},
			bson.M{
				"_id": "state-active", "personaId": "persona-active",
				"scope": "all", "entries": bson.A{}, "version": int64(1),
				"updatedAt": now,
			},
		},
		"recent_search_receipts": {
			bson.M{
				"_id": "receipt-closed", "personaId": "persona-closed",
				"commandDigest": "digest-closed", "stateVersion": int64(1),
				"createdAt": now, "expiresAt": now.Add(time.Hour),
			},
			bson.M{
				"_id": "receipt-active", "personaId": "persona-active",
				"commandDigest": "digest-active", "stateVersion": int64(1),
				"createdAt": now, "expiresAt": now.Add(time.Hour),
			},
		},
		"search_queries": {
			bson.M{
				"searchRequestId": "request-closed", "query": "私密检索词",
				"viewerId": "persona-closed", "createdAt": now,
			},
			bson.M{
				"searchRequestId": "request-account", "query": "账号私密词",
				"viewerId": "account-closed", "createdAt": now,
			},
			bson.M{
				"searchRequestId": "request-active", "query": "保留热词",
				"viewerId": "persona-active", "createdAt": now,
			},
		},
		"search_feedback_events": {
			bson.M{
				"searchRequestId": "request-closed", "eventType": "click",
				"objectId": "post-closed", "createdAt": now,
				"commandDigest": "digest-feedback-closed-request",
			},
			bson.M{
				"searchRequestId": "request-expired-query", "viewerId": "persona-closed",
				"eventType": "dwell", "objectId": "post-closed", "createdAt": now,
				"commandDigest": "digest-feedback-closed-viewer",
			},
			bson.M{
				"searchRequestId": "request-active", "viewerId": "persona-active",
				"eventType": "click", "objectId": "post-active", "createdAt": now,
				"commandDigest": "digest-feedback-active",
			},
		},
		"search_feedback_command_receipts": {
			bson.M{
				"_id": "feedback-closed-request", "commandDigest": "digest-feedback-closed-request",
				"searchRequestId": "request-closed", "eventType": "click", "objectId": "post-closed",
				"status": "completed", "createdAt": now, "updatedAt": now, "expiresAt": now.Add(time.Hour),
			},
			bson.M{
				"_id": "feedback-closed-viewer", "commandDigest": "digest-feedback-closed-viewer",
				"viewerId": "persona-closed", "searchRequestId": "request-expired-query",
				"eventType": "dwell", "objectId": "post-closed", "status": "completed",
				"createdAt": now, "updatedAt": now, "expiresAt": now.Add(time.Hour),
			},
			bson.M{
				"_id": "feedback-active", "commandDigest": "digest-feedback-active",
				"viewerId": "persona-active", "searchRequestId": "request-active",
				"eventType": "click", "objectId": "post-active", "status": "completed",
				"createdAt": now, "updatedAt": now, "expiresAt": now.Add(time.Hour),
			},
		},
		"rm_search_term_heat": {
			bson.M{"normalizedTerm": "私密检索词", "relevance": 1.0, "updatedAt": now},
			bson.M{"normalizedTerm": "账号私密词", "relevance": 1.0, "updatedAt": now},
			bson.M{"normalizedTerm": "保留热词", "relevance": 1.0, "updatedAt": now},
		},
	}
	for collection, documents := range fixtures {
		if _, err := mongoDB.Collection(collection).InsertMany(ctx, documents); err != nil {
			t.Fatalf("seed %s: %v", collection, err)
		}
	}
}

func countSearchClosureDocuments(
	t *testing.T,
	collection string,
	filter bson.M,
) int64 {
	t.Helper()
	count, err := mongoDB.Collection(collection).CountDocuments(
		context.Background(),
		filter,
	)
	if err != nil {
		t.Fatalf("count %s: %v", collection, err)
	}
	return count
}
