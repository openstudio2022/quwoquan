// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-003
// readiness_case: login-with-phone-api
// readiness_case: login-with-wechat-api
// readiness_case: login-with-alipay-api
// readiness_case: login-with-qq-api
// readiness_case: login-one-tap-api
// readiness_case: login-anonymous-api
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	rtauth "quwoquan_service/runtime/auth"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	sessionpersistence "quwoquan_service/services/user-service/internal/account/account_session/infrastructure/persistence"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengepersistence "quwoquan_service/services/user-service/internal/account/authentication_challenge/infrastructure/persistence"
	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingpersistence "quwoquan_service/services/user-service/internal/account/credential_binding/infrastructure/persistence"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	registrationpersistence "quwoquan_service/services/user-service/internal/account/device_registration/infrastructure/persistence"
	httpadapter "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	accountintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
	accountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	userpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestPublishedLoginRoutesUseProductionHTTPAndPostgresPackets(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		const (
			ownerID      = "account-session-login-owner"
			personaID    = "account-session-login-persona"
			phone        = "+8613800000501"
			carrierPhone = "+8613800000502"
			anonymousKey = "fp-account-session-api"
			otpCode      = "246810"
		)
		if err := usersupport.SeedAccountPersona(ctx, pool, ownerID, personaID); err != nil {
			t.Fatalf("seed AccountSession login owner: %v", err)
		}

		bindingStore, err := bindingpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("credential store: %v", err)
		}
		bindingCommands := bindingapp.NewCredentialCommandFacade(bindingStore)
		for _, seed := range []struct {
			credentialType bindingmodel.CredentialType
			credentialKey  string
		}{
			{bindingmodel.CredentialTypePhone, phone},
			{bindingmodel.CredentialTypeFederatedSlotA, "wechat-subject-api"},
			{bindingmodel.CredentialTypeFederatedSlotB, "alipay-subject-api"},
			{bindingmodel.CredentialTypeFederatedSlotC, "qq-subject-api"},
			{bindingmodel.CredentialTypeCarrierPhone, carrierPhone},
			{bindingmodel.CredentialTypeAnonymousDevice, anonymousKey},
		} {
			if _, err := bindingCommands.BindVerifiedCredential(
				ctx,
				ownerID,
				bindingapp.BindCredentialCommand{
					CredentialType: seed.credentialType,
					CredentialKey:  seed.credentialKey,
					DisplayLabel:   string(seed.credentialType),
				},
			); err != nil {
				t.Fatalf("seed %s login credential: %v", seed.credentialType, err)
			}
		}

		challengeStore, err := challengepersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("challenge store: %v", err)
		}
		challengeCommands := challengeapp.NewAuthenticationChallengeCommandFacade(
			challengeStore,
			challengeapp.OTPCredentialVerifier{},
		)
		challengeID := "otp-account-session-login"
		destinationHash := challengeapp.SMSDestinationHash(phone)
		if _, err := challengeCommands.CreateChallenge(ctx, challengeapp.CreateChallengeCommand{
			ID:              challengeID,
			Purpose:         "phone_login",
			Channel:         "sms",
			DestinationHash: destinationHash,
			SecretRef:       challengeapp.OTPSecretReference(challengeID, destinationHash, []byte(otpCode)),
			IdempotencyKey:  "account-session-phone-login-readiness",
			ExpiresAt:       time.Now().UTC().Add(5 * time.Minute),
		}); err != nil {
			t.Fatalf("seed phone login challenge: %v", err)
		}

		providerServer := httptest.NewTLSServer(http.HandlerFunc(
			func(writer http.ResponseWriter, request *http.Request) {
				switch request.URL.Path {
				case "/carrier":
					var payload map[string]string
					if err := json.NewDecoder(request.Body).Decode(&payload); err != nil || payload["token"] != "carrier-login-api-proof" {
						http.Error(writer, "invalid carrier proof", http.StatusUnauthorized)
						return
					}
					_ = json.NewEncoder(writer).Encode(map[string]string{
						"phone": carrierPhone, "displayLabel": "138****0502",
					})
				case "/federated":
					var payload struct {
						Action   string `json:"action"`
						Provider string `json:"provider"`
						Code     string `json:"code"`
					}
					if err := json.NewDecoder(request.Body).Decode(&payload); err != nil ||
						payload.Action != "resolveIdentity" || payload.Code == "" {
						http.Error(writer, "invalid federated proof", http.StatusBadRequest)
						return
					}
					_ = json.NewEncoder(writer).Encode(map[string]string{
						"credentialKey": payload.Provider + "-subject-api",
						"displayName":   "Federated Login Owner",
						"avatarUrl":     "",
					})
				default:
					http.NotFound(writer, request)
				}
			},
		))
		defer providerServer.Close()
		carrierResolver, err := accountintegration.NewProtocolSubstituteCarrierPhoneResolver(
			providerServer.URL+"/carrier",
			providerServer.Client(),
		)
		if err != nil {
			t.Fatalf("carrier protocol adapter: %v", err)
		}
		verifiers := make(map[string]accountapp.FederatedIdentityVerifier, 3)
		for provider, credentialType := range map[string]bindingmodel.CredentialType{
			"wechat": bindingmodel.CredentialTypeFederatedSlotA,
			"alipay": bindingmodel.CredentialTypeFederatedSlotB,
			"qq":     bindingmodel.CredentialTypeFederatedSlotC,
		} {
			verifier, err := accountintegration.NewProtocolSubstituteFederatedIdentityVerifier(
				credentialType,
				provider,
				providerServer.URL+"/federated",
				providerServer.Client(),
			)
			if err != nil {
				t.Fatalf("%s protocol adapter: %v", provider, err)
			}
			verifiers[provider] = verifier
		}

		sessionStore, err := sessionpersistence.NewAccountSessionPostgresStore(pool)
		if err != nil {
			t.Fatalf("AccountSession store: %v", err)
		}
		registrationStore, err := registrationpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("DeviceRegistration store: %v", err)
		}
		cipher, err := registrationpersistence.NewAESGCMTokenCipher(make([]byte, 32))
		if err != nil {
			t.Fatalf("DeviceRegistration cipher: %v", err)
		}
		security, err := accountpersistence.NewEnforcementStore(pool)
		if err != nil {
			t.Fatalf("account security reader: %v", err)
		}
		signer, err := rtauth.NewHS256Signer(rtauth.TokenConfig{
			Secret:       []byte("account-session-login-api-32bytes"),
			Issuer:       "https://auth.quwoquan.test",
			Audience:     "quwoquan-api",
			Type:         rtauth.TokenTypeAccess,
			TokenVersion: 1,
			TTL:          30 * time.Minute,
		})
		if err != nil {
			t.Fatalf("access signer: %v", err)
		}
		authService := accountapp.NewAuthService(
			accountpersistence.NewPgProfileStore(pool),
			userpersistence.NewPgPersonaStore(pool),
			bindingStore,
			userpersistence.NewPgAnonymousDeviceBindingStore(pool),
			nil,
			accountapp.WithAccountSessionCommands(sessionapp.NewAccountSessionCommandFacade(sessionStore)),
			accountapp.WithDeviceRegistration(registrationapp.NewCommandFacade(registrationStore, cipher)),
			accountapp.WithConsentRecordStore(accountpersistence.NewPgConsentRecordStore(pool)),
			accountapp.WithAuthenticationChallenges(challengeCommands),
			accountapp.WithCarrierPhoneResolver(carrierResolver),
			accountapp.WithAccountSecurityReader(security),
			accountapp.WithAccessTokenSigner(signer),
		)
		federated := make(map[string]*accountapp.FederatedLoginFacade, len(verifiers))
		for provider, verifier := range verifiers {
			federated[provider] = accountapp.NewFederatedLoginFacade(authService, verifier, nil)
		}

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
		routes := handler.WithFederatedLogins(
			federated["wechat"],
			federated["alipay"],
			federated["qq"],
		).Routes()

		requests := []struct {
			operation string
			path      string
			body      string
		}{
			{
				operation: "LoginWithPhone",
				path:      "/auth/login/phone",
				body: fmt.Sprintf(
					`{"phone":%q,"otpCode":%q,"deviceId":"login-api-phone","platform":"ios","appVersion":"1.0.0","agreementVersion":"agreement-v1","privacyVersion":"privacy-v1"}`,
					phone,
					otpCode,
				),
			},
			{operation: "LoginWithWechat", path: "/auth/login/wechat", body: accountSessionFederatedBody("wechatCode", "wechat-code", "wechat")},
			{operation: "LoginWithAlipay", path: "/auth/login/alipay", body: accountSessionFederatedBody("alipayAuthCode", "alipay-code", "alipay")},
			{operation: "LoginWithQq", path: "/auth/login/qq", body: accountSessionFederatedBody("qqAuthCode", "qq-code", "qq")},
			{
				operation: "LoginOneTap",
				path:      "/auth/login/one-tap",
				body:      `{"carrierToken":"carrier-login-api-proof","deviceId":"login-api-carrier","platform":"android","appVersion":"1.0.0","agreementVersion":"agreement-v1","privacyVersion":"privacy-v1"}`,
			},
			{
				operation: "LoginAnonymous",
				path:      "/auth/login/anonymous",
				body: fmt.Sprintf(
					`{"installId":"install-account-session-api","deviceFingerprintHash":%q,"platform":"android","appVersion":"1.0.0"}`,
					anonymousKey,
				),
			},
		}
		for _, login := range requests {
			response := accountSessionLoginRequest(t, routes, login.path, login.body)
			if response.Code != http.StatusOK ||
				!strings.Contains(response.Body.String(), ownerID) ||
				!strings.Contains(response.Body.String(), "accessToken") {
				t.Fatalf("%s status=%d body=%s", login.operation, response.Code, response.Body.String())
			}
		}

		var sessionCount, registrationCount, consentCount, anonymousBindingCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM account_sessions WHERE account_id=$1 AND status='active'`, ownerID).Scan(&sessionCount); err != nil {
			t.Fatalf("count active login sessions: %v", err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM user_devices WHERE account_id=$1`, ownerID).Scan(&registrationCount); err != nil {
			t.Fatalf("count login device registrations: %v", err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM consent_records WHERE owner_id=$1`, ownerID).Scan(&consentCount); err != nil {
			t.Fatalf("count login consent records: %v", err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM anonymous_device_bindings WHERE owner_id=$1 AND device_fingerprint_hash=$2`, ownerID, anonymousKey).Scan(&anonymousBindingCount); err != nil {
			t.Fatalf("count anonymous device binding: %v", err)
		}
		if sessionCount != 6 || registrationCount != 5 || consentCount != 5 || anonymousBindingCount != 1 {
			t.Fatalf(
				"login packet counts sessions=%d registrations=%d consents=%d anonymousBindings=%d",
				sessionCount,
				registrationCount,
				consentCount,
				anonymousBindingCount,
			)
		}
	})
}

func accountSessionFederatedBody(field string, code string, provider string) string {
	encoded, _ := json.Marshal(map[string]string{
		field:              code,
		"deviceId":         "login-api-" + provider,
		"platform":         "ios",
		"appVersion":       "1.0.0",
		"agreementVersion": "agreement-v1",
		"privacyVersion":   "privacy-v1",
	})
	return string(encoded)
}

func accountSessionLoginRequest(
	t *testing.T,
	handler http.Handler,
	path string,
	body string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}
