// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-002
// readiness_case: list-skill-subscriptions-api
// readiness_case: create-skill-subscription-api
// readiness_case: get-skill-subscription-api
// readiness_case: update-skill-subscription-status-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	subscriptionhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/adapters/inbound/http"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
	subscriptionpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/infrastructure/persistence"
)

func TestSkillSubscriptionCommandsCommitAggregateReceiptAndOutboxAtomically(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "assistant_skill_subscription_api_integration")
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	store := subscriptionpersistence.NewMongoStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure SkillSubscription indexes: %v", err)
	}
	service := orchestration.NewAssistantService(
		nil,
		nil,
		orchestration.WithSkillSubscriptionStore(store),
	)
	mux := http.NewServeMux()
	subscriptionhttp.NewHandler(
		subscriptionapplication.NewUseCases(store, nil, service, time.Now),
	).RegisterRoutes(mux)

	createBody := map[string]any{
		"skillId":  "news_briefing",
		"domainId": "news",
		"tagRefs":  []string{"local", "daily"},
		"searchQueryPlan": map[string]any{
			"rawText": "今日新闻",
			"queries": []string{"今日新闻"},
		},
		"trigger": map[string]any{
			"type":     "cron",
			"cron":     "30 8 * * *",
			"timezone": "Asia/Shanghai",
		},
		"destination": map[string]any{
			"destinationType":  "user",
			"maxPerDay":        1,
			"cooldownMinutes":  60,
			"quietHoursPolicy": "inherit_user_setting",
		},
		"clientRequestId": "create-news-subscription",
	}
	created := skillSubscriptionRequest(
		t, mux, http.MethodPost, "/assistant/skill-subscriptions",
		"account-subscription", "create-news-subscription", createBody,
	)
	if created.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", created.Code, created.Body.String())
	}
	var createdResult struct {
		SubscriptionID string `json:"subscriptionId"`
		Version        int64  `json:"version"`
		Status         string `json:"status"`
		UpdatedAt      string `json:"updatedAt"`
	}
	if err := json.Unmarshal(created.Body.Bytes(), &createdResult); err != nil {
		t.Fatalf("decode create result: %v", err)
	}
	if createdResult.SubscriptionID == "" || createdResult.Version != 1 || createdResult.Status != "active" {
		t.Fatalf("unexpected create result: %+v", createdResult)
	}
	listed := skillSubscriptionRequest(
		t,
		mux,
		http.MethodGet,
		"/assistant/skill-subscriptions?status=active&limit=20",
		"account-subscription",
		"",
		nil,
	)
	if listed.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listed.Code, listed.Body.String())
	}
	var listResult struct {
		Items []struct {
			SubscriptionID string `json:"subscriptionId"`
			Status         string `json:"status"`
		} `json:"items"`
	}
	if err := json.Unmarshal(listed.Body.Bytes(), &listResult); err != nil {
		t.Fatalf("decode list result: %v", err)
	}
	if len(listResult.Items) != 1 ||
		listResult.Items[0].SubscriptionID != createdResult.SubscriptionID ||
		listResult.Items[0].Status != "active" {
		t.Fatalf("unexpected list result: %+v", listResult)
	}
	loaded := skillSubscriptionRequest(
		t,
		mux,
		http.MethodGet,
		"/assistant/skill-subscriptions/"+createdResult.SubscriptionID,
		"account-subscription",
		"",
		nil,
	)
	if loaded.Code != http.StatusOK {
		t.Fatalf("get status=%d body=%s", loaded.Code, loaded.Body.String())
	}
	var loadedResult struct {
		SubscriptionID string `json:"subscriptionId"`
		Version        int64  `json:"version"`
		Status         string `json:"status"`
	}
	if err := json.Unmarshal(loaded.Body.Bytes(), &loadedResult); err != nil {
		t.Fatalf("decode get result: %v", err)
	}
	if loadedResult.SubscriptionID != createdResult.SubscriptionID ||
		loadedResult.Version != 1 || loadedResult.Status != "active" {
		t.Fatalf("unexpected get result: %+v", loadedResult)
	}
	foreign := skillSubscriptionRequest(
		t,
		mux,
		http.MethodGet,
		"/assistant/skill-subscriptions/"+createdResult.SubscriptionID,
		"account-other",
		"",
		nil,
	)
	if foreign.Code != http.StatusNotFound {
		t.Fatalf("foreign get status=%d body=%s", foreign.Code, foreign.Body.String())
	}

	replay := skillSubscriptionRequest(
		t, mux, http.MethodPost, "/assistant/skill-subscriptions",
		"account-subscription", "create-news-subscription", createBody,
	)
	if replay.Code != http.StatusCreated || replay.Body.String() != created.Body.String() {
		t.Fatalf("create replay drifted: status=%d body=%s first=%s", replay.Code, replay.Body.String(), created.Body.String())
	}

	conflictingCreate := cloneCommand(createBody)
	conflictingCreate["skillId"] = "stock_sentinel"
	conflict := skillSubscriptionRequest(
		t, mux, http.MethodPost, "/assistant/skill-subscriptions",
		"account-subscription", "create-news-subscription", conflictingCreate,
	)
	assertSkillSubscriptionConflict(t, conflict)
	assertMongoCount(t, runtime.Database.Collection("skill_subscriptions"), bson.M{}, 1)
	assertMongoCount(t, runtime.Database.Collection("skill_subscription_command_receipts"), bson.M{}, 1)
	assertMongoCount(t, runtime.Database.Collection("skill_subscription_outbox"), bson.M{}, 1)

	statusPath := "/assistant/skill-subscriptions/" + createdResult.SubscriptionID + "/status"
	pauseBody := map[string]any{
		"status":          "paused",
		"clientRequestId": "pause-news-subscription",
	}
	paused := skillSubscriptionRequest(
		t, mux, http.MethodPatch, statusPath,
		"account-subscription", "pause-news-subscription", pauseBody,
	)
	if paused.Code != http.StatusOK {
		t.Fatalf("pause status=%d body=%s", paused.Code, paused.Body.String())
	}
	var pausedResult struct {
		Version   int64  `json:"version"`
		Status    string `json:"status"`
		UpdatedAt string `json:"updatedAt"`
	}
	if err := json.Unmarshal(paused.Body.Bytes(), &pausedResult); err != nil {
		t.Fatalf("decode pause result: %v", err)
	}
	if pausedResult.Version != 2 || pausedResult.Status != "paused" || pausedResult.UpdatedAt == createdResult.UpdatedAt {
		t.Fatalf("status transition did not advance one aggregate revision: create=%+v pause=%+v", createdResult, pausedResult)
	}
	assertMongoCount(t, runtime.Database.Collection("skill_subscription_command_receipts"), bson.M{}, 2)
	assertMongoCount(t, runtime.Database.Collection("skill_subscription_outbox"), bson.M{}, 2)

	pauseReplay := skillSubscriptionRequest(
		t, mux, http.MethodPatch, statusPath,
		"account-subscription", "pause-news-subscription", pauseBody,
	)
	if pauseReplay.Code != http.StatusOK || pauseReplay.Body.String() != paused.Body.String() {
		t.Fatalf("status replay drifted: status=%d body=%s first=%s", pauseReplay.Code, pauseReplay.Body.String(), paused.Body.String())
	}

	noopBody := map[string]any{
		"status":          "paused",
		"clientRequestId": "confirm-news-paused",
	}
	noop := skillSubscriptionRequest(
		t, mux, http.MethodPatch, statusPath,
		"account-subscription", "confirm-news-paused", noopBody,
	)
	if noop.Code != http.StatusOK || noop.Body.String() != paused.Body.String() {
		t.Fatalf("status no-op changed aggregate: status=%d body=%s previous=%s", noop.Code, noop.Body.String(), paused.Body.String())
	}
	assertMongoCount(t, runtime.Database.Collection("skill_subscription_command_receipts"), bson.M{}, 3)
	assertMongoCount(t, runtime.Database.Collection("skill_subscription_outbox"), bson.M{}, 2)

	conflictingNoop := map[string]any{
		"status":          "active",
		"clientRequestId": "confirm-news-paused",
	}
	statusConflict := skillSubscriptionRequest(
		t, mux, http.MethodPatch, statusPath,
		"account-subscription", "confirm-news-paused", conflictingNoop,
	)
	assertSkillSubscriptionConflict(t, statusConflict)
	assertMongoCount(t, runtime.Database.Collection("skill_subscriptions"), bson.M{"version": int64(2), "status": "paused"}, 1)
	publicationClaimAt := time.Now().UTC().Truncate(time.Millisecond)
	publication, found, err := store.ClaimPendingOutbox(
		startupCtx,
		"subscription-publication-owner-a",
		publicationClaimAt,
		10*time.Second,
	)
	if err != nil || !found {
		t.Fatalf("ClaimPendingOutbox()=%+v found=%v error=%v", publication, found, err)
	}
	if publication.AggregateID != createdResult.SubscriptionID ||
		string(publication.Payload) != `{"subscriptionId":"`+createdResult.SubscriptionID+`"}` {
		t.Fatalf("subscription publication leaked or drifted: %+v", publication)
	}
	if _, err := runtime.Database.Collection("skill_subscription_outbox").UpdateMany(
		startupCtx,
		bson.M{"_id": bson.M{"$ne": publication.EventID}},
		bson.M{"$set": bson.M{"nextAttemptAt": publicationClaimAt.Add(24 * time.Hour)}},
	); err != nil {
		t.Fatalf("isolate subscription retry event: %v", err)
	}
	failedAt := publicationClaimAt.Add(time.Second)
	retryAt := failedAt.Add(5 * time.Second)
	if err := store.ScheduleOutboxRetry(
		startupCtx, publication.EventID, "subscription-publication-owner-a",
		failedAt, retryAt, "transport_unavailable",
	); err != nil {
		t.Fatalf("ScheduleOutboxRetry() error=%v", err)
	}
	var deliveryState struct {
		AttemptCount  int       `bson:"attemptCount"`
		NextAttemptAt time.Time `bson:"nextAttemptAt"`
		LastErrorCode string    `bson:"lastErrorCode"`
		ClaimOwner    string    `bson:"claimOwner"`
	}
	if err := runtime.Database.Collection("skill_subscription_outbox").FindOne(
		startupCtx, bson.M{"_id": publication.EventID},
	).Decode(&deliveryState); err != nil {
		t.Fatalf("load subscription retry state: %v", err)
	}
	if deliveryState.AttemptCount != 1 || !deliveryState.NextAttemptAt.Equal(retryAt) ||
		deliveryState.LastErrorCode != "transport_unavailable" || deliveryState.ClaimOwner != "" {
		t.Fatalf("persisted subscription retry state=%+v", deliveryState)
	}
	if beforeDue, found, err := store.ClaimPendingOutbox(
		startupCtx, "subscription-publication-owner-b",
		retryAt.Add(-time.Millisecond), 3*time.Second,
	); err != nil || found {
		t.Fatalf("claim subscription before retry due=%+v found=%t err=%v", beforeDue, found, err)
	}
	retried, found, err := store.ClaimPendingOutbox(
		startupCtx, "subscription-publication-owner-b", retryAt, 3*time.Second,
	)
	if err != nil || !found || retried.EventID != publication.EventID || retried.AttemptCount != 2 {
		t.Fatalf("claim subscription retry=%+v found=%t err=%v", retried, found, err)
	}
	expiredAt := retryAt.Add(3 * time.Second)
	if err := store.MarkOutboxPublished(
		startupCtx, retried.EventID, "subscription-publication-owner-b", expiredAt,
	); !errors.Is(err, subscriptionports.ErrOutboxClaimLost) {
		t.Fatalf("expired subscription checkpoint error=%v, want claim lost", err)
	}
	if err := store.ScheduleOutboxRetry(
		startupCtx, retried.EventID, "subscription-publication-owner-b",
		expiredAt, expiredAt.Add(time.Second), "expired_owner",
	); !errors.Is(err, subscriptionports.ErrOutboxClaimLost) {
		t.Fatalf("expired subscription retry error=%v, want claim lost", err)
	}
	takeover, found, err := store.ClaimPendingOutbox(
		startupCtx, "subscription-publication-owner-c", expiredAt, 10*time.Second,
	)
	if err != nil || !found || takeover.EventID != publication.EventID || takeover.AttemptCount != 3 {
		t.Fatalf("subscription lease takeover=%+v found=%t err=%v", takeover, found, err)
	}
	if err := store.MarkOutboxPublished(
		startupCtx, takeover.EventID, "subscription-publication-owner-c", expiredAt,
	); err != nil {
		t.Fatalf("MarkOutboxPublished(takeover) error=%v", err)
	}
	assertMongoCount(
		t,
		runtime.Database.Collection("skill_subscription_outbox"),
		bson.M{"publishedAt": bson.M{"$exists": true}},
		1,
	)
}

func skillSubscriptionRequest(
	t *testing.T,
	handler http.Handler,
	method, path, accountID, commandID string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal SkillSubscription request: %v", err)
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", commandID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{
			Actor: operation.ActorContext{
				AccountID: accountID,
				PersonaID: accountID + ":persona",
			},
		},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func cloneCommand(source map[string]any) map[string]any {
	cloned := make(map[string]any, len(source))
	for key, value := range source {
		cloned[key] = value
	}
	return cloned
}

func assertSkillSubscriptionConflict(t *testing.T, recorder *httptest.ResponseRecorder) {
	t.Helper()
	if recorder.Code != http.StatusConflict ||
		!strings.Contains(recorder.Body.String(), "subscription_idempotency_conflict") {
		t.Fatalf("expected canonical idempotency conflict, status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

func assertMongoCount(
	t *testing.T,
	collection *mongo.Collection,
	filter any,
	want int64,
) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	got, err := collection.CountDocuments(ctx, filter)
	if err != nil || got != want {
		t.Fatalf("%s count=%d error=%v, want %d", collection.Name(), got, err, want)
	}
}
