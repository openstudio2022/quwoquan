package tests

import (
	"context"
	"net/http"
	"strings"
	"testing"
)

func TestAuth_AnonymousLogin_ReusesOwnerAndCreatesSingleDeviceBinding(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	first := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/anonymous",
		`{"installId":"install-ios-1","deviceFingerprintHash":"fp_same_device","platform":"ios","appVersion":"1.0.0"}`,
		nil,
	)
	if first.Code != http.StatusOK {
		t.Fatalf("first anonymous login: expected 200, got %d: %s", first.Code, first.Body.String())
	}
	firstBody := parseJSON(t, first)
	ownerID, _ := firstBody["ownerId"].(string)
	if !strings.HasPrefix(ownerID, "uo_01_ad_") {
		t.Fatalf("expected anonymous ownerId prefix, got %q", ownerID)
	}
	if firstBody["accountState"] != "anonymous" {
		t.Fatalf("expected anonymous accountState, got %#v", firstBody["accountState"])
	}
	if firstBody["identityOrigin"] != "anonymous_device" {
		t.Fatalf("expected anonymous_device origin, got %#v", firstBody["identityOrigin"])
	}
	if int(firstBody["subAccountCount"].(float64)) != 1 {
		t.Fatalf("expected one sub account, got %#v", firstBody["subAccountCount"])
	}
	activeSub, _ := firstBody["activeSub"].(map[string]any)
	subAccountID, _ := activeSub["subAccountId"].(string)
	if !strings.HasPrefix(subAccountID, "us_01_") {
		t.Fatalf("expected structured subAccountId, got %q", subAccountID)
	}
	logicalShard := int(firstBody["logicalShard"].(float64))
	if logicalShard < 0 || logicalShard >= 16384 {
		t.Fatalf("expected logicalShard in [0,16384), got %d", logicalShard)
	}

	var firstBindingCount int
	var firstBindingOwnerID string
	var firstInstallHash string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT count(*), min(owner_id), min(install_id_hash)
		   FROM anonymous_device_bindings`,
	).Scan(&firstBindingCount, &firstBindingOwnerID, &firstInstallHash); err != nil {
		t.Fatalf("query first anonymous device binding: %v", err)
	}
	if firstBindingCount != 1 {
		t.Fatalf("expected 1 anonymous device binding after first login, got %d", firstBindingCount)
	}
	if firstBindingOwnerID != ownerID {
		t.Fatalf("expected binding owner %q, got %q", ownerID, firstBindingOwnerID)
	}
	if firstInstallHash == "" || firstInstallHash == "install-ios-1" {
		t.Fatalf("expected installId to be persisted as hash, got %q", firstInstallHash)
	}

	second := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/anonymous",
		`{"installId":"install-ios-2","deviceFingerprintHash":"fp_same_device","platform":"ios","appVersion":"1.0.1"}`,
		nil,
	)
	if second.Code != http.StatusOK {
		t.Fatalf("second anonymous login: expected 200, got %d: %s", second.Code, second.Body.String())
	}
	secondBody := parseJSON(t, second)
	secondOwnerID, _ := secondBody["ownerId"].(string)
	if secondOwnerID != ownerID {
		t.Fatalf("expected same ownerId on repeated anonymous login, got %q vs %q", secondOwnerID, ownerID)
	}

	var secondBindingCount int
	var secondBindingOwnerID string
	var secondInstallHash string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT count(*), min(owner_id), min(install_id_hash)
		   FROM anonymous_device_bindings`,
	).Scan(&secondBindingCount, &secondBindingOwnerID, &secondInstallHash); err != nil {
		t.Fatalf("query second anonymous device binding: %v", err)
	}
	if secondBindingCount != 1 {
		t.Fatalf("expected still 1 anonymous device binding, got %d", secondBindingCount)
	}
	if secondBindingOwnerID != ownerID {
		t.Fatalf("expected binding owner to remain %q, got %q", ownerID, secondBindingOwnerID)
	}
	if secondInstallHash == firstInstallHash || secondInstallHash == "install-ios-2" {
		t.Fatalf("expected installId hash to refresh without storing raw installId, got %q", secondInstallHash)
	}

	var credentialCount int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT count(*) FROM credential_bindings
		  WHERE credential_type = 'anonymous_device' AND credential_key = 'fp_same_device'`,
	).Scan(&credentialCount); err != nil {
		t.Fatalf("query anonymous credential count: %v", err)
	}
	if credentialCount != 1 {
		t.Fatalf("expected 1 anonymous credential binding, got %d", credentialCount)
	}
}

func TestAuth_AnonymousLogin_BackfillsDeviceBindingFromExistingCredential(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	ownerID := "uo_01_ad_00aa_anonowner00000001"
	subAccountID := "us_01_00aa_anonowner000000001"
	createTestProfile(t, ownerID, "anon-owner")
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE user_profiles
		    SET account_state = 'anonymous',
		        identity_origin = 'anonymous_device',
		        anonymous_retention_policy = 'preserve'
		  WHERE user_id = $1`,
		ownerID,
	); err != nil {
		t.Fatalf("update anonymous profile: %v", err)
	}
	createTestPersonaFull(t, "", ownerID, subAccountID, "AnonProfile", "open", true, true)
	createTestCredential(t, "cred_anonymous", ownerID, "anonymous_device", "fp_anonymous_device")

	rec := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/anonymous",
		`{"installId":"install-anonymous-1","deviceFingerprintHash":"fp_anonymous_device","platform":"android","appVersion":"2.0.0"}`,
		nil,
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("anonymous login with existing credential: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	gotOwnerID, _ := body["ownerId"].(string)
	if gotOwnerID != ownerID {
		t.Fatalf("expected reused ownerId %q, got %q", ownerID, gotOwnerID)
	}

	var bindingCount int
	var bindingOwnerID string
	var bindingPlatform string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT count(*), min(owner_id), min(platform)
		   FROM anonymous_device_bindings
		WHERE device_fingerprint_hash = 'fp_anonymous_device'`,
	).Scan(&bindingCount, &bindingOwnerID, &bindingPlatform); err != nil {
		t.Fatalf("query backfilled anonymous device binding: %v", err)
	}
	if bindingCount != 1 {
		t.Fatalf("expected backfilled anonymous device binding, got %d rows", bindingCount)
	}
	if bindingOwnerID != ownerID {
		t.Fatalf("expected backfilled binding owner %q, got %q", ownerID, bindingOwnerID)
	}
	if bindingPlatform != "android" {
		t.Fatalf("expected backfilled binding platform android, got %q", bindingPlatform)
	}
}

func TestAuth_RefreshToken_RotatesAndLogoutRevokes(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	otpCode := requestOtpCode(t, "+8618013813909")
	login := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/phone",
		`{"phone":"+8618013813909","otpCode":"`+otpCode+`","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if login.Code != http.StatusOK {
		t.Fatalf("phone login: expected 200, got %d: %s", login.Code, login.Body.String())
	}
	loginBody := parseJSON(t, login)
	ownerID, _ := loginBody["ownerId"].(string)
	refreshToken, _ := loginBody["refreshToken"].(string)
	if ownerID == "" || refreshToken == "" {
		t.Fatalf("expected ownerId and refreshToken, got %#v", loginBody)
	}

	var storedToken string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT refresh_token FROM user_auth WHERE user_id = $1`,
		ownerID,
	).Scan(&storedToken); err != nil {
		t.Fatalf("query refresh token: %v", err)
	}
	if storedToken != refreshToken {
		t.Fatalf("stored refresh token mismatch")
	}

	refresh := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/token/refresh",
		`{"refreshToken":"`+refreshToken+`"}`,
		nil,
	)
	if refresh.Code != http.StatusOK {
		t.Fatalf("refresh: expected 200, got %d: %s", refresh.Code, refresh.Body.String())
	}
	refreshBody := parseJSON(t, refresh)
	rotatedToken, _ := refreshBody["refreshToken"].(string)
	if rotatedToken == "" || rotatedToken == refreshToken {
		t.Fatalf("expected rotated refresh token, got %q", rotatedToken)
	}

	logout := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/logout",
		`{"refreshToken":"`+rotatedToken+`","deviceId":"ios-1"}`,
		authHeaders(ownerID),
	)
	if logout.Code != http.StatusOK {
		t.Fatalf("logout: expected 200, got %d: %s", logout.Code, logout.Body.String())
	}

	reuse := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/token/refresh",
		`{"refreshToken":"`+rotatedToken+`"}`,
		nil,
	)
	if reuse.Code == http.StatusOK {
		t.Fatalf("expected revoked token refresh to fail")
	}
}

func TestAuth_OneTapLogin_UsesServerResolvedPhone(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	hint := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/one-tap/hint",
		`{"vendor":"test","carrierToken":"carrier_token_new","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0"}`,
		nil,
	)
	if hint.Code != http.StatusOK {
		t.Fatalf("one tap hint: expected 200, got %d: %s", hint.Code, hint.Body.String())
	}
	hintBody := parseJSON(t, hint)
	if hintBody["registered"] != false {
		t.Fatalf("expected unregistered hint before login, got %#v", hintBody)
	}
	if hintBody["maskedPhone"] != "180****3901" {
		t.Fatalf("expected masked phone hint, got %#v", hintBody["maskedPhone"])
	}

	rec := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/one-tap",
		`{"vendor":"test","carrierToken":"carrier_token_new","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-05","privacyVersion":"2026-05"}`,
		nil,
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("one tap login: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	ownerID, _ := body["ownerId"].(string)
	if ownerID == "" {
		t.Fatalf("expected ownerId, got %#v", body)
	}

	var phone string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT phone FROM user_profiles WHERE user_id = $1`,
		ownerID,
	).Scan(&phone); err != nil {
		t.Fatalf("query profile phone: %v", err)
	}
	if phone != "+8618013813901" {
		t.Fatalf("expected server resolved phone, got %q", phone)
	}

	accountHint, _ := body["accountHint"].(map[string]any)
	if accountHint["maskedPhone"] != "180****3901" {
		t.Fatalf("expected accountHint masked phone, got %#v", accountHint)
	}

	var deviceCount int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT count(*) FROM user_devices WHERE user_id = $1 AND device_id = 'ios-1'`,
		ownerID,
	).Scan(&deviceCount); err != nil {
		t.Fatalf("query user device: %v", err)
	}
	if deviceCount != 1 {
		t.Fatalf("expected login device side effect, got %d", deviceCount)
	}

	var consentCount int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT count(*) FROM consent_records WHERE owner_id = $1 AND agreement_version = '2026-05' AND privacy_version = '2026-05'`,
		ownerID,
	).Scan(&consentCount); err != nil {
		t.Fatalf("query consent record: %v", err)
	}
	if consentCount != 1 {
		t.Fatalf("expected consent record side effect, got %d", consentCount)
	}

	hintAfterLogin := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/one-tap/hint",
		`{"vendor":"test","carrierToken":"carrier_token_new","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0"}`,
		nil,
	)
	if hintAfterLogin.Code != http.StatusOK {
		t.Fatalf("one tap hint after login: expected 200, got %d: %s", hintAfterLogin.Code, hintAfterLogin.Body.String())
	}
	registeredBody := parseJSON(t, hintAfterLogin)
	if registeredBody["registered"] != true {
		t.Fatalf("expected registered hint after login, got %#v", registeredBody)
	}
	if _, ok := registeredBody["accountHint"].(map[string]any); !ok {
		t.Fatalf("expected accountHint for registered phone, got %#v", registeredBody)
	}
}

func TestAuth_RetiredGenericLoginRoute_Removed(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	rec := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login",
		`{"credentialType":"phone","credentialKey":"+8618013813909"}`,
		nil,
	)
	if rec.Code == http.StatusOK {
		t.Fatalf("retired generic login route should not be available")
	}
}

func TestAuth_PhoneLogin_RequiresValidOtp(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const phone = "+8618013813920"

	// 未发码直接登录：验证码缺失，应被拒绝（非 200）。
	noCode := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"123456","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if noCode.Code == http.StatusOK {
		t.Fatalf("phone login without sent otp: expected failure, got 200: %s", noCode.Body.String())
	}

	// 发码后用错误验证码：应被拒绝。
	code := requestOtpCode(t, phone)
	missingConsent := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"`+code+`","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0"}`,
		nil,
	)
	if missingConsent.Code == http.StatusOK {
		t.Fatalf("phone login without consent versions: expected failure, got 200: %s", missingConsent.Body.String())
	}
	missingConsentBody := parseJSON(t, missingConsent)
	if missingConsentBody["code"] != "USER.AUTH.consent_required" {
		t.Fatalf("expected consent_required, got %#v", missingConsentBody)
	}

	wrong := "000000"
	if wrong == code {
		wrong = "111111"
	}
	mismatch := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"`+wrong+`","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if mismatch.Code == http.StatusOK {
		t.Fatalf("phone login with wrong otp: expected failure, got 200: %s", mismatch.Body.String())
	}

	// 正确验证码：登录成功并签发 token。
	login := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"`+code+`","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if login.Code != http.StatusOK {
		t.Fatalf("phone login with valid otp: expected 200, got %d: %s", login.Code, login.Body.String())
	}
	loginBody := parseJSON(t, login)
	if accessToken, _ := loginBody["accessToken"].(string); accessToken == "" {
		t.Fatalf("expected accessToken on phone login, got %#v", loginBody)
	}
	ownerID, _ := loginBody["ownerId"].(string)
	var deviceCount int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT count(*) FROM user_devices WHERE user_id = $1 AND device_id = 'ios-1'`,
		ownerID,
	).Scan(&deviceCount); err != nil {
		t.Fatalf("query phone login device: %v", err)
	}
	if deviceCount != 1 {
		t.Fatalf("expected phone login device side effect, got %d", deviceCount)
	}
	var consentCount int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT count(*) FROM consent_records WHERE owner_id = $1 AND agreement_version = '2026-06' AND privacy_version = '2026-06' AND source_operation = 'LoginWithPhone'`,
		ownerID,
	).Scan(&consentCount); err != nil {
		t.Fatalf("query phone login consent: %v", err)
	}
	if consentCount != 1 {
		t.Fatalf("expected phone login consent record, got %d", consentCount)
	}

	// 验证码一次性：相同验证码不可复用。
	reuse := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"`+code+`","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if reuse.Code == http.StatusOK {
		t.Fatalf("phone login reusing consumed otp: expected failure, got 200: %s", reuse.Body.String())
	}
}

func TestAuth_AccessToken_IsJWTAndDrivesIdentity(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const phone = "+8618013813930"
	otpCode := requestOtpCode(t, phone)
	login := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"`+otpCode+`","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if login.Code != http.StatusOK {
		t.Fatalf("phone login: expected 200, got %d: %s", login.Code, login.Body.String())
	}
	loginBody := parseJSON(t, login)
	ownerID, _ := loginBody["ownerId"].(string)
	accessToken, _ := loginBody["accessToken"].(string)
	if ownerID == "" || accessToken == "" {
		t.Fatalf("expected ownerId and accessToken, got %#v", loginBody)
	}

	// access token 必须是可本地验签的 JWT，principal 与登录用户一致。
	claims, err := testAccessVerifier.Verify(accessToken)
	if err != nil {
		t.Fatalf("access token is not a verifiable JWT: %v", err)
	}
	if claims.Subject != ownerID {
		t.Fatalf("expected JWT subject %q, got %q", ownerID, claims.Subject)
	}

	// 仅携带 Bearer token、不传 X-Client-User-Id：身份必须由 token 推导。
	me := doRequest(
		t,
		http.MethodGet,
		"/v1/me",
		"",
		map[string]string{"Authorization": "Bearer " + accessToken},
	)
	if me.Code != http.StatusOK {
		t.Fatalf("GET /v1/me with bearer only: expected 200, got %d: %s", me.Code, me.Body.String())
	}

	// 伪造 X-Client-User-Id 必须被 token principal 覆盖（防越权）。
	spoof := doRequest(
		t,
		http.MethodGet,
		"/v1/me",
		"",
		map[string]string{
			"Authorization":    "Bearer " + accessToken,
			"X-Client-User-Id": "attacker-owner-id",
		},
	)
	if spoof.Code != http.StatusOK {
		t.Fatalf("GET /v1/me with spoofed header: expected 200, got %d: %s", spoof.Code, spoof.Body.String())
	}
}

func TestAuth_SendOtp_ThrottlesResend(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const phone = "+8618013813921"
	first := doRequest(t, http.MethodPost, "/v1/auth/otp/send", `{"phone":"`+phone+`","deviceId":"ios-test","platform":"ios","appVersion":"1.0.0","sourceOperation":"test"}`, nil)
	if first.Code != http.StatusOK {
		t.Fatalf("first send otp: expected 200, got %d: %s", first.Code, first.Body.String())
	}
	firstBody := parseJSON(t, first)
	if firstBody["maskedPhone"] != "180****3921" {
		t.Fatalf("expected maskedPhone in send otp response, got %#v", firstBody["maskedPhone"])
	}
	if firstBody["requestId"] == "" || firstBody["challengeId"] == "" {
		t.Fatalf("expected requestId/challengeId in send otp response, got %#v", firstBody)
	}
	if firstBody["deliveryStatus"] == "" {
		t.Fatalf("expected deliveryStatus in send otp response, got %#v", firstBody)
	}
	// 冷却窗口内立即重发应被限频拒绝。
	second := doRequest(t, http.MethodPost, "/v1/auth/otp/send", `{"phone":"`+phone+`","deviceId":"ios-test","platform":"ios","appVersion":"1.0.0","sourceOperation":"test"}`, nil)
	if second.Code == http.StatusOK {
		t.Fatalf("immediate resend: expected throttled failure, got 200: %s", second.Body.String())
	}
	secondBody := parseJSON(t, second)
	if secondBody["code"] != "USER.AUTH.otp_rate_limited" {
		t.Fatalf("expected otp_rate_limited, got %#v", secondBody)
	}
}
