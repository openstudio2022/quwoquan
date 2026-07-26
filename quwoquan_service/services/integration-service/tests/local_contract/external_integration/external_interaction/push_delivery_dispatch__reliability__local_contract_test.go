package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	serviceclients "quwoquan_service/generated/serviceclients"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/generated/external_integration/push_delivery"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
)

const localContractEndpointRef = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

type fixedAuthorization string

func (a fixedAuthorization) AuthorizationHeader(context.Context) (string, error) {
	return string(a), nil
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return f(request)
}

type senderFunc func(
	context.Context,
	string,
	application.PushDeliveryMessage,
) (application.PushSendReceipt, error)

func (f senderFunc) SendPush(
	ctx context.Context,
	token string,
	message application.PushDeliveryMessage,
) (application.PushSendReceipt, error) {
	return f(ctx, token, message)
}

type staticEndpointAccess struct {
	kind          string
	token         string
	invalidations atomic.Int32
}

func (s *staticEndpointAccess) ResolvePushEndpointSecret(
	_ context.Context,
	endpointRef string,
) (application.PushEndpointSecret, error) {
	return application.PushEndpointSecret{
		EndpointRef:  endpointRef,
		EndpointKind: s.kind,
		Token:        s.token,
	}, nil
}

func (s *staticEndpointAccess) InvalidatePushEndpoint(
	context.Context,
	string,
	string,
	string,
) error {
	s.invalidations.Add(1)
	return nil
}

func TestPushDispatchProviderRoutesExactlyByEndpointKind(t *testing.T) {
	var apnsCalls atomic.Int32
	var fcmCalls atomic.Int32
	apns := senderFunc(func(
		context.Context,
		string,
		application.PushDeliveryMessage,
	) (application.PushSendReceipt, error) {
		apnsCalls.Add(1)
		return application.PushSendReceipt{ProviderRequestID: "apns-id"}, nil
	})
	fcm := senderFunc(func(
		context.Context,
		string,
		application.PushDeliveryMessage,
	) (application.PushSendReceipt, error) {
		fcmCalls.Add(1)
		return application.PushSendReceipt{ProviderRequestID: "fcm-id"}, nil
	})
	for _, testCase := range []struct {
		kind     string
		wantAPNs int32
		wantFCM  int32
	}{
		{kind: application.PushEndpointKindAPNSVoIP, wantAPNs: 1},
		{kind: application.PushEndpointKindFCM, wantAPNs: 1, wantFCM: 1},
	} {
		access := &staticEndpointAccess{kind: testCase.kind, token: "transient-token"}
		dispatch, err := application.NewPushDispatchProvider(
			access,
			access,
			apns,
			fcm,
			slog.New(slog.NewTextHandler(&bytes.Buffer{}, nil)),
		)
		if err != nil {
			t.Fatal(err)
		}
		result, err := dispatch.Send(
			context.Background(),
			pushRequest(time.Now().UTC().Add(2*time.Minute)),
			reliabletask.ReliableAsyncTask{TaskID: "task-route"},
		)
		if err != nil {
			t.Fatalf("dispatch %s: %v", testCase.kind, err)
		}
		if result.Provider != testCase.kind ||
			result.Status != reliabletask.ExternalInteractionStatusSentUnconfirmed {
			t.Fatalf("unexpected dispatch result: %+v", result)
		}
		if apnsCalls.Load() != testCase.wantAPNs || fcmCalls.Load() != testCase.wantFCM {
			t.Fatalf(
				"kind=%s routed APNs=%d FCM=%d",
				testCase.kind,
				apnsCalls.Load(),
				fcmCalls.Load(),
			)
		}
	}
}

func TestPushTransportErrorRedactsSecretURL(t *testing.T) {
	const token = "plaintext-device-token-in-url"
	request, err := http.NewRequest(
		http.MethodPost,
		"https://api.push.apple.com/3/device/"+token,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	transport := provider.RedactingRoundTripper{
		Base: roundTripFunc(func(request *http.Request) (*http.Response, error) {
			return nil, errors.New(request.URL.String())
		}),
	}
	_, transportErr := transport.RoundTrip(request)
	if transportErr == nil || strings.Contains(transportErr.Error(), token) {
		t.Fatalf("transport error leaked token: %v", transportErr)
	}
}

func TestUserPushEndpointClientAcceptsServiceAuthenticatedInternalHTTP(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		calls.Add(1)
		wantPath := strings.ReplaceAll(
			serviceclients.UserPushEndpointSecretPathTemplate,
			"{endpointRef}",
			localContractEndpointRef,
		)
		if request.Method != http.MethodGet || request.URL.Path != wantPath {
			t.Errorf("unexpected user-service request %s %s", request.Method, request.URL.Path)
		}
		if request.Header.Get("Authorization") != "Bearer service-credential" {
			t.Errorf("internal HTTP request is missing service authorization")
		}
		if request.Header.Get("Cache-Control") != "no-store" {
			t.Errorf("push endpoint secret request must disable caches")
		}
		_ = json.NewEncoder(writer).Encode(map[string]string{
			"endpointRef":  localContractEndpointRef,
			"endpointKind": application.PushEndpointKindFCM,
			"token":        "transient-fcm-token",
		})
	}))
	t.Cleanup(server.Close)

	client, err := provider.NewUserPushEndpointClient(
		provider.UserPushEndpointClientConfig{
			BaseURL:     server.URL,
			Credentials: fixedAuthorization("Bearer service-credential"),
			Timeout:     time.Second,
		},
		server.Client(),
	)
	if err != nil {
		t.Fatalf("loopback internal HTTP must be accepted: %v", err)
	}
	secret, err := client.ResolvePushEndpointSecret(
		context.Background(),
		localContractEndpointRef,
	)
	if err != nil {
		t.Fatalf("resolve endpoint over authenticated internal HTTP: %v", err)
	}
	if secret.EndpointKind != application.PushEndpointKindFCM ||
		secret.Token != "transient-fcm-token" ||
		calls.Load() != 1 {
		t.Fatalf(
			"unexpected endpoint metadata kind=%q calls=%d",
			secret.EndpointKind,
			calls.Load(),
		)
	}

	for _, internalOrigin := range []string{
		"http://user-service:18082",
		"http://user-service.default.svc:18082",
		"http://user-service.default.svc.cluster.local:18082",
		"https://user-service.internal:18082",
	} {
		if _, err := provider.NewUserPushEndpointClient(
			provider.UserPushEndpointClientConfig{
				BaseURL:     internalOrigin,
				Credentials: fixedAuthorization("Bearer service-credential"),
				Timeout:     time.Second,
			},
			http.DefaultClient,
		); err != nil {
			t.Errorf("trusted internal origin %q must be accepted: %v", internalOrigin, err)
		}
	}
}

func TestUserPushEndpointClientRejectsPublicPlainHTTPAndNonOrigins(t *testing.T) {
	for _, rawURL := range []string{
		"http://api.example.com",
		"http://198.51.100.10:18082",
		"http://10.0.0.8:18082",
		"http://user-service.evil.example:18082",
		"http://user:secret@user-service:18082",
		"http://user-service:18082/internal",
		"http://user-service:18082?mode=compat",
		"http://user-service:18082#fragment",
	} {
		if _, err := provider.NewUserPushEndpointClient(
			provider.UserPushEndpointClientConfig{
				BaseURL:     rawURL,
				Credentials: fixedAuthorization("Bearer service-credential"),
				Timeout:     time.Second,
			},
			http.DefaultClient,
		); err == nil {
			t.Errorf("untrusted user-service origin %q must be rejected", rawURL)
		}
	}
}

func TestPushPermanentProviderErrorInvalidatesEndpointWithoutFallback(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	_, keyFile := writeTemporaryECKey(t)
	var fcmCalls atomic.Int32
	var invalidations atomic.Int32
	const endpointToken = "apns-transient-secret-token"
	userServer := newHTTP2TLSServer(t, http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		if request.ProtoMajor != 2 {
			t.Errorf("user-service request must use HTTP/2")
		}
		if request.Header.Get("Authorization") != "Bearer service-credential" {
			t.Errorf("missing service credential")
		}
		switch {
		case request.Method == http.MethodGet &&
			request.URL.Path == strings.ReplaceAll(
				serviceclients.UserPushEndpointSecretPathTemplate,
				"{endpointRef}",
				localContractEndpointRef,
			):
			if request.Header.Get("Cache-Control") != "no-store" {
				t.Errorf("push endpoint secret request must disable caches")
			}
			_ = json.NewEncoder(w).Encode(map[string]string{
				"endpointRef":  localContractEndpointRef,
				"endpointKind": application.PushEndpointKindAPNSVoIP,
				"token":        endpointToken,
			})
		case request.Method == http.MethodPost &&
			request.URL.Path == strings.ReplaceAll(
				serviceclients.UserPushEndpointInvalidatePathTemplate,
				"{endpointRef}",
				localContractEndpointRef,
			):
			invalidations.Add(1)
			var body struct {
				Reason string `json:"reason"`
			}
			_ = json.NewDecoder(request.Body).Decode(&body)
			if body.Reason != generated.ErrPushEndpointPermanentlyInvalid.Error() {
				t.Errorf("unexpected invalidation body: %+v", body)
			}
			w.WriteHeader(http.StatusNoContent)
		default:
			http.NotFound(w, request)
		}
	}))
	apnsServer := newHTTP2TLSServer(t, http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		if !strings.HasSuffix(request.URL.Path, "/"+endpointToken) {
			t.Errorf("APNs did not receive resolved token")
		}
		w.WriteHeader(http.StatusGone)
		_ = json.NewEncoder(w).Encode(map[string]string{"reason": "Unregistered"})
	}))
	endpointClient, err := provider.NewUserPushEndpointClient(
		provider.UserPushEndpointClientConfig{
			BaseURL:     userServer.URL,
			Credentials: fixedAuthorization("Bearer service-credential"),
			Timeout:     time.Second,
		},
		userServer.Client(),
	)
	if err != nil {
		t.Fatal(err)
	}
	apns, err := provider.NewAPNsVoIPProvider(provider.APNsVoIPConfig{
		Environment: provider.APNsEnvironmentSandbox,
		KeyFile:     keyFile,
		KeyID:       "APNSKEY01",
		TeamID:      "TEAM000001",
		Topic:       "com.quwoquan.app.voip",
		Timeout:     time.Second,
		BaseURL:     apnsServer.URL,
		Now:         func() time.Time { return now },
	}, apnsServer.Client())
	if err != nil {
		t.Fatal(err)
	}
	fcm := senderFunc(func(
		context.Context,
		string,
		application.PushDeliveryMessage,
	) (application.PushSendReceipt, error) {
		fcmCalls.Add(1)
		return application.PushSendReceipt{ProviderRequestID: "must-not-run"}, nil
	})
	var logs bytes.Buffer
	dispatch, err := application.NewPushDispatchProvider(
		endpointClient,
		endpointClient,
		apns,
		fcm,
		slog.New(slog.NewJSONHandler(&logs, nil)),
	)
	if err != nil {
		t.Fatal(err)
	}
	result, sendErr := dispatch.Send(
		context.Background(),
		pushRequest(now.Add(2*time.Minute)),
		reliabletask.ReliableAsyncTask{TaskID: "task-permanent"},
	)
	if sendErr == nil {
		t.Fatal("expected permanent APNs failure")
	}
	var failure *application.PushProviderFailure
	if !errors.As(sendErr, &failure) ||
		failure.Retryable ||
		!failure.PermanentEndpoint ||
		failure.Code != generated.ErrPushEndpointPermanentlyInvalid.Error() {
		t.Fatalf("unexpected permanent failure: %+v", failure)
	}
	if result.Retryable || result.Provider != application.PushEndpointKindAPNSVoIP {
		t.Fatalf("unexpected failure result: %+v", result)
	}
	if invalidations.Load() != 1 || fcmCalls.Load() != 0 {
		t.Fatalf(
			"permanent failure invalidations=%d fcmFallbackCalls=%d",
			invalidations.Load(),
			fcmCalls.Load(),
		)
	}
	if strings.Contains(logs.String(), endpointToken) ||
		strings.Contains(logs.String(), localContractEndpointRef) ||
		strings.Contains(sendErr.Error(), endpointToken) {
		t.Fatalf("secret or raw endpointRef leaked: logs=%s err=%v", logs.String(), sendErr)
	}
}

func TestAPNs5xxIsRetryableWithoutFallbackOrInvalidation(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	_, keyFile := writeTemporaryECKey(t)
	apnsServer := newHTTP2TLSServer(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
		_ = json.NewEncoder(w).Encode(map[string]string{"reason": "ServiceUnavailable"})
	}))
	apns, err := provider.NewAPNsVoIPProvider(provider.APNsVoIPConfig{
		Environment: provider.APNsEnvironmentSandbox,
		KeyFile:     keyFile,
		KeyID:       "APNSKEY01",
		TeamID:      "TEAM000001",
		Topic:       "com.quwoquan.app.voip",
		Timeout:     time.Second,
		BaseURL:     apnsServer.URL,
		Now:         func() time.Time { return now },
	}, apnsServer.Client())
	if err != nil {
		t.Fatal(err)
	}
	access := &staticEndpointAccess{
		kind:  application.PushEndpointKindAPNSVoIP,
		token: "apns-retry-token",
	}
	var fcmCalls atomic.Int32
	dispatch, err := application.NewPushDispatchProvider(
		access,
		access,
		apns,
		senderFunc(func(
			context.Context,
			string,
			application.PushDeliveryMessage,
		) (application.PushSendReceipt, error) {
			fcmCalls.Add(1)
			return application.PushSendReceipt{}, nil
		}),
		slog.New(slog.NewTextHandler(&bytes.Buffer{}, nil)),
	)
	if err != nil {
		t.Fatal(err)
	}
	_, sendErr := dispatch.Send(
		context.Background(),
		pushRequest(now.Add(2*time.Minute)),
		reliabletask.ReliableAsyncTask{TaskID: "task-apns-503"},
	)
	var failure *application.PushProviderFailure
	if !errors.As(sendErr, &failure) ||
		!failure.Retryable ||
		failure.PermanentEndpoint ||
		failure.Code != generated.ErrPushProviderRejected.Error() ||
		access.invalidations.Load() != 0 ||
		fcmCalls.Load() != 0 {
		t.Fatalf(
			"APNs 5xx classification=%+v invalidations=%d fallback=%d",
			failure,
			access.invalidations.Load(),
			fcmCalls.Load(),
		)
	}
}

func TestFCMUNREGISTEREDIsPermanentAnd429IsRetryable(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	key := writeTemporaryRSAKey(t)
	var providerStatus atomic.Int32
	providerStatus.Store(http.StatusNotFound)
	server := newHTTP2TLSServer(t, http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/token":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"access_token": "oauth-token",
				"token_type":   "Bearer",
				"expires_in":   3600,
			})
		case "/v1/projects/qwq-test/messages:send":
			status := int(providerStatus.Load())
			w.WriteHeader(status)
			if status == http.StatusNotFound {
				_ = json.NewEncoder(w).Encode(map[string]any{
					"error": map[string]any{
						"status":  "NOT_FOUND",
						"details": []map[string]string{{"errorCode": "UNREGISTERED"}},
					},
				})
			}
		default:
			http.NotFound(w, request)
		}
	}))
	fcm, err := provider.NewFCMProvider(provider.FCMConfig{
		ServiceAccountFile: writeServiceAccountFile(t, key, server.URL+"/token"),
		ProjectID:          "qwq-test",
		Timeout:            time.Second,
		APIBaseURL:         server.URL,
		Now:                func() time.Time { return now },
	}, server.Client())
	if err != nil {
		t.Fatal(err)
	}
	access := &staticEndpointAccess{
		kind:  application.PushEndpointKindFCM,
		token: "fcm-transient-token",
	}
	var apnsCalls atomic.Int32
	dispatch, err := application.NewPushDispatchProvider(
		access,
		access,
		senderFunc(func(
			context.Context,
			string,
			application.PushDeliveryMessage,
		) (application.PushSendReceipt, error) {
			apnsCalls.Add(1)
			return application.PushSendReceipt{}, nil
		}),
		fcm,
		slog.New(slog.NewTextHandler(&bytes.Buffer{}, nil)),
	)
	if err != nil {
		t.Fatal(err)
	}
	_, permanentErr := dispatch.Send(
		context.Background(),
		pushRequest(now.Add(2*time.Minute)),
		reliabletask.ReliableAsyncTask{TaskID: "task-fcm-unregistered"},
	)
	var permanent *application.PushProviderFailure
	if !errors.As(permanentErr, &permanent) || !permanent.PermanentEndpoint ||
		permanent.Retryable || access.invalidations.Load() != 1 || apnsCalls.Load() != 0 {
		t.Fatalf(
			"UNREGISTERED classification=%+v invalidations=%d apns=%d",
			permanent,
			access.invalidations.Load(),
			apnsCalls.Load(),
		)
	}

	providerStatus.Store(http.StatusTooManyRequests)
	_, retryErr := dispatch.Send(
		context.Background(),
		pushRequest(now.Add(2*time.Minute)),
		reliabletask.ReliableAsyncTask{TaskID: "task-fcm-rate-limit"},
	)
	var retryable *application.PushProviderFailure
	if !errors.As(retryErr, &retryable) ||
		!retryable.Retryable ||
		retryable.PermanentEndpoint ||
		retryable.Code != generated.ErrPushProviderRateLimited.Error() ||
		access.invalidations.Load() != 1 ||
		apnsCalls.Load() != 0 {
		t.Fatalf("429 classification=%+v invalidations=%d", retryable, access.invalidations.Load())
	}
}

func pushRequest(expiresAt time.Time) reliabletask.ExternalInteractionRequest {
	return reliabletask.ExternalInteractionRequest{
		RequestID:      "push-request-001",
		Operation:      reliabletask.ExternalInteractionOperationPush,
		Tenant:         "quwoquan",
		Env:            "gamma",
		IdempotencyKey: "delivery-001",
		ExpiresAt:      expiresAt.UTC(),
		Payload: map[string]string{
			"action":          application.PushDeliveryActionRing,
			"endpointRef":     localContractEndpointRef,
			"deliveryKey":     "delivery-001",
			"callId":          "call-001",
			"targetPersonaId": "persona-target-001",
			"callType":        "audio",
			"callerName":      "来电用户",
			"sourceLabel":     "契约会话",
			"trustRelation":   "known",
			"expiresAt":       expiresAt.UTC().Format(time.RFC3339),
			"occurredAt":      time.Now().UTC().Add(-time.Second).Format(time.RFC3339),
		},
	}
}
