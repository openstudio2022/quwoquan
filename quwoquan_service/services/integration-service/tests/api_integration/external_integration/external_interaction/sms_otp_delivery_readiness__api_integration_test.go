// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-012
// readiness_case: get-sms-otp-delivery-readiness-api
package api_integration

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/runtime/otpseal"
	externalgenerated "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	httpadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/http"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/resultrelay"
)

type readinessTransport struct{}

func (readinessTransport) AppendDurable(context.Context, runtimemessaging.DurableMessage) (string, error) {
	return "1-0", nil
}

func (readinessTransport) SetDurableRetention(context.Context, string, time.Duration) error {
	return nil
}

func scopedReadinessRequest(path string, subject string, scope string) *http.Request {
	request := httptest.NewRequest(http.MethodGet, path, nil)
	return request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{
			Subject: subject,
			Scope:   scope,
			Roles:   []string{"service"},
		},
		Actor: operation.ActorContext{AccountID: subject},
	}))
}

func TestSmsOtpDeliveryReadinessUsesProviderProbeAndMongoBackedRelay(t *testing.T) {
	resetReliableTaskCollections(t)
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodGet || request.URL.Path != "/healthz" {
			http.Error(writer, "unexpected readiness probe", http.StatusNotFound)
			return
		}
		_ = json.NewEncoder(writer).Encode(map[string]any{"status": "ready"})
	}))
	defer upstream.Close()

	sealer, err := otpseal.NewFromBase64("test-k1", map[string]string{
		"test-k1": base64.StdEncoding.EncodeToString([]byte("0123456789abcdef0123456789abcdef")),
	})
	if err != nil {
		t.Fatal(err)
	}
	references := provider.NewMongoOTPCodeReferenceStore(integrationMongoDB)
	smsProvider, err := provider.NewHTTPExternalProvider(provider.HTTPExternalProviderConfig{
		Name:              "aliyun_sms",
		Operation:         "sms_otp.send",
		Endpoint:          upstream.URL + "/v1/provider/sms/send",
		BearerToken:       "provider-secret",
		Timeout:           time.Second,
		OTPCodeSealer:     sealer,
		OTPCodeReferences: references,
	}, upstream.Client())
	if err != nil {
		t.Fatal(err)
	}
	relay, err := resultrelay.New(integrationReliableStore, readinessTransport{}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := relay.ProcessOnce(context.Background()); err != nil {
		t.Fatal(err)
	}
	queries := application.NewSmsOtpDeliveryReadinessQueryFacade(smsProvider, relay)
	handler := httpadapter.NewHandler(nil, queries).Routes()
	handler = rtauth.EnforceGeneratedOperationAuthorization(
		operationsecurity.ForDomain("integration"),
	)(handler)

	request := scopedReadinessRequest(
		externalgenerated.SmsOtpDeliveryReadinessPath,
		"service:user-service",
		"integration.identity.sms.otp.readiness.read",
	)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("readiness status=%d body=%s", response.Code, response.Body.String())
	}
	var body application.SmsOtpDeliveryReadiness
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Availability != "ready" || body.RetryAfterSeconds != 0 {
		t.Fatalf("readiness body=%+v", body)
	}

	for _, testCase := range []struct {
		name    string
		subject string
		scope   string
	}{
		{name: "wrong service", subject: "service:notification-service", scope: "integration.identity.sms.otp.readiness.read"},
		{name: "missing scope", subject: "service:user-service", scope: "integration.external_interaction.read"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			denied := httptest.NewRecorder()
			handler.ServeHTTP(denied, scopedReadinessRequest(
				externalgenerated.SmsOtpDeliveryReadinessPath,
				testCase.subject,
				testCase.scope,
			))
			if denied.Code != http.StatusForbidden {
				t.Fatalf("denied status=%d body=%s", denied.Code, denied.Body.String())
			}
		})
	}
}
