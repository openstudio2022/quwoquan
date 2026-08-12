// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-003
// readiness_case: send-otp-api
// readiness_case: create-alipay-authorization-request-api
// readiness_case: resolve-one-tap-login-hint-api
package api_integration

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"quwoquan_service/runtime/otpseal"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengepersistence "quwoquan_service/services/user-service/internal/account/authentication_challenge/infrastructure/persistence"
	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	bindingpersistence "quwoquan_service/services/user-service/internal/account/credential_binding/infrastructure/persistence"
	httpadapter "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	accountintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
	accountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestAuthenticationChallengePostgresCreateIsIdempotent(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store, err := challengepersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		facade := challengeapp.NewAuthenticationChallengeCommandFacade(store, challengeapp.OTPCredentialVerifier{})
		command := challengeapp.CreateChallengeCommand{
			ID: "challenge-pg-1", AccountID: "account-pg-1", Purpose: "phone_login",
			Channel: "sms", DestinationHash: "destination-hash", SecretRef: "otp-secret-ref",
			IdempotencyKey: "challenge-create-key", ExpiresAt: time.Now().UTC().Add(5 * time.Minute),
		}
		first, err := facade.CreateChallenge(ctx, command)
		if err != nil {
			t.Fatal(err)
		}
		command.ID = "challenge-pg-retry"
		replayed, err := facade.CreateChallenge(ctx, command)
		if err != nil || !replayed.IdempotentReplay || replayed.Challenge.ID != first.Challenge.ID {
			t.Fatalf("AuthenticationChallenge replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var count int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM authentication_challenges WHERE idempotency_key=$1`, command.IdempotencyKey).Scan(&count); err != nil || count != 1 {
			t.Fatalf("AuthenticationChallenge row count=%d err=%v", count, err)
		}
	})
}

func TestAuthenticationChallengeOperationsUseProductionHTTPAndPostgres(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		carrier := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			var payload map[string]string
			if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
				http.Error(writer, "invalid payload", http.StatusBadRequest)
				return
			}
			if payload["token"] != "carrier-api-proof" {
				http.Error(writer, "invalid proof", http.StatusUnauthorized)
				return
			}
			_ = json.NewEncoder(writer).Encode(map[string]string{
				"phone": "+8613800000301", "displayLabel": "138****0301",
			})
		}))
		defer carrier.Close()
		carrierResolver, err := accountintegration.NewProtocolSubstituteCarrierPhoneResolver(
			carrier.URL,
			carrier.Client(),
		)
		if err != nil {
			t.Fatalf("carrier protocol adapter: %v", err)
		}

		challengeStore, err := challengepersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("challenge store: %v", err)
		}
		challengeCommands := challengeapp.NewAuthenticationChallengeCommandFacade(
			challengeStore,
			challengeapp.OTPCredentialVerifier{},
		)
		bindingStore, err := bindingpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("credential store: %v", err)
		}
		dispatch := &apiAuthenticationChallengeDispatch{}
		authService := accountapp.NewAuthService(
			accountpersistence.NewPgProfileStore(pool),
			nil,
			bindingStore,
			nil,
			nil,
			accountapp.WithOtpCodeStore(apiAuthenticationChallengeRateLimit{}),
			accountapp.WithAuthenticationChallenges(challengeCommands),
			accountapp.WithOTPCodeGenerator(func() (string, error) { return "135790", nil }),
			accountapp.WithOTPCodeSealer(apiAuthenticationChallengeSealer{}),
			accountapp.WithExternalInteractionClient(dispatch),
			accountapp.WithCarrierPhoneResolver(carrierResolver),
		)

		privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
		if err != nil {
			t.Fatalf("generate Alipay RSA key: %v", err)
		}
		verifier, issuer, err := accountintegration.NewAlipayFederatedIdentityVerifier(
			accountintegration.ProviderOAuthConfig{
				AppID:                "alipay-api-readiness",
				AppPrivateKeyPEM:     apiAuthenticationPrivateKeyPEM(t, privateKey),
				PlatformPublicKeyPEM: apiAuthenticationPublicKeyPEM(t, &privateKey.PublicKey),
				MerchantPID:          "alipay-api-pid",
			},
			nil,
		)
		if err != nil {
			t.Fatalf("Alipay production issuer: %v", err)
		}
		alipay := accountapp.NewFederatedLoginFacade(nil, verifier, issuer)
		handler, err := httpadapter.NewUserHandler(
			nil,
			nil,
			nil,
			nil,
			authService,
			bindingapp.NewCredentialQueryFacade(bindingStore),
			nil,
			nil,
		)
		if err != nil {
			t.Fatalf("User HTTP handler: %v", err)
		}
		routes := handler.WithFederatedLogins(nil, alipay, nil).Routes()

		otpResponse := apiAuthenticationRequest(
			t,
			routes,
			http.MethodPost,
			"/auth/otp/send",
			`{"phone":"+8613800000300","deviceId":"device-api-otp","platform":"ios","appVersion":"1.0.0","sourceOperation":"phone_login"}`,
		)
		if otpResponse.Code != http.StatusOK {
			t.Fatalf("SendOtp status=%d body=%s", otpResponse.Code, otpResponse.Body.String())
		}
		var firstOTP map[string]any
		if err := json.Unmarshal(otpResponse.Body.Bytes(), &firstOTP); err != nil {
			t.Fatalf("decode SendOtp response: %v", err)
		}
		if firstOTP["retryAfterSeconds"] != float64(60) ||
			firstOTP["deliveryStatus"] != "queued" ||
			strings.TrimSpace(anyStringForAuthenticationTest(firstOTP["requestId"])) == "" ||
			strings.TrimSpace(anyStringForAuthenticationTest(firstOTP["challengeId"])) == "" {
			t.Fatalf("SendOtp reliability response=%v", firstOTP)
		}
		// 模拟服务端已经提交短信，但首个 HTTP response 在客户端侧丢失。
		// 同一 Idempotency-Key 重放必须读取原 challenge，不能二次投递。
		replayedOTPResponse := apiAuthenticationRequest(
			t,
			routes,
			http.MethodPost,
			"/auth/otp/send",
			`{"phone":"+8613800000300","deviceId":"device-api-otp","platform":"ios","appVersion":"1.0.0","sourceOperation":"phone_login"}`,
		)
		if replayedOTPResponse.Code != http.StatusOK {
			t.Fatalf(
				"SendOtp replay status=%d body=%s",
				replayedOTPResponse.Code,
				replayedOTPResponse.Body.String(),
			)
		}
		var replayedOTP map[string]any
		if err := json.Unmarshal(replayedOTPResponse.Body.Bytes(), &replayedOTP); err != nil {
			t.Fatalf("decode SendOtp replay response: %v", err)
		}
		if replayedOTP["requestId"] != firstOTP["requestId"] ||
			replayedOTP["challengeId"] != firstOTP["challengeId"] ||
			len(dispatch.requests) != 1 {
			t.Fatalf(
				"SendOtp replay drift: first=%v replay=%v dispatch=%d",
				firstOTP,
				replayedOTP,
				len(dispatch.requests),
			)
		}
		var challengeCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM authentication_challenges WHERE purpose='phone_login' AND channel='sms'`).Scan(&challengeCount); err != nil {
			t.Fatalf("count persisted OTP challenges: %v", err)
		}
		if challengeCount != 1 || len(dispatch.requests) != 1 || dispatch.requests[0].CodeRef != "sealed-api-otp-proof" {
			t.Fatalf("SendOtp challengeCount=%d dispatch=%+v", challengeCount, dispatch.requests)
		}

		hintResponse := apiAuthenticationRequest(
			t,
			routes,
			http.MethodPost,
			"/auth/login/one-tap/hint",
			`{"carrierToken":"carrier-api-proof","deviceId":"device-api-hint","platform":"ios","appVersion":"1.0.0"}`,
		)
		if hintResponse.Code != http.StatusOK ||
			!strings.Contains(hintResponse.Body.String(), `"state":"new_phone"`) ||
			!strings.Contains(hintResponse.Body.String(), `"maskedPhone":"138****0301"`) {
			t.Fatalf("ResolveOneTapLoginHint status=%d body=%s", hintResponse.Code, hintResponse.Body.String())
		}

		authorizationResponse := apiAuthenticationRequest(
			t,
			routes,
			http.MethodPost,
			"/auth/authorization/alipay",
			`{}`,
		)
		if authorizationResponse.Code != http.StatusOK ||
			!strings.Contains(authorizationResponse.Body.String(), "authorizationPayload") ||
			!strings.Contains(authorizationResponse.Body.String(), "RSA2") {
			t.Fatalf("CreateAlipayAuthorizationRequest status=%d body=%s", authorizationResponse.Code, authorizationResponse.Body.String())
		}
	})
}

func anyStringForAuthenticationTest(value any) string {
	text, _ := value.(string)
	return text
}

func apiAuthenticationRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	if path == "/auth/otp/send" {
		request.Header.Set("Idempotency-Key", "api-authentication-otp-key-000001")
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

type apiAuthenticationChallengeRateLimit struct{}

func (apiAuthenticationChallengeRateLimit) AllowSend(
	context.Context,
	string,
	string,
	string,
) (accountapp.OtpSendAdmission, error) {
	return accountapp.OtpSendAdmission{
		Allowed:           true,
		RetryAfterSeconds: 60,
	}, nil
}

type apiAuthenticationChallengeSealer struct{}

func (apiAuthenticationChallengeSealer) Seal(otpseal.Secret, otpseal.Binding) (string, error) {
	return "sealed-api-otp-proof", nil
}

type apiAuthenticationChallengeDispatch struct {
	requests []accountapp.SMSOTPDispatchRequest
}

func (dispatch *apiAuthenticationChallengeDispatch) SubmitSMSOTP(
	_ context.Context,
	request accountapp.SMSOTPDispatchRequest,
) (accountapp.ExternalInteractionAccepted, error) {
	dispatch.requests = append(dispatch.requests, request)
	return accountapp.ExternalInteractionAccepted{RequestID: request.RequestID, Status: "queued"}, nil
}

func apiAuthenticationPrivateKeyPEM(t *testing.T, key *rsa.PrivateKey) string {
	t.Helper()
	encoded, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatalf("marshal private key: %v", err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: encoded}))
}

func apiAuthenticationPublicKeyPEM(t *testing.T, key *rsa.PublicKey) string {
	t.Helper()
	encoded, err := x509.MarshalPKIXPublicKey(key)
	if err != nil {
		t.Fatalf("marshal public key: %v", err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: encoded}))
}

var (
	_ accountapp.OtpCodeStore              = apiAuthenticationChallengeRateLimit{}
	_ accountapp.OTPCodeSealer             = apiAuthenticationChallengeSealer{}
	_ accountapp.ExternalInteractionClient = (*apiAuthenticationChallengeDispatch)(nil)
)
