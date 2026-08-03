// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/runtime/reliabletask"
	externalgenerated "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	httpadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/http"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	pushapp "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
)

// TestExternalInteractionControlPlaneReadsCanonicalMongoFacts proves that the
// first-party query and operator routes read and mutate the same Mongo facts
// used by the reliable-task runtime. The local recorder is only the external
// Provider substitute; MongoDB and the HTTP/application/store path are real.
func TestExternalInteractionControlPlaneReadsCanonicalMongoFacts(t *testing.T) {
	resetReliableTaskCollections(t)
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Millisecond)
	taskType := reliabletask.TaskTypeForExternalInteraction(
		reliabletask.ExternalInteractionOperationPush,
	)
	runtimeStore := canonicalMongoExternalStore(t)
	service, err := application.NewExternalInteractionService(
		runtimeStore,
		map[string]reliabletask.ExternalProvider{
			pushapp.PushProviderLocalRecorder: pushapp.LocalRecorderPushProvider{},
		},
		map[string]reliabletask.ProviderPolicy{
			reliabletask.ExternalInteractionOperationPush: {
				Providers:   []string{pushapp.PushProviderLocalRecorder},
				Timeout:     time.Second,
				RetryPolicy: reliabletask.RetryPolicy{MaxAttempts: 1},
			},
		},
	)
	if err != nil {
		t.Fatalf("construct external interaction service: %v", err)
	}
	handler := httpadapter.NewHandler(service).Routes()

	requestID := "request-control-plane-001"
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
		t.Fatalf("declare canonical external interaction task: %v", err)
	}

	status, requestState := performExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodGet,
		externalgenerated.ExternalRequestsPath+"/"+requestID,
		nil,
	)
	if status != http.StatusOK ||
		requestState["requestId"] != requestID ||
		requestState["operation"] != reliabletask.ExternalInteractionOperationPush ||
		requestState["status"] != reliabletask.ExternalInteractionStatusAccepted {
		t.Fatalf("non-canonical external request state: status=%d body=%#v", status, requestState)
	}

	if _, err := runtimeStore.DispatchDueTasks(ctx, now, 1); err != nil {
		t.Fatalf("dispatch canonical external interaction task: %v", err)
	}
	task, err := runtimeStore.ClaimReadyTask(
		ctx,
		[]string{taskType},
		"external-control-plane-test",
		time.Minute,
		now,
	)
	if err != nil || task == nil {
		t.Fatalf("claim external interaction task: task=%#v err=%v", task, err)
	}
	if _, err := runtimeStore.RecordProviderAttempt(ctx, reliabletask.ProviderAttemptRecord{
		AttemptID:             "attempt-control-plane-001",
		RequestID:             requestID,
		TaskID:                task.TaskID,
		Operation:             reliabletask.ExternalInteractionOperationPush,
		Provider:              pushapp.PushProviderLocalRecorder,
		ProviderRequestDigest: reliabletask.ProviderRequestDigest("provider-request-control-plane-001"),
		Status:                reliabletask.ExternalInteractionStatusFailed,
		NormalizedError:       "provider rejected control-plane fixture",
		Retryable:             false,
		RecoveryAction:        "manual_recover",
		CreatedAt:             now,
	}); err != nil {
		t.Fatalf("record canonical provider attempt: %v", err)
	}
	if err := runtimeStore.FailTask(
		ctx,
		task.TaskID,
		task.LeaseToken,
		reliabletask.RuntimeFailure{
			Code:    "INTEGRATION.MIDDLEWARE.provider_rejected",
			Message: "provider rejected control-plane fixture",
		},
		reliabletask.RetryPolicy{MaxAttempts: 1},
		now.Add(time.Millisecond),
	); err != nil {
		t.Fatalf("dead-letter canonical external interaction task: %v", err)
	}

	status, attempts := performExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodGet,
		externalgenerated.ExternalRequestsPath+"/"+requestID+"/attempts",
		nil,
	)
	assertSingleExternalInteractionItem(
		t,
		status,
		attempts,
		"attemptId",
		"attempt-control-plane-001",
	)

	deadLettersPath := externalgenerated.ExternalRequestDeadLettersPath + "?requestId=" + requestID
	status, deadLetters := performExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodGet,
		deadLettersPath,
		nil,
	)
	assertSingleExternalInteractionItem(t, status, deadLetters, "taskId", task.TaskID)

	status, metrics := performExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodGet,
		externalgenerated.ExternalRequestMetricsSnapshotPath,
		nil,
	)
	if status != http.StatusOK || metrics["deadTasks"] != float64(1) {
		t.Fatalf("metrics did not read canonical dead task: status=%d body=%#v", status, metrics)
	}

	status, invalidRecovery := performExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodPost,
		externalgenerated.ExternalRequestDeadLetterRecoverPath,
		map[string]any{"taskId": task.TaskID, "unexpected": true},
	)
	if status != http.StatusBadRequest || invalidRecovery["code"] != "INTEGRATION.USER.invalid_external_request" {
		t.Fatalf("recovery wire must fail closed: status=%d body=%#v", status, invalidRecovery)
	}

	status, recovered := performExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodPost,
		externalgenerated.ExternalRequestDeadLetterRecoverPath,
		map[string]any{"taskId": task.TaskID},
	)
	if status != http.StatusAccepted || recovered["taskId"] != task.TaskID || recovered["recovered"] != true {
		t.Fatalf("dead-letter recovery did not update canonical task: status=%d body=%#v", status, recovered)
	}
	status, replayedRecovery := performExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodPost,
		externalgenerated.ExternalRequestDeadLetterRecoverPath,
		map[string]any{"taskId": task.TaskID},
	)
	if status != http.StatusAccepted ||
		replayedRecovery["taskId"] != task.TaskID ||
		replayedRecovery["recovered"] != true {
		t.Fatalf(
			"dead-letter recovery replay did not return the first receipt: status=%d body=%#v",
			status,
			replayedRecovery,
		)
	}
	receiptCount, err := integrationMongoDB.Collection("reliable_task_recovery_receipts").
		CountDocuments(ctx, map[string]any{"taskId": task.TaskID})
	if err != nil || receiptCount != 1 {
		t.Fatalf("recovery receipt count=%d err=%v", receiptCount, err)
	}
	status, deadLetters = performExternalInteractionJSONRequest(
		t,
		handler,
		http.MethodGet,
		deadLettersPath,
		nil,
	)
	items, ok := deadLetters["items"].([]any)
	if status != http.StatusOK || !ok || len(items) != 1 {
		t.Fatalf("immutable dead-letter fact changed after recovery: status=%d body=%#v", status, deadLetters)
	}
}

func performExternalInteractionJSONRequest(
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
			t.Fatalf("encode HTTP request body: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(encoded))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "control-plane-test-key")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	decoded := map[string]any{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &decoded); err != nil {
		t.Fatalf("decode HTTP response status=%d body=%q: %v", recorder.Code, recorder.Body.String(), err)
	}
	return recorder.Code, decoded
}

func assertSingleExternalInteractionItem(
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
