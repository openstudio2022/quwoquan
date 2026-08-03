package local_contract

import (
	"bytes"
	"context"
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
