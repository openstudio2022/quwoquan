// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
// readiness_case: submit-external-interaction-local
// readiness_case: get-external-interaction-local
// readiness_case: list-external-interaction-attempts-local
// readiness_case: list-external-interaction-dead-letters-local
// readiness_case: recover-external-interaction-dead-letter-local
// readiness_case: get-external-interaction-metrics-local
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	externalgenerated "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	httpadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/http"
	externalapplication "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

type handlerTestExternalProvider struct{}

func (handlerTestExternalProvider) Send(
	_ context.Context,
	request reliabletask.ExternalInteractionRequest,
	_ reliabletask.ReliableAsyncTask,
) (reliabletask.ExternalInteractionResult, error) {
	return reliabletask.ExternalInteractionResult{
		RequestID:         request.RequestID,
		Operation:         request.Operation,
		Status:            reliabletask.ExternalInteractionStatusSentUnconfirmed,
		Provider:          "test_sms",
		ProviderRequestID: "test-provider-" + request.RequestID,
		OccurredAt:        time.Now().UTC(),
	}, nil
}

type handlerTestOTPReferenceStore struct{}

func (handlerTestOTPReferenceStore) Put(context.Context, otpseal.StoredReference) error { return nil }
func (handlerTestOTPReferenceStore) Get(context.Context, string, string) (otpseal.StoredReference, error) {
	return otpseal.StoredReference{}, otpseal.ErrReferenceNotFound
}
func (handlerTestOTPReferenceStore) Delete(context.Context, string, string) error { return nil }

func TestSubmitExternalInteractionReturnsAcceptedAndRecordsAttempt(t *testing.T) {
	store := reliabletask.NewMemoryStore()
	service, err := externalapplication.NewExternalInteractionService(
		canonicalMemoryExternalStore(store),
		map[string]reliabletask.ExternalProvider{"test_sms": handlerTestExternalProvider{}},
		map[string]reliabletask.ProviderPolicy{
			reliabletask.ExternalInteractionOperationSmsOTP: {
				Providers:   []string{"test_sms"},
				Timeout:     time.Second,
				RetryPolicy: reliabletask.DefaultRetryPolicy(),
			},
		},
		handlerTestOTPReferenceStore{},
	)
	if err != nil {
		t.Fatalf("construct external interaction service: %v", err)
	}
	body := []byte(`{
		"requestId":"req-sms-1",
		"operation":"sms_otp.send",
		"tenant":"quwoquan",
		"env":"gamma",
		"idempotencyKey":"otp:fixture",
		"payloadRef":"otp_challenge:ch-1",
		"payloadDigest":"digest",
		"sensitivity":"secret",
		"expiresAt":"2030-01-01T00:00:00Z",
		"payload":{"challengeId":"ch-1","codeRef":"otpref.test","phoneHash":"hash","maskedRecipient":"180****3909"}
	}`)
	req := httptest.NewRequest(http.MethodPost, externalgenerated.ExternalRequestsPath, bytes.NewReader(body))
	recorder := httptest.NewRecorder()
	httpadapter.NewHandler(service).Routes().ServeHTTP(recorder, req)
	if recorder.Code != http.StatusAccepted {
		t.Fatalf("status=%d, want=202 body=%s", recorder.Code, recorder.Body.String())
	}
	if err := service.DispatchDue(context.Background(), 10); err != nil {
		t.Fatalf("dispatch due: %v", err)
	}
	processed, err := service.ProcessOne(context.Background())
	if err != nil {
		t.Fatalf("process one: %v", err)
	}
	if !processed {
		t.Fatal("expected external worker to process one task")
	}
	attempts, err := store.ListProviderAttempts(context.Background(), "req-sms-1")
	if err != nil {
		t.Fatalf("list attempts: %v", err)
	}
	if len(attempts) != 1 || attempts[0].Provider != "test_sms" {
		t.Fatalf("unexpected attempts: %#v", attempts)
	}
}

func TestExternalInteractionControlPlaneUsesCanonicalMemoryStore(t *testing.T) {
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	taskType := reliabletask.TaskTypeForExternalInteraction(
		reliabletask.ExternalInteractionOperationPush,
	)
	memoryStore := reliabletask.NewMemoryStore()
	runtimeStore := canonicalMemoryExternalStore(memoryStore)
	service, err := externalapplication.NewExternalInteractionService(
		runtimeStore,
		map[string]reliabletask.ExternalProvider{"test_sms": handlerTestExternalProvider{}},
		map[string]reliabletask.ProviderPolicy{
			reliabletask.ExternalInteractionOperationPush: {
				Providers:   []string{"test_sms"},
				Timeout:     time.Second,
				RetryPolicy: reliabletask.RetryPolicy{MaxAttempts: 1},
			},
		},
	)
	if err != nil {
		t.Fatalf("construct external interaction service: %v", err)
	}
	handler := httpadapter.NewHandler(service).Routes()
	requestID := "request-control-plane-local-001"
	_, err = runtimeStore.DeclareTask(ctx, reliabletask.DeclareTaskRequest{
		TaskType:       taskType,
		OwnerDomain:    "integration",
		AggregateType:  "external_interaction",
		AggregateID:    requestID,
		DedupeKey:      requestID,
		IdempotencyKey: requestID,
		PartitionKey:   requestID,
		Payload:        map[string]string{"requestId": requestID},
		PayloadAllow:   []string{"requestId"},
		StartAt:        now.Add(-time.Second),
	})
	if err != nil {
		t.Fatalf("declare canonical task: %v", err)
	}

	status, requestState := performLocalExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodGet,
		externalgenerated.ExternalRequestsPath+"/"+requestID,
		nil,
	)
	if status != http.StatusOK || requestState["requestId"] != requestID ||
		requestState["status"] != reliabletask.ExternalInteractionStatusAccepted {
		t.Fatalf("unexpected request state: status=%d body=%#v", status, requestState)
	}

	if _, err := runtimeStore.DispatchDueTasks(ctx, now, 1); err != nil {
		t.Fatalf("dispatch task: %v", err)
	}
	task, err := runtimeStore.ClaimReadyTask(
		ctx,
		[]string{taskType},
		"local-control-plane-test",
		time.Minute,
		now,
	)
	if err != nil || task == nil {
		t.Fatalf("claim task: task=%#v err=%v", task, err)
	}
	if _, err := runtimeStore.RecordProviderAttempt(ctx, reliabletask.ProviderAttemptRecord{
		AttemptID:             "attempt-control-plane-local-001",
		RequestID:             requestID,
		TaskID:                task.TaskID,
		Operation:             reliabletask.ExternalInteractionOperationPush,
		Provider:              "test_sms",
		ProviderRequestDigest: reliabletask.ProviderRequestDigest("provider-request-local-001"),
		Status:                reliabletask.ExternalInteractionStatusFailed,
		NormalizedError:       "provider rejected local fixture",
		Retryable:             false,
		RecoveryAction:        "manual_recover",
		CreatedAt:             now,
	}); err != nil {
		t.Fatalf("record provider attempt: %v", err)
	}
	if err := runtimeStore.FailTask(
		ctx,
		task.TaskID,
		task.LeaseToken,
		reliabletask.RuntimeFailure{
			Code:    "INTEGRATION.MIDDLEWARE.provider_rejected",
			Message: "provider rejected local fixture",
		},
		reliabletask.RetryPolicy{MaxAttempts: 1},
		now.Add(time.Millisecond),
	); err != nil {
		t.Fatalf("dead-letter task: %v", err)
	}

	status, attempts := performLocalExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodGet,
		externalgenerated.ExternalRequestsPath+"/"+requestID+"/attempts",
		nil,
	)
	assertSingleLocalExternalInteractionItem(
		t,
		status,
		attempts,
		"attemptId",
		"attempt-control-plane-local-001",
	)
	deadLettersPath := externalgenerated.ExternalRequestDeadLettersPath + "?requestId=" + requestID
	status, deadLetters := performLocalExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodGet,
		deadLettersPath,
		nil,
	)
	assertSingleLocalExternalInteractionItem(t, status, deadLetters, "taskId", task.TaskID)

	status, metrics := performLocalExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodGet,
		externalgenerated.ExternalRequestMetricsSnapshotPath,
		nil,
	)
	if status != http.StatusOK || metrics["deadTasks"] != float64(1) {
		t.Fatalf("unexpected metrics: status=%d body=%#v", status, metrics)
	}
	status, recovered := performLocalExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodPost,
		externalgenerated.ExternalRequestDeadLetterRecoverPath,
		map[string]any{"taskId": task.TaskID},
	)
	if status != http.StatusAccepted || recovered["taskId"] != task.TaskID ||
		recovered["recovered"] != true {
		t.Fatalf("unexpected recovery: status=%d body=%#v", status, recovered)
	}
}

func performLocalExternalInteractionJSONRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body map[string]any,
) (int, map[string]any) {
	t.Helper()
	var encoded []byte
	if body != nil {
		var err error
		encoded, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("encode request body: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(encoded))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "local-control-plane-test-key")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	decoded := map[string]any{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &decoded); err != nil {
		t.Fatalf("decode response status=%d body=%q: %v", recorder.Code, recorder.Body.String(), err)
	}
	return recorder.Code, decoded
}

func assertSingleLocalExternalInteractionItem(
	t *testing.T,
	status int,
	body map[string]any,
	field string,
	want any,
) {
	t.Helper()
	items, ok := body["items"].([]any)
	if status != http.StatusOK || !ok || len(items) != 1 {
		t.Fatalf("expected one item: status=%d body=%#v", status, body)
	}
	item, ok := items[0].(map[string]any)
	if !ok || item[field] != want {
		t.Fatalf("unexpected item field %s: item=%#v want=%#v", field, items[0], want)
	}
}
