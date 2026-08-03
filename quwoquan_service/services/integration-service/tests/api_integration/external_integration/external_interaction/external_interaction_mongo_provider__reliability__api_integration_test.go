package api_integration

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/reliabletaskmongo"
	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
)

type callbackRecorder struct{}

func (callbackRecorder) SendExternalInteractionResult(
	context.Context,
	reliabletask.ExternalInteractionResult,
) error {
	return nil
}

type providerSpy struct {
	mu            sync.Mutex
	requests      []map[string]any
	authorization []string
}

func (s *providerSpy) handler(w http.ResponseWriter, r *http.Request) {
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	s.mu.Lock()
	s.requests = append(s.requests, body)
	s.authorization = append(s.authorization, r.Header.Get("Authorization"))
	s.mu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"providerRequestId": "aliyun-message-001",
		"status":            "sent_unconfirmed",
	})
}

func (s *providerSpy) snapshot() ([]map[string]any, []string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	requests := append([]map[string]any(nil), s.requests...)
	authorization := append([]string(nil), s.authorization...)
	return requests, authorization
}

func TestExternalInteractionPersistsIdempotentlyAndRecordsProviderAttempt(t *testing.T) {
	resetReliableTaskCollections(t)
	spy := &providerSpy{}
	upstream := httptest.NewTLSServer(http.HandlerFunc(spy.handler))
	t.Cleanup(upstream.Close)
	expiresAt := time.Now().UTC().Add(5 * time.Minute)
	sealer, err := otpseal.NewFromBase64("test-k1", map[string]string{
		"test-k1": base64.StdEncoding.EncodeToString([]byte("0123456789abcdef0123456789abcdef")),
	})
	if err != nil {
		t.Fatal(err)
	}
	references := provider.NewMongoOTPCodeReferenceStore(integrationMongoDB)
	if err := references.EnsureIndexes(context.Background()); err != nil {
		t.Fatal(err)
	}
	codeRef, err := sealer.Seal(
		otpseal.Secret{Phone: "+8618013813909", Code: "123456"},
		otpseal.Binding{
			RequestID:   "req-real-sms-001",
			ChallengeID: "challenge-real-001",
			ExpiresAt:   expiresAt,
		},
	)
	if err != nil {
		t.Fatal(err)
	}

	smsProvider, err := provider.NewHTTPExternalProvider(
		provider.HTTPExternalProviderConfig{
			Name:              "aliyun_sms",
			Operation:         reliabletask.ExternalInteractionOperationSmsOTP,
			Endpoint:          upstream.URL,
			BearerToken:       "provider-secret",
			Timeout:           2 * time.Second,
			OTPCodeSealer:     sealer,
			OTPCodeReferences: references,
		},
		upstream.Client(),
	)
	if err != nil {
		t.Fatalf("construct real HTTP SMS provider: %v", err)
	}
	policies := map[string]reliabletask.ProviderPolicy{
		reliabletask.ExternalInteractionOperationSmsOTP: {
			Providers:   []string{"aliyun_sms"},
			Timeout:     2 * time.Second,
			RetryPolicy: reliabletask.DefaultRetryPolicy(),
		},
	}
	service, err := application.NewExternalInteractionService(
		canonicalMongoExternalStore(t),
		map[string]reliabletask.ExternalProvider{"aliyun_sms": smsProvider},
		policies,
		references,
	)
	if err != nil {
		t.Fatalf("construct external interaction service: %v", err)
	}

	request := reliabletask.ExternalInteractionRequest{
		RequestID:      "req-real-sms-001",
		Operation:      reliabletask.ExternalInteractionOperationSmsOTP,
		Tenant:         "quwoquan",
		Env:            "gamma",
		IdempotencyKey: "otp:challenge-real-001",
		PayloadRef:     "otp_challenge:challenge-real-001",
		PayloadDigest:  "sha256:masked",
		Sensitivity:    "secret",
		ExpiresAt:      expiresAt,
		Payload: map[string]string{
			"challengeId":     "challenge-real-001",
			"codeRef":         codeRef,
			"phoneHash":       "sha256:phone",
			"maskedRecipient": "180****3909",
			"templateId":      "sms_otp_login",
		},
	}
	first, err := service.Submit(context.Background(), request)
	if err != nil {
		t.Fatalf("submit first external request: %v", err)
	}
	second, err := service.Submit(context.Background(), request)
	if err != nil {
		t.Fatalf("submit idempotent external request: %v", err)
	}
	if first.RequestID != request.RequestID || second.RequestID != request.RequestID {
		t.Fatalf("unexpected accepted IDs: first=%+v second=%+v", first, second)
	}
	outboxCount, err := integrationMongoDB.Collection("reliable_task_outbox").CountDocuments(
		context.Background(),
		bson.M{"idempotencyKey": request.IdempotencyKey},
	)
	if err != nil {
		t.Fatalf("count persisted reliable outbox: %v", err)
	}
	if outboxCount != 1 {
		t.Fatalf("idempotency must persist one outbox row, got %d", outboxCount)
	}
	var outboxDocument bson.M
	if err := integrationMongoDB.Collection("reliable_task_outbox").FindOne(
		context.Background(),
		bson.M{"idempotencyKey": request.IdempotencyKey},
	).Decode(&outboxDocument); err != nil {
		t.Fatalf("read persisted reliable outbox: %v", err)
	}
	if strings.Contains(fmt.Sprint(outboxDocument), "codeRef") ||
		strings.Contains(fmt.Sprint(outboxDocument), codeRef) ||
		strings.Contains(fmt.Sprint(outboxDocument), "123456") ||
		strings.Contains(fmt.Sprint(outboxDocument), "+8618013813909") {
		t.Fatalf("outbox leaked OTP secret material: %+v", outboxDocument)
	}

	reopenedStore := reliabletaskmongo.NewExternalInteraction(integrationMongoDB)
	reopenedService, err := application.NewExternalInteractionService(
		canonicalMongoExternalStoreFrom(t, reopenedStore),
		map[string]reliabletask.ExternalProvider{"aliyun_sms": smsProvider},
		policies,
		references,
	)
	if err != nil {
		t.Fatalf("reopen external interaction service: %v", err)
	}
	if err := reopenedService.DispatchDue(context.Background(), 10); err != nil {
		t.Fatalf("dispatch persisted external request: %v", err)
	}
	processed, err := reopenedService.ProcessOne(context.Background())
	if err != nil {
		t.Fatalf("process persisted external request: %v", err)
	}
	if !processed {
		t.Fatal("expected persisted external request to be processed")
	}

	requests, authorization := spy.snapshot()
	if len(requests) != 1 {
		t.Fatalf("provider must be called exactly once, got %d", len(requests))
	}
	if authorization[0] != "Bearer provider-secret" {
		t.Fatalf("provider authorization header not injected: %q", authorization[0])
	}
	if requests[0]["requestId"] != request.RequestID ||
		requests[0]["operation"] != reliabletask.ExternalInteractionOperationSmsOTP {
		t.Fatalf("provider request was not normalized: %+v", requests[0])
	}
	providerPayload, _ := requests[0]["payload"].(map[string]any)
	if providerPayload["recipient"] != "+8618013813909" ||
		providerPayload["code"] != "123456" ||
		providerPayload["templateId"] != "sms_otp_login" ||
		strings.Contains(fmt.Sprint(requests[0]), "codeRef") {
		t.Fatalf("provider request did not use transient decrypted payload: %+v", requests[0])
	}

	attempts, err := reopenedService.ListAttempts(context.Background(), request.RequestID)
	if err != nil {
		t.Fatalf("read persisted provider attempt ledger: %v", err)
	}
	if len(attempts) != 1 {
		t.Fatalf("expected one provider attempt, got %+v", attempts)
	}
	if attempts[0].Provider != "aliyun_sms" ||
		attempts[0].ProviderRequestID != "aliyun-message-001" ||
		attempts[0].Status != reliabletask.ExternalInteractionStatusSentUnconfirmed {
		t.Fatalf("unexpected provider attempt: %+v", attempts[0])
	}
	taskCount, err := integrationMongoDB.Collection("reliable_async_task").CountDocuments(
		context.Background(),
		bson.M{
			"aggregateId": request.RequestID,
			"status":      reliabletask.TaskStatusSucceeded,
		},
	)
	if err != nil {
		t.Fatalf("count completed reliable task: %v", err)
	}
	if taskCount != 1 {
		t.Fatalf("persisted task must complete exactly once, got %d", taskCount)
	}
}
