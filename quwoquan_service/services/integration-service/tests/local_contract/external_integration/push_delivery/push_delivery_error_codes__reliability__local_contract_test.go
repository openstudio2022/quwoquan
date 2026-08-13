package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/generated/external_integration/push_delivery"
	"quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
	"quwoquan_service/services/integration-service/internal/external_integration/push_delivery/infrastructure/provider"
)

// resolutionFailingEndpointAccess 注入 user-service endpoint 解析失败：
// Resolve 返回非结构化基础设施错误，驱动 dispatch 落入默认 resolution_failed 分类。
type resolutionFailingEndpointAccess struct {
	invalidations atomic.Int32
}

func (r *resolutionFailingEndpointAccess) ResolvePushEndpointSecret(
	context.Context,
	string,
) (application.PushEndpointSecret, error) {
	return application.PushEndpointSecret{}, errors.New("user-service endpoint lookup is offline")
}

func (r *resolutionFailingEndpointAccess) InvalidatePushEndpoint(
	context.Context,
	string,
	string,
	string,
) error {
	r.invalidations.Add(1)
	return nil
}

// invalidationFailingEndpointAccess 解析成功但失效回写失败，
// 驱动 dispatch 记录 push_endpoint_invalidation_failed 而不中断原始失败分类。
type invalidationFailingEndpointAccess struct {
	kind          string
	token         string
	invalidations atomic.Int32
}

func (s *invalidationFailingEndpointAccess) ResolvePushEndpointSecret(
	_ context.Context,
	endpointRef string,
) (application.PushEndpointSecret, error) {
	return application.PushEndpointSecret{
		EndpointRef:  endpointRef,
		EndpointKind: s.kind,
		Token:        s.token,
	}, nil
}

func (s *invalidationFailingEndpointAccess) InvalidatePushEndpoint(
	context.Context,
	string,
	string,
	string,
) error {
	s.invalidations.Add(1)
	return errors.New("user-service invalidation is offline")
}

func countingSender(calls *atomic.Int32) senderFunc {
	return func(
		context.Context,
		string,
		application.PushDeliveryMessage,
	) (application.PushSendReceipt, error) {
		calls.Add(1)
		return application.PushSendReceipt{ProviderRequestID: "must-not-run"}, nil
	}
}

func TestPushEndpointResolutionFailureMapsToResolutionFailedCode(t *testing.T) {
	access := &resolutionFailingEndpointAccess{}
	var apnsCalls, fcmCalls atomic.Int32
	dispatch, err := application.NewPushDispatchProvider(
		access,
		access,
		countingSender(&apnsCalls),
		countingSender(&fcmCalls),
		slog.New(slog.NewTextHandler(&bytes.Buffer{}, nil)),
	)
	if err != nil {
		t.Fatal(err)
	}
	result, sendErr := dispatch.Send(
		context.Background(),
		pushRequest(time.Now().UTC().Add(2*time.Minute)),
		reliabletask.ReliableAsyncTask{TaskID: "task-resolution-failed"},
	)
	var failure *application.PushProviderFailure
	if !errors.As(sendErr, &failure) ||
		failure.Code != generated.ErrPushEndpointResolutionFailed.Error() ||
		!failure.Retryable ||
		failure.PermanentEndpoint {
		t.Fatalf("resolution outage classification=%+v", failure)
	}
	if result.NormalizedError != generated.ErrPushEndpointResolutionFailed.Error() ||
		result.Status != reliabletask.ExternalInteractionStatusFailed {
		t.Fatalf("unexpected failure result: %+v", result)
	}
	if apnsCalls.Load() != 0 || fcmCalls.Load() != 0 || access.invalidations.Load() != 0 {
		t.Fatalf(
			"resolution failure must not reach providers: apns=%d fcm=%d invalidations=%d",
			apnsCalls.Load(),
			fcmCalls.Load(),
			access.invalidations.Load(),
		)
	}
}

func TestAPNsTransportTimeoutMapsToPushProviderTimeout(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	_, keyFile := writeTemporaryECKey(t)
	apns, err := provider.NewAPNsVoIPProvider(provider.APNsVoIPConfig{
		Environment: application.APNsEnvironmentSandbox,
		KeyFile:     keyFile,
		KeyID:       "APNSKEY01",
		TeamID:      "TEAM000001",
		Topic:       "com.quwoquan.app.voip",
		Timeout:     time.Second,
		BaseURL:     "https://apns.local.invalid",
		Now:         func() time.Time { return now },
	}, &http.Client{
		Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
			return nil, context.DeadlineExceeded
		}),
	})
	if err != nil {
		t.Fatal(err)
	}
	access := &staticEndpointAccess{
		kind:  application.PushEndpointKindAPNSVoIP,
		token: "apns-timeout-token",
	}
	var fcmCalls atomic.Int32
	dispatch, err := application.NewPushDispatchProvider(
		access,
		access,
		apns,
		countingSender(&fcmCalls),
		slog.New(slog.NewTextHandler(&bytes.Buffer{}, nil)),
	)
	if err != nil {
		t.Fatal(err)
	}
	_, sendErr := dispatch.Send(
		context.Background(),
		pushRequest(now.Add(2*time.Minute)),
		reliabletask.ReliableAsyncTask{TaskID: "task-apns-timeout"},
	)
	var failure *application.PushProviderFailure
	if !errors.As(sendErr, &failure) ||
		failure.Code != generated.ErrPushProviderTimeout.Error() ||
		!failure.Retryable ||
		failure.PermanentEndpoint ||
		access.invalidations.Load() != 0 ||
		fcmCalls.Load() != 0 {
		t.Fatalf(
			"APNs timeout classification=%+v invalidations=%d fallback=%d",
			failure,
			access.invalidations.Load(),
			fcmCalls.Load(),
		)
	}
}

func TestAPNsForbiddenMapsToPushProviderCredentialsInvalid(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	_, keyFile := writeTemporaryECKey(t)
	apnsServer := newHTTP2TLSServer(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_ = json.NewEncoder(w).Encode(map[string]string{"reason": "InvalidProviderToken"})
	}))
	apns, err := provider.NewAPNsVoIPProvider(provider.APNsVoIPConfig{
		Environment: application.APNsEnvironmentSandbox,
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
		token: "apns-credentials-token",
	}
	var fcmCalls atomic.Int32
	dispatch, err := application.NewPushDispatchProvider(
		access,
		access,
		apns,
		countingSender(&fcmCalls),
		slog.New(slog.NewTextHandler(&bytes.Buffer{}, nil)),
	)
	if err != nil {
		t.Fatal(err)
	}
	_, sendErr := dispatch.Send(
		context.Background(),
		pushRequest(now.Add(2*time.Minute)),
		reliabletask.ReliableAsyncTask{TaskID: "task-apns-403"},
	)
	var failure *application.PushProviderFailure
	if !errors.As(sendErr, &failure) ||
		failure.Code != generated.ErrPushProviderCredentialsInvalid.Error() ||
		failure.Retryable ||
		failure.PermanentEndpoint ||
		access.invalidations.Load() != 0 ||
		fcmCalls.Load() != 0 {
		t.Fatalf(
			"APNs 403 classification=%+v invalidations=%d fallback=%d",
			failure,
			access.invalidations.Load(),
			fcmCalls.Load(),
		)
	}
}

func TestPushEndpointInvalidationFailureIsLoggedWithInvalidationFailedCode(t *testing.T) {
	access := &invalidationFailingEndpointAccess{
		kind:  application.PushEndpointKindAPNSVoIP,
		token: "apns-permanent-token",
	}
	permanentSender := senderFunc(func(
		context.Context,
		string,
		application.PushDeliveryMessage,
	) (application.PushSendReceipt, error) {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:              generated.ErrPushEndpointPermanentlyInvalid.Error(),
			Provider:          application.PushEndpointKindAPNSVoIP,
			Retryable:         false,
			PermanentEndpoint: true,
			Cause:             errors.New("device token is gone"),
		}
	})
	var fcmCalls atomic.Int32
	var logs bytes.Buffer
	dispatch, err := application.NewPushDispatchProvider(
		access,
		access,
		permanentSender,
		countingSender(&fcmCalls),
		slog.New(slog.NewJSONHandler(&logs, nil)),
	)
	if err != nil {
		t.Fatal(err)
	}
	_, sendErr := dispatch.Send(
		context.Background(),
		pushRequest(time.Now().UTC().Add(2*time.Minute)),
		reliabletask.ReliableAsyncTask{TaskID: "task-invalidation-failed"},
	)
	var failure *application.PushProviderFailure
	if !errors.As(sendErr, &failure) ||
		failure.Code != generated.ErrPushEndpointPermanentlyInvalid.Error() ||
		!failure.PermanentEndpoint {
		t.Fatalf("permanent provider failure must be preserved: %+v", failure)
	}
	if access.invalidations.Load() != 1 || fcmCalls.Load() != 0 {
		t.Fatalf(
			"invalidation must be attempted exactly once without fallback: invalidations=%d fcm=%d",
			access.invalidations.Load(),
			fcmCalls.Load(),
		)
	}
	if !strings.Contains(logs.String(), generated.ErrPushEndpointInvalidationFailed.Error()) {
		t.Fatalf(
			"invalidation outage must be logged with %s: logs=%s",
			generated.ErrPushEndpointInvalidationFailed.Error(),
			logs.String(),
		)
	}
}
