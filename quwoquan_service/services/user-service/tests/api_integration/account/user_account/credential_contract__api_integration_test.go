package api_integration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	runtimeerrors "quwoquan_service/runtime/errors"
	accountsessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	accountsessionpersistence "quwoquan_service/services/user-service/internal/account/account_session/infrastructure/persistence"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengepersistence "quwoquan_service/services/user-service/internal/account/authentication_challenge/infrastructure/persistence"
	credentialhttp "quwoquan_service/services/user-service/internal/account/credential_binding/adapters/inbound/http"
	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	credentialpersistence "quwoquan_service/services/user-service/internal/account/credential_binding/infrastructure/persistence"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	registrationpersistence "quwoquan_service/services/user-service/internal/account/device_registration/infrastructure/persistence"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	accountcache "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/cache"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	userpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/persistence"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
)

func testAccountPacketOptions(t *testing.T) []application.AuthServiceOption {
	t.Helper()
	sessionStore, err := accountsessionpersistence.NewAccountSessionPostgresStore(
		pgPool,
	)
	if err != nil {
		t.Fatalf("account session store: %v", err)
	}
	registrationStore, err := registrationpersistence.NewPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("device registration store: %v", err)
	}
	tokenCipher, err := registrationpersistence.NewAESGCMTokenCipher(
		make([]byte, 32),
	)
	if err != nil {
		t.Fatalf("device registration cipher: %v", err)
	}
	accountSecurityReader, err := useraccountpersistence.NewEnforcementStore(pgPool)
	if err != nil {
		t.Fatalf("account security reader: %v", err)
	}
	authenticationChallengeStore, err := challengepersistence.NewPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("authentication challenge store: %v", err)
	}
	personaCommandStore, err := personapersistence.NewPersonaCommandPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("Persona command store: %v", err)
	}
	personaProfileProjector, err := useraccountpersistence.NewPersonaProfileProjector(pgPool)
	if err != nil {
		t.Fatalf("Persona profile projector: %v", err)
	}
	return []application.AuthServiceOption{
		application.WithAccountSessionCommands(
			accountsessionapp.NewAccountSessionCommandFacade(sessionStore),
		),
		application.WithDeviceRegistration(
			registrationapp.NewCommandFacade(
				registrationStore,
				tokenCipher,
			),
		),
		application.WithAccountSecurityReader(accountSecurityReader),
		application.WithPersonaCommandPipeline(
			personaCommandStore,
			personaProfileProjector,
		),
		application.WithConsentRecordStore(persistence.NewPgConsentRecordStore(pgPool)),
		application.WithFederatedPhoneBindingTickets(
			credentialStoreForFederatedBinding(t),
		),
		application.WithOtpCodeStore(accountcache.NewOtpCodeCache(redisClient)),
		application.WithAuthenticationChallenges(
			challengeapp.NewAuthenticationChallengeCommandFacade(
				authenticationChallengeStore,
				challengeapp.OTPCredentialVerifier{},
			),
		),
		application.WithOTPCodeSealer(testOTPCodeSealer),
		application.WithExternalInteractionClient(externalInteractionRuntime.client),
	}
}

func credentialStoreForFederatedBinding(t *testing.T) *credentialpersistence.PostgresStore {
	t.Helper()
	store, err := credentialpersistence.NewPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("federated credential store: %v", err)
	}
	return store
}

const (
	testAgreementVersion = "agreement-login-v1"
	testPrivacyVersion   = "privacy-login-v1"
)

func newFederatedLoginTestRuntime(
	t *testing.T,
) (*application.AuthService, *application.FederatedLoginFacade) {
	t.Helper()
	credentialStore, err := credentialpersistence.NewPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("credential store: %v", err)
	}
	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		t.Fatalf("load shard directory: %v", err)
	}
	options := append(
		testAccountPacketOptions(t),
		application.WithAccessTokenSigner(testAccessSigner),
		application.WithCredentialCommands(
			credentialapp.NewCredentialCommandFacade(credentialStore),
		),
	)
	authService := application.NewAuthService(
		persistence.NewPgProfileStore(pgPool),
		userpersistence.NewPgPersonaStore(pgPool),
		credentialStore,
		userpersistence.NewPgAnonymousDeviceBindingStore(pgPool),
		shardDirectory,
		options...,
	)
	return authService, application.NewFederatedLoginFacade(
		authService,
		externalProviderRuntime.wechat,
		nil,
	)
}

func startFederatedPhoneBinding(
	t *testing.T,
	wechatLogin *application.FederatedLoginFacade,
	authorizationCode string,
) *accountsessionapp.FederatedLoginOutcome {
	t.Helper()
	outcome, err := wechatLogin.Login(
		context.Background(),
		authorizationCode,
		"device-social-1",
		"ios",
		"1.0.0",
		testAgreementVersion,
		testPrivacyVersion,
	)
	if err != nil {
		t.Fatalf("start federated phone binding: %v", err)
	}
	if outcome.Status != accountsessionapp.FederatedLoginPhoneBindingRequired ||
		outcome.BindingTicket == "" || outcome.Session != nil {
		t.Fatalf("new federated identity must return binding-only outcome: %#v", outcome)
	}
	return outcome
}

func sendFederatedBindingOtp(
	t *testing.T,
	authService *application.AuthService,
	outcome *accountsessionapp.FederatedLoginOutcome,
	phone string,
) (*application.OtpSendResult, string) {
	t.Helper()
	result, err := authService.SendOtp(
		context.Background(),
		phone,
		"device-social-1",
		"ios",
		"1.0.0",
		"bind_phone",
		outcome.BindingTicket,
		"credential-contract-bind-otp-000001",
	)
	if err != nil {
		t.Fatalf("send bind-phone otp: %v", err)
	}
	code, err := externalInteractionRuntime.captureBridge.readOTP(phone)
	if err != nil {
		t.Fatalf("bind-phone otp protected readback failed: %v", err)
	}
	return result, code
}

func federatedBindingCommand(
	outcome *accountsessionapp.FederatedLoginOutcome,
	phone string,
	challengeID string,
	otpCode string,
) credentialapp.CompleteFederatedPhoneBindingCommand {
	return credentialapp.CompleteFederatedPhoneBindingCommand{
		BindingTicket:    outcome.BindingTicket,
		Phone:            phone,
		OTPCode:          otpCode,
		ChallengeID:      challengeID,
		DeviceID:         "device-social-1",
		Platform:         "ios",
		AppVersion:       "1.0.0",
		AgreementVersion: testAgreementVersion,
		PrivacyVersion:   testPrivacyVersion,
	}
}

func assertLoginAppErrorCode(t *testing.T, err error, want string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected login error %s, got nil", want)
	}
	var appError *runtimeerrors.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("expected *runtimeerrors.AppError, got %T: %v", err, err)
	}
	if got := appError.Code.String(); got != want {
		t.Fatalf(
			"login error code=%s, want %s: %v (debug=%s)",
			got,
			want,
			err,
			appError.DebugMessage,
		)
	}
}

func completeWechatPhoneBinding(
	t *testing.T,
	authService *application.AuthService,
	wechatLogin *application.FederatedLoginFacade,
	authorizationCode string,
	phone string,
) *accountsessionapp.AuthSessionGrant {
	t.Helper()
	outcome := startFederatedPhoneBinding(t, wechatLogin, authorizationCode)
	return completeFederatedBindingFromPending(t, authService, outcome, phone)
}

func completeFederatedBindingFromPending(
	t *testing.T,
	authService *application.AuthService,
	outcome *accountsessionapp.FederatedLoginOutcome,
	phone string,
) *accountsessionapp.AuthSessionGrant {
	t.Helper()
	sendResult, code := sendFederatedBindingOtp(t, authService, outcome, phone)

	result, err := authService.CompleteFederatedPhoneBinding(
		context.Background(),
		federatedBindingCommand(outcome, phone, sendResult.ChallengeID, code),
	)
	if err != nil {
		t.Fatalf("complete federated phone binding: %v", err)
	}
	if result == nil || result.OwnerID == "" || result.AccessToken == "" {
		t.Fatalf("completed binding must return authenticated session: %#v", result)
	}
	return result
}

// T3 CredentialBinding 全场景契约测试

func TestUnsupportedFutureLoginMethodsAreNotPublic(t *testing.T) {
	for _, route := range []string{
		"/auth/login/apple",
		"/auth/login/passkey",
	} {
		rec := doRequest(t, http.MethodPost, route, `{"credential":"must-not-be-accepted"}`, nil)
		if rec.Code != http.StatusNotFound {
			t.Fatalf(
				"%s is out of scope and must not be publicly routable: got %d: %s",
				route,
				rec.Code,
				rec.Body.String(),
			)
		}
	}
}

func TestLoginWithSocialProvider_FirstSyncSeedsAvatarVersion(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	profileStore := persistence.NewPgProfileStore(pgPool)
	personaStore := userpersistence.NewPgPersonaStore(pgPool)
	credentialStore, err := credentialpersistence.NewPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("credential store: %v", err)
	}
	credentialCommands := credentialapp.NewCredentialCommandFacade(
		credentialStore,
	)
	anonymousDeviceBindingStore := userpersistence.NewPgAnonymousDeviceBindingStore(pgPool)
	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		t.Fatalf("load shard directory: %v", err)
	}
	options := testAccountPacketOptions(t)
	options = append(
		options,
		application.WithAccessTokenSigner(testAccessSigner),
		application.WithCredentialCommands(credentialCommands),
	)
	authService := application.NewAuthService(
		profileStore,
		personaStore,
		credentialStore,
		anonymousDeviceBindingStore,
		shardDirectory,
		options...,
	)
	wechatLogin := application.NewFederatedLoginFacade(
		authService,
		externalProviderRuntime.wechat,
		nil,
	)

	pending, err := wechatLogin.Login(
		context.Background(),
		"sandbox-wechat-avatar-001",
		"device-social-1",
		"ios",
		"1.0.0",
		testAgreementVersion,
		testPrivacyVersion,
	)
	if err != nil {
		t.Fatalf("social authorization: %v", err)
	}
	if pending.Status != "phoneBindingRequired" || pending.Session != nil {
		t.Fatalf("first social authorization must not issue a session: %#v", pending)
	}
	var preBindingAccounts int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM user_profiles`,
	).Scan(&preBindingAccounts); err != nil {
		t.Fatalf("count pre-binding accounts: %v", err)
	}
	if preBindingAccounts != 0 {
		t.Fatalf("social authorization created %d accounts before phone binding", preBindingAccounts)
	}

	result := completeFederatedBindingFromPending(
		t,
		authService,
		pending,
		"+8618013813903",
	)

	var profileAvatarURL string
	var profileAvatarVersion int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COALESCE(avatar_url, ''), avatar_version FROM user_profiles WHERE user_id = $1`,
		result.OwnerID,
	).Scan(&profileAvatarURL, &profileAvatarVersion); err != nil {
		t.Fatalf("query profile avatar version: %v", err)
	}
	if profileAvatarURL == "" {
		t.Fatal("expected social login to seed avatar_url")
	}
	if profileAvatarVersion != 1 {
		t.Fatalf("expected social login to seed avatar_version=1, got %d", profileAvatarVersion)
	}

	var personaAvatarURL string
	var personaAvatarVersion int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COALESCE(avatar_url, ''), avatar_version FROM personas WHERE user_id = $1`,
		result.OwnerID,
	).Scan(&personaAvatarURL, &personaAvatarVersion); err != nil {
		t.Fatalf("query persona avatar version: %v", err)
	}
	if personaAvatarURL != profileAvatarURL {
		t.Fatalf("expected default persona avatar_url to inherit profile avatar, got %q vs %q", personaAvatarURL, profileAvatarURL)
	}
	if personaAvatarVersion != profileAvatarVersion {
		t.Fatalf("expected default persona avatar_version=%d, got %d", profileAvatarVersion, personaAvatarVersion)
	}
}

func TestLogin_ExistingCredentialReturnsOwner(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		t.Fatalf("load shard directory: %v", err)
	}
	credentialStore, err := credentialpersistence.NewPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("credential store: %v", err)
	}
	credentialCommands := credentialapp.NewCredentialCommandFacade(
		credentialStore,
	)
	options := testAccountPacketOptions(t)
	options = append(
		options,
		application.WithAccessTokenSigner(testAccessSigner),
		application.WithCredentialCommands(credentialCommands),
	)
	authService := application.NewAuthService(
		persistence.NewPgProfileStore(pgPool),
		userpersistence.NewPgPersonaStore(pgPool),
		credentialStore,
		userpersistence.NewPgAnonymousDeviceBindingStore(pgPool),
		shardDirectory,
		options...,
	)
	wechatLogin := application.NewFederatedLoginFacade(
		authService,
		externalProviderRuntime.wechat,
		nil,
	)
	firstLogin := completeWechatPhoneBinding(
		t,
		authService,
		wechatLogin,
		"sandbox-wechat-existing",
		"+8618013813904",
	)
	secondLogin, err := wechatLogin.Login(
		context.Background(),
		"sandbox-wechat-existing",
		"device-existing",
		"ios",
		"1.0.0",
		testAgreementVersion,
		testPrivacyVersion,
	)
	if err != nil {
		t.Fatalf("second WeChat credential login failed: %v", err)
	}
	if secondLogin.Status != "authenticated" || secondLogin.Session == nil {
		t.Fatalf("existing federated credential must return a session: %#v", secondLogin)
	}
	if secondLogin.Session.OwnerID != firstLogin.OwnerID {
		t.Errorf(
			"expected existing credential ownerId=%s, got %s",
			firstLogin.OwnerID,
			secondLogin.Session.OwnerID,
		)
	}
}

func TestBindPhoneCredential_ExistingAccountDoesNotRequireFederatedTicket(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const (
		ownerID = "settings-bind-owner"
		phone   = "+8618013813905"
	)
	createTestProfile(t, ownerID, "设置页绑定账号")
	createTestPersona(t, "settings-bind-persona", ownerID, "设置页绑定账号", true)

	send := doRequest(
		t,
		http.MethodPost,
		"/auth/otp/send",
		`{"phone":"`+phone+`","deviceId":"settings-device","platform":"ios","appVersion":"1.0.0","sourceOperation":"bind_phone"}`,
		nil,
	)
	if send.Code != http.StatusOK {
		t.Fatalf("send settings bind-phone otp: got %d: %s", send.Code, send.Body.String())
	}
	sendBody := parseJSON(t, send)
	challengeID, _ := sendBody["challengeId"].(string)
	code, err := externalInteractionRuntime.captureBridge.readOTP(phone)
	if challengeID == "" || err != nil || code == "" {
		t.Fatalf(
			"settings bind-phone challenge/code missing: %#v err=%v",
			sendBody,
			err,
		)
	}

	bind := doRequest(
		t,
		http.MethodPost,
		"/owner/credentials/phone/bind",
		`{"phone":"`+phone+`","otpCode":"`+code+`","displayLabel":"本机号码"}`,
		authHeaders(ownerID),
	)
	if bind.Code != http.StatusOK {
		t.Fatalf("bind settings phone: got %d: %s", bind.Code, bind.Body.String())
	}
	var purpose string
	var bindingTicketID *string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT purpose, binding_ticket_id FROM authentication_challenges WHERE challenge_id=$1`,
		challengeID,
	).Scan(&purpose, &bindingTicketID); err != nil {
		t.Fatalf("query settings bind-phone challenge: %v", err)
	}
	if purpose != "bind_phone" || bindingTicketID != nil {
		t.Fatalf("settings bind-phone challenge must remain ticket-free: purpose=%q ticket=%v", purpose, bindingTicketID)
	}
}

func TestFederatedPhoneBinding_IsAtomicAndTicketSingleUse(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	authService, wechatLogin := newFederatedLoginTestRuntime(t)
	pending := startFederatedPhoneBinding(
		t,
		wechatLogin,
		"sandbox-wechat-single-use",
	)
	const phone = "+8618013813906"
	sendResult, code := sendFederatedBindingOtp(t, authService, pending, phone)
	command := federatedBindingCommand(
		pending,
		phone,
		sendResult.ChallengeID,
		code,
	)
	payload := `{"bindingTicket":"` + pending.BindingTicket +
		`","phone":"` + phone +
		`","otpCode":"` + code +
		`","challengeId":"` + sendResult.ChallengeID +
		`","deviceId":"device-social-1","platform":"ios","appVersion":"1.0.0","agreementVersion":"` +
		testAgreementVersion + `","privacyVersion":"` + testPrivacyVersion + `"}`

	grant, err := authService.CompleteFederatedPhoneBinding(
		context.Background(),
		command,
	)
	if err != nil || grant == nil || grant.OwnerID == "" {
		t.Fatalf("complete federated binding: grant=%#v err=%v", grant, err)
	}
	ownerID := grant.OwnerID

	bindingHandler, err := credentialhttp.NewFederatedPhoneBindingHandler(authService)
	if err != nil {
		t.Fatalf("build federated binding HTTP adapter: %v", err)
	}
	mux := http.NewServeMux()
	bindingHandler.RegisterRoutes(mux)
	replayRequest := httptest.NewRequest(
		http.MethodPost,
		"/auth/login/social/phone/complete",
		strings.NewReader(payload),
	)
	replayRequest.Header.Set("Content-Type", "application/json")
	replayRequest.Header.Set("X-Request-Id", "binding-replay-request")
	replayRequest.Header.Set("X-Trace-Id", "binding-replay-trace")
	replay := httptest.NewRecorder()
	mux.ServeHTTP(replay, replayRequest)
	if replay.Code == http.StatusOK {
		t.Fatalf("consumed ticket must reject replay: %s", replay.Body.String())
	}
	replayBody := parseJSON(t, replay)
	if replayBody["code"] != "USER.AUTH.challenge_consumed" {
		t.Fatalf("replayed ticket code=%v, want USER.AUTH.challenge_consumed", replayBody["code"])
	}
	if replayBody["requestId"] != "binding-replay-request" ||
		replayBody["traceId"] != "binding-replay-trace" {
		t.Fatalf("replay request/trace not observable: %#v", replayBody)
	}

	var profileCount, credentialCount, sessionCount int
	if err := pgPool.QueryRow(context.Background(), `SELECT COUNT(*) FROM user_profiles WHERE user_id=$1`, ownerID).Scan(&profileCount); err != nil {
		t.Fatalf("count federated profiles: %v", err)
	}
	if err := pgPool.QueryRow(context.Background(), `SELECT COUNT(*) FROM credential_bindings WHERE owner_id=$1`, ownerID).Scan(&credentialCount); err != nil {
		t.Fatalf("count federated credentials: %v", err)
	}
	if err := pgPool.QueryRow(context.Background(), `SELECT COUNT(*) FROM account_sessions WHERE account_id=$1`, ownerID).Scan(&sessionCount); err != nil {
		t.Fatalf("count federated sessions: %v", err)
	}
	if profileCount != 1 || credentialCount != 2 || sessionCount != 1 {
		t.Fatalf(
			"atomic completion/replay counts profile=%d credentials=%d sessions=%d",
			profileCount,
			credentialCount,
			sessionCount,
		)
	}

	var ticketStatus, ticketHash, challengeStatus, bindingTicketID string
	if err := pgPool.QueryRow(context.Background(), `
SELECT t.status, t.ticket_hash, c.status, c.binding_ticket_id
FROM federated_phone_binding_tickets t
JOIN authentication_challenges c ON c.binding_ticket_id=t.ticket_id
WHERE c.challenge_id=$1`, sendResult.ChallengeID).Scan(
		&ticketStatus,
		&ticketHash,
		&challengeStatus,
		&bindingTicketID,
	); err != nil {
		t.Fatalf("query consumed binding packet: %v", err)
	}
	ticketDigest := sha256.Sum256([]byte(pending.BindingTicket))
	if ticketStatus != "consumed" || challengeStatus != "completed" ||
		bindingTicketID == "" || ticketHash != hex.EncodeToString(ticketDigest[:]) {
		t.Fatalf(
			"binding packet state ticket=%q challenge=%q ref=%q hashMatches=%v",
			ticketStatus,
			challengeStatus,
			bindingTicketID,
			ticketHash == hex.EncodeToString(ticketDigest[:]),
		)
	}
}

func TestFederatedPhoneBinding_OtpMismatchIsRecoverableWithoutConsumingTicket(
	t *testing.T,
) {
	t.Cleanup(func() { cleanAll(t) })
	authService, wechatLogin := newFederatedLoginTestRuntime(t)
	pending := startFederatedPhoneBinding(
		t,
		wechatLogin,
		"sandbox-wechat-otp-recovery",
	)
	const phone = "+8618013813910"
	sendResult, code := sendFederatedBindingOtp(t, authService, pending, phone)
	wrongCode := "000000"
	if wrongCode == code {
		wrongCode = "999999"
	}
	_, err := authService.CompleteFederatedPhoneBinding(
		context.Background(),
		federatedBindingCommand(
			pending,
			phone,
			sendResult.ChallengeID,
			wrongCode,
		),
	)
	assertLoginAppErrorCode(t, err, "USER.AUTH.otp_mismatch")

	var ticketStatus, challengeStatus string
	var failedAttempts int
	if err := pgPool.QueryRow(context.Background(), `
SELECT t.status, c.status, c.failed_attempts
FROM federated_phone_binding_tickets t
JOIN authentication_challenges c ON c.binding_ticket_id=t.ticket_id
WHERE c.challenge_id=$1`, sendResult.ChallengeID).Scan(
		&ticketStatus,
		&challengeStatus,
		&failedAttempts,
	); err != nil {
		t.Fatalf("query mismatched binding state: %v", err)
	}
	if ticketStatus != "pending" || challengeStatus != "pending" ||
		failedAttempts != 1 {
		t.Fatalf(
			"mismatch ticket=%q challenge=%q attempts=%d",
			ticketStatus,
			challengeStatus,
			failedAttempts,
		)
	}
	var accountCount, sessionCount int
	if err := pgPool.QueryRow(context.Background(), `SELECT COUNT(*) FROM user_profiles`).Scan(&accountCount); err != nil {
		t.Fatalf("count accounts after mismatch: %v", err)
	}
	if err := pgPool.QueryRow(context.Background(), `SELECT COUNT(*) FROM account_sessions`).Scan(&sessionCount); err != nil {
		t.Fatalf("count sessions after mismatch: %v", err)
	}
	if accountCount != 0 || sessionCount != 0 {
		t.Fatalf("mismatch created accounts=%d sessions=%d", accountCount, sessionCount)
	}

	grant, err := authService.CompleteFederatedPhoneBinding(
		context.Background(),
		federatedBindingCommand(
			pending,
			phone,
			sendResult.ChallengeID,
			code,
		),
	)
	if err != nil || grant == nil || grant.OwnerID == "" {
		t.Fatalf("correct OTP must recover the pending ticket: grant=%#v err=%v", grant, err)
	}
}

func TestFederatedPhoneBinding_PhoneConflictRetainsRecoverableTicket(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const (
		existingOwner    = "existing-phone-owner"
		existingPhone    = "+8618013813907"
		replacementPhone = "+8618013813908"
	)
	createTestProfile(t, existingOwner, "已有手机号账号")
	createTestPersona(t, "existing-phone-persona", existingOwner, "已有手机号账号", true)
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE user_profiles SET phone=$2 WHERE user_id=$1`,
		existingOwner,
		existingPhone,
	); err != nil {
		t.Fatalf("set existing profile phone: %v", err)
	}
	createTestCredential(t, "existing-phone-credential", existingOwner, "phone", existingPhone)

	authService, wechatLogin := newFederatedLoginTestRuntime(t)
	pending := startFederatedPhoneBinding(
		t,
		wechatLogin,
		"sandbox-wechat-existing-phone-owner",
	)
	challenge, code := sendFederatedBindingOtp(
		t,
		authService,
		pending,
		existingPhone,
	)
	grant, err := authService.CompleteFederatedPhoneBinding(
		context.Background(),
		federatedBindingCommand(
			pending,
			existingPhone,
			challenge.ChallengeID,
			code,
		),
	)
	if grant != nil {
		t.Fatalf("phone conflict must not issue a session: %#v", grant)
	}
	assertLoginAppErrorCode(t, err, "USER.AUTH.credential_conflict")

	var profileCount, socialBindingCount, sessionCount int
	if err := pgPool.QueryRow(context.Background(), `SELECT COUNT(*) FROM user_profiles`).Scan(&profileCount); err != nil {
		t.Fatalf("count profiles after conflict: %v", err)
	}
	if err := pgPool.QueryRow(context.Background(), `
SELECT COUNT(*) FROM credential_bindings
	WHERE credential_type='federated_slot_a' AND is_active=true`).Scan(&socialBindingCount); err != nil {
		t.Fatalf("count social bindings after conflict: %v", err)
	}
	if err := pgPool.QueryRow(context.Background(), `SELECT COUNT(*) FROM account_sessions`).Scan(&sessionCount); err != nil {
		t.Fatalf("count sessions after conflict: %v", err)
	}
	if profileCount != 1 || socialBindingCount != 0 || sessionCount != 0 {
		t.Fatalf(
			"phone conflict changed state: profiles=%d social=%d sessions=%d",
			profileCount,
			socialBindingCount,
			sessionCount,
		)
	}

	var ticketStatus, challengeStatus string
	if err := pgPool.QueryRow(context.Background(), `
SELECT t.status, c.status
FROM federated_phone_binding_tickets t
JOIN authentication_challenges c ON c.binding_ticket_id=t.ticket_id
WHERE c.challenge_id=$1`, challenge.ChallengeID).Scan(
		&ticketStatus,
		&challengeStatus,
	); err != nil {
		t.Fatalf("query conflict state: %v", err)
	}
	if ticketStatus != "pending" || challengeStatus != "pending" {
		t.Fatalf(
			"ticket=%q challenge=%q, want pending/pending after conflict",
			ticketStatus,
			challengeStatus,
		)
	}

	replacementChallenge, replacementCode := sendFederatedBindingOtp(
		t,
		authService,
		pending,
		replacementPhone,
	)
	grant, err = authService.CompleteFederatedPhoneBinding(
		context.Background(),
		federatedBindingCommand(
			pending,
			replacementPhone,
			replacementChallenge.ChallengeID,
			replacementCode,
		),
	)
	if err != nil || grant == nil || grant.OwnerID == "" {
		t.Fatalf("replacement phone must complete binding: grant=%#v err=%v", grant, err)
	}
	if grant.OwnerID == existingOwner {
		t.Fatalf("replacement phone must create a distinct account, got owner=%q", grant.OwnerID)
	}
}

func TestGenericCredentialBindRouteIsNotPublic(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "bind_owner", "bind_user")
	createTestCredential(t, "cred_phone", "bind_owner", "phone", "hash_phone_bind")

	rec := doRequest(t, http.MethodPost, "/owner/credentials/bind",
		`{"credentialType":"federated_slot_a","credentialKey":"federated_identity_123","displayLabel":"联邦账号"}`,
		authHeaders("bind_owner"))
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf(
			"generic bind must not accept client-supplied stable identity: got %d: %s",
			rec.Code,
			rec.Body.String(),
		)
	}
}

func TestUnbindCredential_LastCredentialForbidden(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "unbind_owner", "unbind_user")
	createTestCredential(t, "cred_only", "unbind_owner", "phone", "hash_only_phone")

	// 尝试解绑唯一凭证应被拒绝
	rec := doRequest(t, http.MethodDelete, "/owner/credentials/phone", "", authHeaders("unbind_owner"))
	if rec.Code == http.StatusOK {
		t.Fatal("expected error when unbinding the last credential")
	}
}

func TestUnbindCredential_KeepsRemaining(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "multi_cred_owner", "multi_cred_user")
	createTestCredential(t, "c_phone", "multi_cred_owner", "phone", "hash_multi_phone")
	createTestCredential(t, "c_federated", "multi_cred_owner", "federated_slot_a", "federated_identity_multi")

	// 解绑联邦凭证（还有手机号剩余）
	rec := doRequest(t, http.MethodDelete, "/owner/credentials/federated_slot_a", "", authHeaders("multi_cred_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("unbind federated credential: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	// DB 验证：手机号仍存在
	var phoneCount int
	_ = pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM credential_bindings WHERE owner_id = $1 AND credential_type = 'phone' AND is_active = true`,
		"multi_cred_owner").Scan(&phoneCount)
	if phoneCount != 1 {
		t.Errorf("phone credential should remain after unbinding federated credential, got count=%d", phoneCount)
	}
}

func TestListCredentials(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "list_cred_owner", "list_cred_user")
	createTestCredential(t, "lc1", "list_cred_owner", "phone", "hash_lc_phone")
	createTestCredential(t, "lc2", "list_cred_owner", "apple", "apple_subject_123")

	rec := doRequest(t, http.MethodGet, "/owner/credentials", "", authHeaders("list_cred_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("list credentials: expected 200, got %d", rec.Code)
	}
	result := parseJSON(t, rec)
	creds, _ := result["credentials"].([]any)
	if len(creds) != 2 {
		t.Errorf("expected 2 credentials, got %d", len(creds))
	}
	// 验证 SECRET 字段 credentialKey 不在响应中
	for _, c := range creds {
		cm, _ := c.(map[string]any)
		if _, hasKey := cm["credentialKey"]; hasKey {
			t.Error("credentialKey (SECRET) should NOT be exposed in list response")
		}
	}
}
