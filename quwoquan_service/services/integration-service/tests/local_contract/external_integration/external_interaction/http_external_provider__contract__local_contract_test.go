package local_contract

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
)

type memoryOTPReferenceStore struct {
	items map[string]otpseal.StoredReference
}

func (s *memoryOTPReferenceStore) Put(_ context.Context, reference otpseal.StoredReference) error {
	if s.items == nil {
		s.items = map[string]otpseal.StoredReference{}
	}
	s.items[reference.RequestID+":"+reference.ChallengeID] = reference
	return nil
}

func (s *memoryOTPReferenceStore) Get(_ context.Context, requestID, challengeID string) (otpseal.StoredReference, error) {
	reference, ok := s.items[requestID+":"+challengeID]
	if !ok {
		return otpseal.StoredReference{}, otpseal.ErrReferenceNotFound
	}
	return reference, nil
}

func (s *memoryOTPReferenceStore) Delete(_ context.Context, requestID, challengeID string) error {
	delete(s.items, requestID+":"+challengeID)
	return nil
}

func smsOTPDependencies(t *testing.T, requestID, challengeID string, expiresAt time.Time) (*otpseal.Sealer, *memoryOTPReferenceStore) {
	t.Helper()
	sealer, err := otpseal.NewFromBase64("test-k1", map[string]string{
		"test-k1": base64.StdEncoding.EncodeToString([]byte("0123456789abcdef0123456789abcdef")),
	})
	if err != nil {
		t.Fatal(err)
	}
	codeRef, err := sealer.Seal(
		otpseal.Secret{Phone: "+8618013813909", Code: "123456"},
		otpseal.Binding{RequestID: requestID, ChallengeID: challengeID, ExpiresAt: expiresAt},
	)
	if err != nil {
		t.Fatal(err)
	}
	store := &memoryOTPReferenceStore{}
	if err := store.Put(context.Background(), otpseal.StoredReference{
		RequestID: requestID, ChallengeID: challengeID, CodeRef: codeRef, ExpiresAt: expiresAt,
	}); err != nil {
		t.Fatal(err)
	}
	return sealer, store
}

func TestHTTPExternalProviderNormalizesAcceptedSMSResponse(t *testing.T) {
	expiresAt := time.Now().UTC().Add(time.Minute)
	sealer, references := smsOTPDependencies(t, "sms-request-001", "challenge-001", expiresAt)
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer provider-token" {
			http.Error(w, "missing provider authorization", http.StatusUnauthorized)
			return
		}
		if r.Header.Get("Idempotency-Key") != "sms-idempotency-001" {
			http.Error(w, "missing idempotency key", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"messageId": "provider-sms-001",
			"status":    "queued",
		})
	}))
	t.Cleanup(upstream.Close)
	externalProvider, err := provider.NewHTTPExternalProvider(
		provider.HTTPExternalProviderConfig{
			Name:              "aliyun_sms",
			Operation:         reliabletask.ExternalInteractionOperationSmsOTP,
			Endpoint:          upstream.URL,
			BearerToken:       "provider-token",
			Timeout:           time.Second,
			OTPCodeSealer:     sealer,
			OTPCodeReferences: references,
		},
		upstream.Client(),
	)
	if err != nil {
		t.Fatalf("construct HTTP provider: %v", err)
	}
	result, err := externalProvider.Send(
		context.Background(),
		reliabletask.ExternalInteractionRequest{
			RequestID:      "sms-request-001",
			Operation:      reliabletask.ExternalInteractionOperationSmsOTP,
			Tenant:         "quwoquan",
			Env:            "gamma",
			IdempotencyKey: "sms-idempotency-001",
			PayloadRef:     "challenge:001",
			PayloadDigest:  "sha256:digest",
			Sensitivity:    "secret",
			ExpiresAt:      expiresAt,
			Payload: map[string]string{
				"challengeId": "challenge-001",
				"templateId":  "sms_otp_login",
			},
		},
		reliabletask.ReliableAsyncTask{TaskID: "task-001"},
	)
	if err != nil {
		t.Fatalf("send HTTP provider request: %v", err)
	}
	if result.Provider != "aliyun_sms" ||
		result.ProviderRequestID != "provider-sms-001" ||
		result.Status != reliabletask.ExternalInteractionStatusSentUnconfirmed {
		t.Fatalf("unexpected normalized result: %+v", result)
	}
}

func TestHTTPExternalProviderNormalizesRemoteFailure(t *testing.T) {
	expiresAt := time.Now().UTC().Add(time.Minute)
	sealer, references := smsOTPDependencies(t, "sms-request-503", "challenge-503", expiresAt)
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "temporary provider failure", http.StatusServiceUnavailable)
	}))
	t.Cleanup(upstream.Close)
	externalProvider, err := provider.NewHTTPExternalProvider(
		provider.HTTPExternalProviderConfig{
			Name:              "aliyun_sms",
			Operation:         reliabletask.ExternalInteractionOperationSmsOTP,
			Endpoint:          upstream.URL,
			BearerToken:       "provider-token",
			Timeout:           time.Second,
			OTPCodeSealer:     sealer,
			OTPCodeReferences: references,
		},
		upstream.Client(),
	)
	if err != nil {
		t.Fatalf("construct HTTP provider: %v", err)
	}
	result, err := externalProvider.Send(
		context.Background(),
		reliabletask.ExternalInteractionRequest{
			RequestID:      "sms-request-503",
			Operation:      reliabletask.ExternalInteractionOperationSmsOTP,
			IdempotencyKey: "sms-idempotency-503",
			ExpiresAt:      expiresAt,
			Payload: map[string]string{
				"challengeId": "challenge-503",
				"phoneHash":   "sha256:phone",
				"templateId":  "sms_otp_login",
			},
		},
		reliabletask.ReliableAsyncTask{TaskID: "task-503"},
	)
	if err == nil {
		t.Fatal("expected provider rejection")
	}
	var providerErr *provider.ExternalProviderError
	if !errors.As(err, &providerErr) {
		t.Fatalf("expected structured ExternalProviderError, got %T: %v", err, err)
	}
	if !providerErr.Retryable || providerErr.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("unexpected provider error: %+v", providerErr)
	}
	if result.Status != reliabletask.ExternalInteractionStatusFailed ||
		result.NormalizedError != "INTEGRATION.MIDDLEWARE.sms_provider_rejected" ||
		!result.Retryable {
		t.Fatalf("unexpected normalized failure result: %+v", result)
	}
}

func TestHTTPExternalProviderFailsClosedWithoutCredentials(t *testing.T) {
	_, err := provider.NewHTTPExternalProvider(
		provider.HTTPExternalProviderConfig{
			Name:      "aliyun_sms",
			Operation: reliabletask.ExternalInteractionOperationSmsOTP,
			Endpoint:  "https://sms.example.invalid/send",
			Timeout:   time.Second,
		},
		http.DefaultClient,
	)
	if err == nil {
		t.Fatal("missing provider token must fail closed")
	}
}

func TestHTTPExternalProviderAcceptsCanonicalLocalCaptureSMSProvider(t *testing.T) {
	expiresAt := time.Now().UTC().Add(time.Minute)
	sealer, references := smsOTPDependencies(
		t,
		"sms-request-local-capture",
		"challenge-local-capture",
		expiresAt,
	)
	_, err := provider.NewHTTPExternalProvider(
		provider.HTTPExternalProviderConfig{
			Name:              "local_capture_sms",
			Operation:         reliabletask.ExternalInteractionOperationSmsOTP,
			Endpoint:          "https://sms-provider-substitute:9443/v1/provider/sms/send",
			BearerToken:       "target-scoped-provider-token",
			Timeout:           time.Second,
			OTPCodeSealer:     sealer,
			OTPCodeReferences: references,
		},
		&http.Client{},
	)
	if err != nil {
		t.Fatalf("canonical local capture SMS provider must be accepted: %v", err)
	}
}

func TestHTTPExternalProviderDoesNotImplementPushDelivery(t *testing.T) {
	_, err := provider.NewHTTPExternalProvider(
		provider.HTTPExternalProviderConfig{
			Name:        "fcm",
			Operation:   reliabletask.ExternalInteractionOperationPush,
			Endpoint:    "https://fcm.googleapis.com/v1/projects/test/messages:send",
			BearerToken: "must-not-enable-generic-push",
			Timeout:     time.Second,
		},
		http.DefaultClient,
	)
	if err == nil {
		t.Fatal("generic bearer-token HTTP provider must not implement push delivery")
	}
}

func TestHTTPExternalProviderRejectsTamperedOTPCodeRefWithoutCallingProvider(t *testing.T) {
	called := false
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		called = true
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(upstream.Close)
	expiresAt := time.Now().UTC().Add(time.Minute)
	sealer, references := smsOTPDependencies(t, "sms-request-tampered", "challenge-tampered", expiresAt)
	reference := references.items["sms-request-tampered:challenge-tampered"]
	replacement := "A"
	if strings.HasSuffix(reference.CodeRef, replacement) {
		replacement = "B"
	}
	reference.CodeRef = reference.CodeRef[:len(reference.CodeRef)-1] + replacement
	references.items["sms-request-tampered:challenge-tampered"] = reference
	externalProvider, err := provider.NewHTTPExternalProvider(
		provider.HTTPExternalProviderConfig{
			Name:              "aliyun_sms",
			Operation:         reliabletask.ExternalInteractionOperationSmsOTP,
			Endpoint:          upstream.URL,
			BearerToken:       "provider-token",
			Timeout:           time.Second,
			OTPCodeSealer:     sealer,
			OTPCodeReferences: references,
		},
		upstream.Client(),
	)
	if err != nil {
		t.Fatal(err)
	}
	result, err := externalProvider.Send(context.Background(), reliabletask.ExternalInteractionRequest{
		RequestID:      "sms-request-tampered",
		Operation:      reliabletask.ExternalInteractionOperationSmsOTP,
		IdempotencyKey: "sms-idempotency-tampered",
		ExpiresAt:      expiresAt,
		Payload: map[string]string{
			"challengeId": "challenge-tampered",
			"templateId":  "sms_otp_login",
		},
	}, reliabletask.ReliableAsyncTask{TaskID: "task-tampered"})
	if err == nil || called {
		t.Fatalf("tampered codeRef must fail before provider call, called=%t err=%v", called, err)
	}
	var providerErr *provider.ExternalProviderError
	if !errors.As(err, &providerErr) || providerErr.Retryable ||
		providerErr.Code != "INTEGRATION.SYSTEM.sms_otp_code_ref_invalid" ||
		result.NormalizedError != providerErr.Code {
		t.Fatalf("unexpected tampered reference result=%+v err=%+v", result, providerErr)
	}
}
