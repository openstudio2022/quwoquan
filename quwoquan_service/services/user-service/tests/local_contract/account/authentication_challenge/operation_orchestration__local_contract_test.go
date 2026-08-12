// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-011.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-003
// readiness_case: send-otp-local
// readiness_case: create-alipay-authorization-request-local
// readiness_case: resolve-one-tap-login-hint-local
package local_contract

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/otpseal"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	accountintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

func TestSendOtpCommitsAuthenticationChallengeBeforeSealedDispatch(t *testing.T) {
	store := newFakeAuthenticationChallengeStore()
	challenges := challengeapp.NewAuthenticationChallengeCommandFacade(
		store,
		challengeapp.OTPCredentialVerifier{},
	)
	dispatch := &authenticationChallengeDispatchProbe{}
	service := accountapp.NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		accountapp.WithOtpCodeStore(authenticationChallengeRateLimit{}),
		accountapp.WithAuthenticationChallenges(challenges),
		accountapp.WithOTPCodeGenerator(func() (string, error) { return "246810", nil }),
		accountapp.WithOTPCodeSealer(authenticationChallengeSealer{}),
		accountapp.WithExternalInteractionClient(dispatch),
	)

	result, err := service.SendOtp(
		context.Background(),
		"+8613800000201",
		"device-otp-1",
		"ios",
		"1.0.0",
		"phone_login",
		"",
		"otp-idempotency-0001",
	)
	if err != nil {
		t.Fatalf("SendOtp: %v", err)
	}
	if result.ChallengeID == "" || result.RequestID == "" || result.DeliveryStatus != "queued" ||
		store.challengeCount() != 1 || len(dispatch.requests) != 1 {
		t.Fatalf("SendOtp result=%+v challengeCount=%d dispatch=%+v", result, store.challengeCount(), dispatch.requests)
	}
	challenge := store.mustLoad(t, result.ChallengeID).State()
	if challenge.Purpose != "phone_login" || challenge.Channel != "sms" ||
		challenge.SecretRef == "" || strings.Contains(challenge.SecretRef, "246810") ||
		dispatch.requests[0].ChallengeID != result.ChallengeID ||
		dispatch.requests[0].CodeRef != "sealed-otp-proof" {
		t.Fatalf("SendOtp did not preserve irreversible challenge + sealed dispatch: challenge=%+v dispatch=%+v", challenge, dispatch.requests[0])
	}
}

func TestCreateAlipayAuthorizationRequestUsesProductionRSA2Issuer(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate RSA key: %v", err)
	}
	verifier, issuer, err := accountintegration.NewAlipayFederatedIdentityVerifier(
		accountintegration.ProviderOAuthConfig{
			AppID:                "alipay-app-readiness",
			AppPrivateKeyPEM:     authenticationChallengePrivateKeyPEM(t, privateKey),
			PlatformPublicKeyPEM: authenticationChallengePublicKeyPEM(t, &privateKey.PublicKey),
			MerchantPID:          "alipay-pid-readiness",
		},
		nil,
	)
	if err != nil {
		t.Fatalf("create Alipay issuer: %v", err)
	}
	facade := accountapp.NewFederatedLoginFacade(nil, verifier, issuer)
	request, err := facade.IssueAuthorizationRequest(context.Background())
	if err != nil {
		t.Fatalf("CreateAlipayAuthorizationRequest: %v", err)
	}
	values, err := url.ParseQuery(request.Payload)
	if err != nil {
		t.Fatalf("parse authorization payload: %v", err)
	}
	if values.Get("app_id") != "alipay-app-readiness" ||
		values.Get("pid") != "alipay-pid-readiness" ||
		values.Get("sign_type") != "RSA2" || values.Get("sign") == "" ||
		!request.ExpiresAt.After(time.Now().UTC()) {
		t.Fatalf("Alipay authorization request=%+v payload=%v", request, values)
	}
}

func TestResolveOneTapLoginHintUsesProductionHTTPSResolver(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		var payload map[string]string
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			http.Error(writer, "invalid payload", http.StatusBadRequest)
			return
		}
		if payload["token"] != "carrier-hint-proof" {
			http.Error(writer, "invalid proof", http.StatusUnauthorized)
			return
		}
		_ = json.NewEncoder(writer).Encode(map[string]string{
			"phone": "+8613800000202", "displayLabel": "138****0202",
		})
	}))
	defer server.Close()
	resolver, err := accountintegration.NewProtocolSubstituteCarrierPhoneResolver(
		server.URL,
		server.Client(),
	)
	if err != nil {
		t.Fatalf("create carrier resolver: %v", err)
	}
	service := accountapp.NewAuthService(
		nil,
		nil,
		authenticationChallengeCredentialLookup{},
		nil,
		nil,
		accountapp.WithCarrierPhoneResolver(resolver),
	)
	hint, err := service.ResolveOneTapLoginHint(
		context.Background(),
		"carrier-hint-proof",
		"device-hint-1",
		"ios",
		"1.0.0",
	)
	if err != nil {
		t.Fatalf("ResolveOneTapLoginHint: %v", err)
	}
	if hint.State != "new_phone" || hint.Registered || hint.MaskedPhone != "138****0202" || hint.ExpiresInSeconds != 60 {
		t.Fatalf("one-tap hint=%+v", hint)
	}
}

type authenticationChallengeRateLimit struct{}

func (authenticationChallengeRateLimit) AllowSend(
	context.Context,
	string,
	string,
	string,
) (accountapp.OtpSendAdmission, error) {
	return accountapp.OtpSendAdmission{Allowed: true}, nil
}

type authenticationChallengeSealer struct{}

func (authenticationChallengeSealer) Seal(otpseal.Secret, otpseal.Binding) (string, error) {
	return "sealed-otp-proof", nil
}

type authenticationChallengeDispatchProbe struct {
	requests []accountapp.SMSOTPDispatchRequest
}

func (probe *authenticationChallengeDispatchProbe) SubmitSMSOTP(
	_ context.Context,
	request accountapp.SMSOTPDispatchRequest,
) (accountapp.ExternalInteractionAccepted, error) {
	probe.requests = append(probe.requests, request)
	return accountapp.ExternalInteractionAccepted{RequestID: request.RequestID, Status: "queued"}, nil
}

type authenticationChallengeCredentialLookup struct{}

func (authenticationChallengeCredentialLookup) Bind(context.Context, bindingmodel.ChangeSet) (bindingports.BindResult, error) {
	return bindingports.BindResult{}, nil
}

func (authenticationChallengeCredentialLookup) LoadByOwnerAndType(context.Context, string, bindingmodel.CredentialType) (bindingmodel.CredentialBinding, bool, error) {
	return bindingmodel.CredentialBinding{}, false, nil
}

func (authenticationChallengeCredentialLookup) FindByTypeAndKey(context.Context, bindingmodel.CredentialType, string) (bindingmodel.CredentialBinding, bool, error) {
	return bindingmodel.CredentialBinding{}, false, nil
}

func (authenticationChallengeCredentialLookup) MarkUsed(context.Context, string, time.Time) error {
	return nil
}

func (authenticationChallengeCredentialLookup) ListByOwner(context.Context, string) ([]bindingmodel.CredentialBinding, error) {
	return nil, nil
}

func (authenticationChallengeCredentialLookup) CommitRevoke(context.Context, int64, bindingmodel.ChangeSet) error {
	return nil
}

func authenticationChallengePrivateKeyPEM(t *testing.T, key *rsa.PrivateKey) string {
	t.Helper()
	encoded, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatalf("marshal private key: %v", err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: encoded}))
}

func authenticationChallengePublicKeyPEM(t *testing.T, key *rsa.PublicKey) string {
	t.Helper()
	encoded, err := x509.MarshalPKIXPublicKey(key)
	if err != nil {
		t.Fatalf("marshal public key: %v", err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: encoded}))
}

var (
	_ accountapp.OtpCodeStore              = authenticationChallengeRateLimit{}
	_ accountapp.OTPCodeSealer             = authenticationChallengeSealer{}
	_ accountapp.ExternalInteractionClient = (*authenticationChallengeDispatchProbe)(nil)
	_ bindingports.AggregateStore          = authenticationChallengeCredentialLookup{}
)
