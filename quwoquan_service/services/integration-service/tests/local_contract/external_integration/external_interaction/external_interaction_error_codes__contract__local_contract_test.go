package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	externalgenerated "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	httpadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/http"
	externalapplication "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

// failingOTPReferenceStore 注入 OTP 引用存储依赖失败：Put 返回与参数校验
// 无关的基础设施错误，驱动 Submit 落入 internal_error 映射分支。
type failingOTPReferenceStore struct{}

func (failingOTPReferenceStore) Put(context.Context, otpseal.StoredReference) error {
	return errors.New("otp reference outbox is offline")
}

func (failingOTPReferenceStore) Get(context.Context, string, string) (otpseal.StoredReference, error) {
	return otpseal.StoredReference{}, otpseal.ErrReferenceNotFound
}

func (failingOTPReferenceStore) Delete(context.Context, string, string) error { return nil }

func newPushOnlyExternalInteractionService(t *testing.T, store *reliabletask.MemoryStore) *externalapplication.ExternalInteractionService {
	t.Helper()
	service, err := externalapplication.NewExternalInteractionService(
		canonicalMemoryExternalStore(store),
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
		t.Fatalf("construct push-only external interaction service: %v", err)
	}
	return service
}

func performExternalInteractionErrorCodeRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	idempotencyKey string,
	body []byte,
) (int, map[string]any) {
	t.Helper()
	request := httptest.NewRequest(method, path, bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	decoded := map[string]any{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &decoded); err != nil {
		t.Fatalf("decode response status=%d body=%q: %v", recorder.Code, recorder.Body.String(), err)
	}
	return recorder.Code, decoded
}

// 枚举内但未启用 policy 的 operation 必须返回
// INTEGRATION.USER.unsupported_operation，而不是被吞成参数错误或内部错误。
func TestSubmitEnumeratedButDisabledOperationReturnsUnsupportedOperation(t *testing.T) {
	service := newPushOnlyExternalInteractionService(t, reliabletask.NewMemoryStore())
	handler := httpadapter.NewHandler(service).Routes()
	body := []byte(`{
		"requestId":"req-unsupported-001",
		"operation":"sms_otp.send",
		"tenant":"quwoquan",
		"env":"gamma",
		"idempotencyKey":"otp:unsupported-001",
		"payloadRef":"otp_challenge:ch-unsupported-001",
		"payloadDigest":"digest",
		"sensitivity":"secret",
		"expiresAt":"2030-01-01T00:00:00Z",
		"payload":{"challengeId":"ch-unsupported-001","codeRef":"otpref.test","phoneHash":"hash","maskedRecipient":"180****3909"}
	}`)
	status, decoded := performExternalInteractionErrorCodeRequest(
		t,
		handler,
		http.MethodPost,
		externalgenerated.ExternalRequestsPath,
		"",
		body,
	)
	if status != http.StatusBadRequest ||
		decoded["code"] != externalgenerated.ErrUnsupportedOperation.Error() {
		t.Fatalf("disabled operation must map to unsupported_operation: status=%d body=%#v", status, decoded)
	}
}

// OTP 引用存储不可用属于依赖失败，Submit 必须返回
// INTEGRATION.SYSTEM.external_interaction_internal_error 而不是伪装成功。
func TestSubmitOTPReferenceStoreFailureReturnsExternalInteractionInternalError(t *testing.T) {
	service, err := externalapplication.NewExternalInteractionService(
		canonicalMemoryExternalStore(reliabletask.NewMemoryStore()),
		map[string]reliabletask.ExternalProvider{"test_sms": handlerTestExternalProvider{}},
		map[string]reliabletask.ProviderPolicy{
			reliabletask.ExternalInteractionOperationSmsOTP: {
				Providers:   []string{"test_sms"},
				Timeout:     time.Second,
				RetryPolicy: reliabletask.DefaultRetryPolicy(),
			},
		},
		failingOTPReferenceStore{},
	)
	if err != nil {
		t.Fatalf("construct external interaction service: %v", err)
	}
	handler := httpadapter.NewHandler(service).Routes()
	body := []byte(`{
		"requestId":"req-internal-001",
		"operation":"sms_otp.send",
		"tenant":"quwoquan",
		"env":"gamma",
		"idempotencyKey":"otp:internal-001",
		"payloadRef":"otp_challenge:ch-internal-001",
		"payloadDigest":"digest",
		"sensitivity":"secret",
		"expiresAt":"2030-01-01T00:00:00Z",
		"payload":{"challengeId":"ch-internal-001","codeRef":"otpref.test","phoneHash":"hash","maskedRecipient":"180****3909"}
	}`)
	status, decoded := performExternalInteractionErrorCodeRequest(
		t,
		handler,
		http.MethodPost,
		externalgenerated.ExternalRequestsPath,
		"",
		body,
	)
	if status != http.StatusInternalServerError ||
		decoded["code"] != externalgenerated.ErrExternalInteractionInternalError.Error() {
		t.Fatalf("reference store outage must map to internal error: status=%d body=%#v", status, decoded)
	}
}

// 同一 Idempotency-Key 被绑定到另一个 dead task 后重复恢复必须返回
// INTEGRATION.USER.dead_letter_recovery_conflict（HTTP 409），不得覆盖已确认回执。
func TestRecoverDeadLetterIdempotencyKeyBoundToAnotherTaskReturnsConflict(t *testing.T) {
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

	deadTaskIDs := make([]string, 0, 2)
	for _, requestID := range []string{
		"request-recovery-conflict-001",
		"request-recovery-conflict-002",
	} {
		if _, err := runtimeStore.DeclareTask(ctx, reliabletask.DeclareTaskRequest{
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
		}); err != nil {
			t.Fatalf("declare canonical task %s: %v", requestID, err)
		}
	}
	if _, err := runtimeStore.DispatchDueTasks(ctx, now, 2); err != nil {
		t.Fatalf("dispatch tasks: %v", err)
	}
	for attemptIndex := range 2 {
		task, err := runtimeStore.ClaimReadyTask(
			ctx,
			[]string{taskType},
			"local-recovery-conflict-test",
			time.Minute,
			now,
		)
		if err != nil || task == nil {
			t.Fatalf("claim task: task=%#v err=%v", task, err)
		}
		if _, err := runtimeStore.RecordProviderAttempt(ctx, reliabletask.ProviderAttemptRecord{
			AttemptID:             "attempt-recovery-conflict-00" + string(rune('1'+attemptIndex)),
			RequestID:             task.AggregateID,
			TaskID:                task.TaskID,
			Operation:             reliabletask.ExternalInteractionOperationPush,
			Provider:              "test_sms",
			ProviderRequestDigest: reliabletask.ProviderRequestDigest("provider-request-recovery-conflict"),
			Status:                reliabletask.ExternalInteractionStatusFailed,
			NormalizedError:       "provider rejected recovery-conflict fixture",
			Retryable:             false,
			RecoveryAction:        "manual_recover",
			CreatedAt:             now,
		}); err != nil {
			t.Fatalf("record provider attempt for %s: %v", task.TaskID, err)
		}
		if err := runtimeStore.FailTask(
			ctx,
			task.TaskID,
			task.LeaseToken,
			reliabletask.RuntimeFailure{
				Code:    "INTEGRATION.MIDDLEWARE.provider_rejected",
				Message: "provider rejected recovery-conflict fixture",
			},
			reliabletask.RetryPolicy{MaxAttempts: 1},
			now.Add(time.Millisecond),
		); err != nil {
			t.Fatalf("dead-letter task %s: %v", task.TaskID, err)
		}
		deadTaskIDs = append(deadTaskIDs, task.TaskID)
	}

	const recoveryKey = "recovery-conflict-shared-key"
	firstBody, err := json.Marshal(map[string]any{"taskId": deadTaskIDs[0]})
	if err != nil {
		t.Fatalf("encode first recovery body: %v", err)
	}
	status, recovered := performExternalInteractionErrorCodeRequest(
		t,
		handler,
		http.MethodPost,
		externalgenerated.ExternalRequestDeadLetterRecoverPath,
		recoveryKey,
		firstBody,
	)
	if status != http.StatusAccepted || recovered["recovered"] != true {
		t.Fatalf("first recovery must succeed: status=%d body=%#v", status, recovered)
	}

	secondBody, err := json.Marshal(map[string]any{"taskId": deadTaskIDs[1]})
	if err != nil {
		t.Fatalf("encode second recovery body: %v", err)
	}
	status, conflict := performExternalInteractionErrorCodeRequest(
		t,
		handler,
		http.MethodPost,
		externalgenerated.ExternalRequestDeadLetterRecoverPath,
		recoveryKey,
		secondBody,
	)
	if status != http.StatusConflict ||
		conflict["code"] != externalgenerated.ErrDeadLetterRecoveryConflict.Error() {
		t.Fatalf("reused idempotency key must map to recovery conflict: status=%d body=%#v", status, conflict)
	}
}

// 短信投递就绪状态只对已验证的 user-service principal 可读。缺少 principal 或
// 换成别的调用方都必须返回 INTEGRATION.USER.external_interaction_readiness_forbidden
// （HTTP 403），不得退化成 unauthenticated、internal_error 或泄露就绪结果。
func TestReadinessWithoutVerifiedUserServicePrincipalReturnsForbidden(t *testing.T) {
	service := newPushOnlyExternalInteractionService(t, reliabletask.NewMemoryStore())
	readiness := externalapplication.NewSmsOtpDeliveryReadinessQueryFacade(
		&readinessProbe{},
		&readinessRelay{},
	)
	handler := httpadapter.NewHandler(service, readiness).Routes()

	for _, principal := range []string{"", "service:content-service", "user:42"} {
		request := httptest.NewRequest(
			http.MethodGet,
			externalgenerated.SmsOtpDeliveryReadinessPath,
			nil,
		)
		if principal != "" {
			request = request.WithContext(rtauth.WithPrincipal(
				request.Context(),
				rtauth.Principal{Claims: rtauth.Claims{Subject: principal}},
			))
		}
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		decoded := map[string]any{}
		if err := json.Unmarshal(recorder.Body.Bytes(), &decoded); err != nil {
			t.Fatalf("principal=%q decode body=%q: %v", principal, recorder.Body.String(), err)
		}
		if recorder.Code != http.StatusForbidden ||
			decoded["code"] != externalgenerated.ErrExternalInteractionReadinessForbidden.Error() {
			t.Fatalf(
				"principal=%q must map to readiness_forbidden: status=%d body=%#v",
				principal,
				recorder.Code,
				decoded,
			)
		}
		if _, leaked := decoded["availability"]; leaked {
			t.Fatalf("principal=%q must not leak readiness result: body=%#v", principal, decoded)
		}
	}
}
