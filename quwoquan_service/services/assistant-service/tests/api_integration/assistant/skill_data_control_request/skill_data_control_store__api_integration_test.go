// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
// readiness_case: create-skill-data-control-request-api
// readiness_case: confirm-skill-data-control-request-api
// readiness_case: get-skill-data-control-request-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	datacontrolhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
	datacontrolports "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/infrastructure/persistence"
)

func TestSkillDataControlStoreCommitsAggregateReceiptAndOutboxAtomically(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(
		startupCtx, "assistant_skill_data_control_api_integration",
	)
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

	store := persistence.NewStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("EnsureIndexes() error=%v", err)
	}
	now := time.Date(2026, 8, 4, 12, 0, 0, 0, time.UTC)
	request, err := model.NewRequest(
		"control-request-a",
		"account-a",
		"travel_companion",
		[]string{model.ActionRevokeConsent, model.ActionArchiveSubscriptions},
		now,
	)
	if err != nil {
		t.Fatalf("NewRequest() error=%v", err)
	}
	create, err := model.NewCreateCommand(request, "create-control-a")
	if err != nil {
		t.Fatalf("NewCreateCommand() error=%v", err)
	}
	created, err := store.Create(startupCtx, create)
	if err != nil || created.Replayed {
		t.Fatalf("Create()=%+v error=%v", created, err)
	}
	replayed, err := store.Create(startupCtx, create)
	if err != nil || !replayed.Replayed || replayed.Request.RequestID != request.RequestID {
		t.Fatalf("Create(replay)=%+v error=%v", replayed, err)
	}
	conflictingRequest, err := model.NewRequest(
		"control-request-conflict",
		"account-a",
		"travel_companion",
		[]string{model.ActionHideActivityHistory},
		now,
	)
	if err != nil {
		t.Fatalf("NewRequest(conflict) error=%v", err)
	}
	conflictingCreate, err := model.NewCreateCommand(
		conflictingRequest, "create-control-a",
	)
	if err != nil {
		t.Fatalf("NewCreateCommand(conflict) error=%v", err)
	}
	if _, err := store.Create(startupCtx, conflictingCreate); !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("Create(conflict) error=%v", err)
	}

	confirm, err := model.NewConfirmCommand(
		"account-a", request.RequestID, request.Revision, true,
		"confirm-control-a", now.Add(time.Minute),
	)
	if err != nil {
		t.Fatalf("NewConfirmCommand() error=%v", err)
	}
	executing, err := store.Confirm(startupCtx, confirm)
	if err != nil || executing.Request.Status != model.StatusExecuting {
		t.Fatalf("Confirm()=%+v error=%v", executing, err)
	}
	claimAt := now.Add(2 * time.Minute)
	type claimResult struct {
		claim model.ExecutionClaim
		found bool
		err   error
	}
	results := make(chan claimResult, 2)
	var claimWait sync.WaitGroup
	for _, workerID := range []string{"worker-a", "worker-b"} {
		workerID := workerID
		claimWait.Add(1)
		go func() {
			defer claimWait.Done()
			claim, found, claimErr := store.ClaimNextExecution(
				startupCtx, workerID, claimAt, 5*time.Second,
			)
			results <- claimResult{claim: claim, found: found, err: claimErr}
		}()
	}
	claimWait.Wait()
	close(results)
	winners := []model.ExecutionClaim{}
	for result := range results {
		if result.err != nil {
			t.Fatalf("ClaimNextExecution(concurrent) error=%v", result.err)
		}
		if result.found {
			winners = append(winners, result.claim)
		}
	}
	if len(winners) != 1 {
		t.Fatalf("concurrent claim winners=%d, want 1", len(winners))
	}
	firstClaim := winners[0]
	current, err := store.MarkActionCompleted(
		startupCtx,
		firstClaim.Fence,
		firstClaim.Request.RequestedActions[0],
		firstClaim.Request.Revision,
		claimAt.Add(time.Second),
	)
	if err != nil {
		t.Fatalf("MarkActionCompleted(first) error=%v", err)
	}
	heartbeat, err := store.HeartbeatExecution(
		startupCtx,
		firstClaim.Fence,
		claimAt.Add(2*time.Second),
		5*time.Second,
	)
	if err != nil || !heartbeat.LeaseExpiresAt.After(firstClaim.Fence.LeaseExpiresAt) {
		t.Fatalf("HeartbeatExecution()=%+v error=%v", heartbeat, err)
	}
	if _, found, err := store.ClaimNextExecution(
		startupCtx,
		"worker-c",
		claimAt.Add(6*time.Second),
		5*time.Second,
	); err != nil || found {
		t.Fatalf("ClaimNextExecution(before heartbeat expiry) found=%v error=%v", found, err)
	}
	recoveryClaim, found, err := store.ClaimNextExecution(
		startupCtx,
		"worker-c",
		claimAt.Add(8*time.Second),
		5*time.Second,
	)
	if err != nil || !found || recoveryClaim.Fence.Token <= firstClaim.Fence.Token {
		t.Fatalf("ClaimNextExecution(recovery)=%+v found=%v error=%v", recoveryClaim, found, err)
	}
	if _, err := store.MarkActionCompleted(
		startupCtx,
		firstClaim.Fence,
		firstClaim.Request.RequestedActions[1],
		current.Revision,
		claimAt.Add(8*time.Second),
	); !errors.Is(err, model.ErrRevisionConflict) {
		t.Fatalf("expired fence MarkActionCompleted() error=%v", err)
	}
	if _, err := store.HeartbeatExecution(
		startupCtx,
		firstClaim.Fence,
		claimAt.Add(8*time.Second),
		5*time.Second,
	); !errors.Is(err, model.ErrRevisionConflict) {
		t.Fatalf("expired fence HeartbeatExecution() error=%v", err)
	}
	if len(recoveryClaim.Request.CompletedActions) != 1 ||
		recoveryClaim.Request.CompletedActions[0] != firstClaim.Request.RequestedActions[0] {
		t.Fatalf("recovery claim lost durable progress: %+v", recoveryClaim.Request)
	}
	current, err = store.MarkActionCompleted(
		startupCtx,
		recoveryClaim.Fence,
		recoveryClaim.Request.RequestedActions[1],
		recoveryClaim.Request.Revision,
		claimAt.Add(9*time.Second),
	)
	if err != nil {
		t.Fatalf("MarkActionCompleted(recovery) error=%v", err)
	}
	current, err = store.MarkCompleted(
		startupCtx,
		recoveryClaim.Fence,
		current.Revision,
		claimAt.Add(10*time.Second),
	)
	if err != nil || current.Status != model.StatusCompleted || current.CompletedAt == nil {
		t.Fatalf("MarkCompleted()=%+v error=%v", current, err)
	}
	if _, found, err := store.ClaimNextExecution(
		startupCtx,
		"worker-d",
		claimAt.Add(30*time.Second),
		5*time.Second,
	); err != nil || found {
		t.Fatalf("completed request was reclaimed found=%v error=%v", found, err)
	}
	confirmReplay, err := store.Confirm(startupCtx, confirm)
	if err != nil || !confirmReplay.Replayed || confirmReplay.Request.Status != model.StatusCompleted {
		t.Fatalf("Confirm(replay)=%+v error=%v", confirmReplay, err)
	}

	assertCount(t, startupCtx, runtime.Database.Collection("skill_data_control_requests"), bson.M{}, 1)
	assertCount(t, startupCtx, runtime.Database.Collection("skill_data_control_command_receipts"), bson.M{}, 2)
	assertCount(t, startupCtx, runtime.Database.Collection("skill_data_control_outbox"), bson.M{}, 3)
	publicationClaimAt := claimAt.Add(40 * time.Second)
	publication, found, err := store.ClaimPendingOutbox(
		startupCtx,
		"data-control-publication-owner-a",
		publicationClaimAt,
		10*time.Second,
	)
	if err != nil || !found {
		t.Fatalf("ClaimPendingOutbox()=%+v found=%v error=%v", publication, found, err)
	}
	var publicationPayload map[string]any
	if err := json.Unmarshal(publication.Payload, &publicationPayload); err != nil {
		t.Fatalf("decode publication payload: %v", err)
	}
	if publication.AggregateID != request.RequestID || publicationPayload["accountId"] != "account-a" {
		t.Fatalf("publication identity/payload drifted: event=%+v payload=%v", publication, publicationPayload)
	}
	if _, err := runtime.Database.Collection("skill_data_control_outbox").UpdateMany(
		startupCtx,
		bson.M{"_id": bson.M{"$ne": publication.EventID}},
		bson.M{"$set": bson.M{"nextAttemptAt": publicationClaimAt.Add(24 * time.Hour)}},
	); err != nil {
		t.Fatalf("isolate data control retry event: %v", err)
	}
	failedAt := publicationClaimAt.Add(time.Second)
	retryAt := failedAt.Add(5 * time.Second)
	if err := store.ScheduleOutboxRetry(
		startupCtx, publication.EventID, "data-control-publication-owner-a",
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
	if err := runtime.Database.Collection("skill_data_control_outbox").FindOne(
		startupCtx, bson.M{"_id": publication.EventID},
	).Decode(&deliveryState); err != nil {
		t.Fatalf("load data control retry state: %v", err)
	}
	if deliveryState.AttemptCount != 1 || !deliveryState.NextAttemptAt.Equal(retryAt) ||
		deliveryState.LastErrorCode != "transport_unavailable" || deliveryState.ClaimOwner != "" {
		t.Fatalf("persisted data control retry state=%+v", deliveryState)
	}
	if beforeDue, found, err := store.ClaimPendingOutbox(
		startupCtx, "data-control-publication-owner-b",
		retryAt.Add(-time.Millisecond), 3*time.Second,
	); err != nil || found {
		t.Fatalf("claim before retry due=%+v found=%t err=%v", beforeDue, found, err)
	}
	retried, found, err := store.ClaimPendingOutbox(
		startupCtx, "data-control-publication-owner-b", retryAt, 3*time.Second,
	)
	if err != nil || !found || retried.EventID != publication.EventID || retried.AttemptCount != 2 {
		t.Fatalf("claim data control retry=%+v found=%t err=%v", retried, found, err)
	}
	expiredAt := retryAt.Add(3 * time.Second)
	if err := store.MarkOutboxPublished(
		startupCtx, retried.EventID, "data-control-publication-owner-b", expiredAt,
	); !errors.Is(err, datacontrolports.ErrOutboxClaimLost) {
		t.Fatalf("expired data control checkpoint error=%v, want claim lost", err)
	}
	if err := store.ScheduleOutboxRetry(
		startupCtx, retried.EventID, "data-control-publication-owner-b",
		expiredAt, expiredAt.Add(time.Second), "expired_owner",
	); !errors.Is(err, datacontrolports.ErrOutboxClaimLost) {
		t.Fatalf("expired data control retry error=%v, want claim lost", err)
	}
	takeover, found, err := store.ClaimPendingOutbox(
		startupCtx, "data-control-publication-owner-c", expiredAt, 10*time.Second,
	)
	if err != nil || !found || takeover.EventID != publication.EventID || takeover.AttemptCount != 3 {
		t.Fatalf("data control lease takeover=%+v found=%t err=%v", takeover, found, err)
	}
	if err := store.MarkOutboxPublished(
		startupCtx, takeover.EventID, "data-control-publication-owner-c", expiredAt,
	); err != nil {
		t.Fatalf("MarkOutboxPublished(takeover) error=%v", err)
	}
	assertCount(
		t,
		startupCtx,
		runtime.Database.Collection("skill_data_control_outbox"),
		bson.M{"publishedAt": bson.M{"$exists": true}},
		1,
	)
	assertIndexExists(
		t,
		startupCtx,
		runtime.Database.Collection("skill_data_control_requests"),
		"idx_skill_data_control_execution_recovery",
	)
	activities, err := store.ListSkillDataControlActivities(
		startupCtx, "account-a", "travel_companion", 20,
	)
	if err != nil || len(activities) != 3 || activities[0].Status != model.StatusCompleted {
		t.Fatalf("ListSkillDataControlActivities()=%+v error=%v", activities, err)
	}

	service := application.NewService(
		store,
		func() time.Time { return now.Add(3 * time.Hour) },
		func() string { return "control-request-http" },
	)
	mux := http.NewServeMux()
	datacontrolhttp.NewHandler(service).RegisterRoutes(mux)
	createdHTTP := skillDataControlRequest(
		t,
		mux,
		http.MethodPost,
		"/assistant/skills/travel_companion/data-control-requests",
		"account-http",
		"create-control-http",
		map[string]any{"requestedActions": []string{model.ActionHideActivityHistory}},
	)
	if createdHTTP.Code != http.StatusOK {
		t.Fatalf("HTTP create status=%d body=%s", createdHTTP.Code, createdHTTP.Body.String())
	}
	var createdHTTPResult model.MutationResult
	if err := json.Unmarshal(createdHTTP.Body.Bytes(), &createdHTTPResult); err != nil {
		t.Fatalf("decode HTTP create result: %v", err)
	}
	if createdHTTPResult.Request.RequestID != "control-request-http" ||
		createdHTTPResult.Request.Status != model.StatusPendingConfirmation {
		t.Fatalf("HTTP create result=%+v", createdHTTPResult)
	}
	confirmedHTTP := skillDataControlRequest(
		t,
		mux,
		http.MethodPost,
		"/assistant/skill-data-control-requests/control-request-http/confirm",
		"account-http",
		"confirm-control-http",
		map[string]any{
			"expectedRevision": createdHTTPResult.Request.Revision,
			"confirmed":        false,
		},
	)
	if confirmedHTTP.Code != http.StatusOK {
		t.Fatalf("HTTP confirm status=%d body=%s", confirmedHTTP.Code, confirmedHTTP.Body.String())
	}
	var confirmedHTTPResult model.MutationResult
	if err := json.Unmarshal(confirmedHTTP.Body.Bytes(), &confirmedHTTPResult); err != nil {
		t.Fatalf("decode HTTP confirm result: %v", err)
	}
	if confirmedHTTPResult.Request.Status != model.StatusCancelled ||
		confirmedHTTPResult.Request.Revision != createdHTTPResult.Request.Revision+1 {
		t.Fatalf("HTTP confirm result=%+v", confirmedHTTPResult)
	}
	loadedHTTP := skillDataControlRequest(
		t,
		mux,
		http.MethodGet,
		"/assistant/skill-data-control-requests/control-request-http",
		"account-http",
		"",
		nil,
	)
	if loadedHTTP.Code != http.StatusOK {
		t.Fatalf("HTTP get status=%d body=%s", loadedHTTP.Code, loadedHTTP.Body.String())
	}
	var loadedHTTPRequest model.Request
	if err := json.Unmarshal(loadedHTTP.Body.Bytes(), &loadedHTTPRequest); err != nil {
		t.Fatalf("decode HTTP get result: %v", err)
	}
	if loadedHTTPRequest.RequestID != "control-request-http" ||
		loadedHTTPRequest.Status != model.StatusCancelled {
		t.Fatalf("HTTP get result=%+v", loadedHTTPRequest)
	}
	foreignHTTP := skillDataControlRequest(
		t,
		mux,
		http.MethodGet,
		"/assistant/skill-data-control-requests/control-request-http",
		"account-other",
		"",
		nil,
	)
	if foreignHTTP.Code != http.StatusNotFound {
		t.Fatalf("foreign HTTP get status=%d body=%s", foreignHTTP.Code, foreignHTTP.Body.String())
	}
	assertCount(t, startupCtx, runtime.Database.Collection("skill_data_control_requests"), bson.M{}, 2)
	assertCount(t, startupCtx, runtime.Database.Collection("skill_data_control_command_receipts"), bson.M{}, 4)
	assertCount(t, startupCtx, runtime.Database.Collection("skill_data_control_outbox"), bson.M{}, 5)
}

func skillDataControlRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	accountID string,
	idempotencyKey string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal SkillDataControl request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{AccountID: accountID}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertIndexExists(
	t *testing.T,
	ctx context.Context,
	collection *mongo.Collection,
	name string,
) {
	t.Helper()
	cursor, err := collection.Indexes().List(ctx)
	if err != nil {
		t.Fatalf("list indexes: %v", err)
	}
	defer cursor.Close(ctx)
	var indexes []bson.M
	if err := cursor.All(ctx, &indexes); err != nil {
		t.Fatalf("decode indexes: %v", err)
	}
	for _, index := range indexes {
		if index["name"] == name {
			return
		}
	}
	t.Fatalf("index %q not found: %+v", name, indexes)
}

func assertCount(
	t *testing.T,
	ctx context.Context,
	collection *mongo.Collection,
	filter any,
	want int64,
) {
	t.Helper()
	got, err := collection.CountDocuments(ctx, filter)
	if err != nil || got != want {
		t.Fatalf("count=%d error=%v, want %d", got, err, want)
	}
}
