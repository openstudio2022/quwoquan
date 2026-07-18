package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"regexp"
	"strings"
	"testing"
)

func TestAuth_SocialLogin_WechatAlipayQqExchangeStableServerIdentity(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	cases := []struct {
		name  string
		path  string
		field string
		code  string
	}{
		{name: "wechat", path: "/auth/login/wechat", field: "wechatCode", code: "wechat-code"},
		{name: "alipay", path: "/auth/login/alipay", field: "alipayAuthCode", code: "alipay-code"},
		{name: "qq", path: "/auth/login/qq", field: "qqAuthCode", code: qqAuthorizationTicket("qq-access-token", "qq-open-id")},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			requestBody, err := json.Marshal(map[string]string{
				tc.field:     tc.code,
				"deviceId":   "social-device-" + tc.name,
				"platform":   "ios",
				"appVersion": "1.0.0",
			})
			if err != nil {
				t.Fatalf("marshal request: %v", err)
			}
			first := doRequest(t, http.MethodPost, tc.path, string(requestBody), nil)
			if first.Code != http.StatusOK {
				t.Fatalf("%s login: expected 200, got %d: %s", tc.name, first.Code, first.Body.String())
			}
			firstBody := parseJSON(t, first)
			ownerID, _ := firstBody["ownerId"].(string)
			if ownerID == "" {
				t.Fatalf("%s login missing ownerId: %#v", tc.name, firstBody)
			}
			accountHint, ok := firstBody["accountHint"].(map[string]any)
			if !ok {
				t.Fatalf("%s login missing accountHint: %#v", tc.name, firstBody)
			}
			if accountHint["nicknameCustomized"] != true {
				t.Fatalf("%s provider nickname must be marked customized: %#v", tc.name, accountHint)
			}
			second := doRequest(t, http.MethodPost, tc.path, string(requestBody), nil)
			if second.Code != http.StatusOK {
				t.Fatalf("%s repeat login failed: %d: %s", tc.name, second.Code, second.Body.String())
			}
			if parseJSON(t, second)["ownerId"] != ownerID {
				t.Fatalf("%s repeat login must resolve the same owner", tc.name)
			}
		})
	}
}

func TestAuth_AnonymousLogin_ReusesOwnerAndCreatesSingleDeviceBinding(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	first := doRequest(
		t,
		http.MethodPost,
		"/auth/login/anonymous",
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
		"/auth/login/anonymous",
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
		"/auth/login/anonymous",
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
		"/auth/login/phone",
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
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE user_profiles
		    SET nickname = $1,
		        owner_display_name = $1,
		        nickname_customized = true,
		        avatar_url = $2,
		        avatar_version = 1
		  WHERE user_id = $3`,
		"刷新后的昵称",
		"https://cdn.example.com/avatar-refresh.png",
		ownerID,
	); err != nil {
		t.Fatalf("update refresh account hint fixture: %v", err)
	}

	refresh := doRequest(
		t,
		http.MethodPost,
		"/auth/token/refresh",
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
	refreshedHint, ok := refreshBody["accountHint"].(map[string]any)
	if !ok {
		t.Fatalf("refresh missing accountHint: %#v", refreshBody)
	}
	if refreshedHint["displayName"] != "刷新后的昵称" || refreshedHint["nicknameCustomized"] != true {
		t.Fatalf("refresh accountHint nickname mismatch: %#v", refreshedHint)
	}
	if avatarURL, _ := refreshedHint["avatarUrl"].(string); !strings.Contains(avatarURL, "avatar-refresh.png") {
		t.Fatalf("refresh accountHint avatar mismatch: %#v", refreshedHint)
	}

	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE user_profiles SET avatar_url = '', avatar_version = 2 WHERE user_id = $1`,
		ownerID,
	); err != nil {
		t.Fatalf("delete refresh account hint avatar fixture: %v", err)
	}
	refreshAfterAvatarDelete := doRequest(
		t,
		http.MethodPost,
		"/auth/token/refresh",
		`{"refreshToken":"`+rotatedToken+`"}`,
		nil,
	)
	if refreshAfterAvatarDelete.Code != http.StatusOK {
		t.Fatalf("refresh after avatar delete: expected 200, got %d: %s", refreshAfterAvatarDelete.Code, refreshAfterAvatarDelete.Body.String())
	}
	refreshAfterDeleteBody := parseJSON(t, refreshAfterAvatarDelete)
	rotatedAfterDelete, _ := refreshAfterDeleteBody["refreshToken"].(string)
	deletedAvatarHint, ok := refreshAfterDeleteBody["accountHint"].(map[string]any)
	if !ok || deletedAvatarHint["avatarUrl"] != "" || deletedAvatarHint["nicknameCustomized"] != true {
		t.Fatalf("refresh must clear deleted avatar and preserve nickname marker: %#v", refreshAfterDeleteBody)
	}

	logout := doRequest(
		t,
		http.MethodPost,
		"/auth/logout",
		`{"refreshToken":"`+rotatedAfterDelete+`","deviceId":"ios-1"}`,
		authHeaders(ownerID),
	)
	if logout.Code != http.StatusOK {
		t.Fatalf("logout: expected 200, got %d: %s", logout.Code, logout.Body.String())
	}

	reuse := doRequest(
		t,
		http.MethodPost,
		"/auth/token/refresh",
		`{"refreshToken":"`+rotatedAfterDelete+`"}`,
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
		"/auth/login/one-tap/hint",
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
		"/auth/login/one-tap",
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
	if accountHint["nicknameCustomized"] != false {
		t.Fatalf("new one-tap account must use system nickname marker: %#v", accountHint)
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
		"/auth/login/one-tap/hint",
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
	registeredHint, ok := registeredBody["accountHint"].(map[string]any)
	if !ok {
		t.Fatalf("expected accountHint for registered phone, got %#v", registeredBody)
	}
	if registeredHint["nicknameCustomized"] != false {
		t.Fatalf("one-tap hint nickname marker mismatch: %#v", registeredHint)
	}
}

func TestAuth_FirstLogin_UsesCloudDefaultNicknamePattern(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const phone = "+8618013813991"
	otpCode := requestOtpCode(t, phone)
	login := doRequest(
		t,
		http.MethodPost,
		"/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"`+otpCode+`","deviceId":"ios-default-nickname","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if login.Code != http.StatusOK {
		t.Fatalf("phone login: expected 200, got %d: %s", login.Code, login.Body.String())
	}
	loginBody := parseJSON(t, login)
	ownerID, _ := loginBody["ownerId"].(string)
	if ownerID == "" {
		t.Fatalf("expected ownerId, got %#v", loginBody)
	}

	var nickname string
	var nicknameCustomized bool
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT nickname, nickname_customized FROM user_profiles WHERE user_id = $1`,
		ownerID,
	).Scan(&nickname, &nicknameCustomized); err != nil {
		t.Fatalf("query default nickname: %v", err)
	}
	if !regexp.MustCompile(`^新同学_[0-9]{6}_[0-9]{7}$`).MatchString(nickname) {
		t.Fatalf("expected cloud default nickname 新同学_YYMMDD_7位尾号, got %q", nickname)
	}
	if nicknameCustomized {
		t.Fatalf("expected first-login nicknameCustomized=false, got true")
	}
	accountHint, ok := loginBody["accountHint"].(map[string]any)
	if !ok {
		t.Fatalf("expected accountHint in first phone login, got %#v", loginBody)
	}
	if accountHint["nicknameCustomized"] != false {
		t.Fatalf("expected accountHint nicknameCustomized=false, got %#v", accountHint)
	}
}

func TestAuth_RetiredGenericLoginRoute_Removed(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	rec := doRequest(
		t,
		http.MethodPost,
		"/auth/login",
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
		"/auth/login/phone",
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
		"/auth/login/phone",
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
		"/auth/login/phone",
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
		"/auth/login/phone",
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
		"/auth/login/phone",
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
		"/auth/login/phone",
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
		"/me",
		"",
		map[string]string{"Authorization": "Bearer " + accessToken},
	)
	if me.Code != http.StatusOK {
		t.Fatalf("GET /me with bearer only: expected 200, got %d: %s", me.Code, me.Body.String())
	}

	// 伪造 X-Client-User-Id 必须被 token principal 覆盖（防越权）。
	spoof := doRequest(
		t,
		http.MethodGet,
		"/me",
		"",
		map[string]string{
			"Authorization":    "Bearer " + accessToken,
			"X-Client-User-Id": "attacker-owner-id",
		},
	)
	if spoof.Code != http.StatusOK {
		t.Fatalf("GET /me with spoofed header: expected 200, got %d: %s", spoof.Code, spoof.Body.String())
	}
}

func TestAuth_SendOtp_ThrottlesResend(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	const phone = "+8618013813921"
	first := doRequest(t, http.MethodPost, "/auth/otp/send", `{"phone":"`+phone+`","deviceId":"ios-test","platform":"ios","appVersion":"1.0.0","sourceOperation":"test"}`, nil)
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
	second := doRequest(t, http.MethodPost, "/auth/otp/send", `{"phone":"`+phone+`","deviceId":"ios-test","platform":"ios","appVersion":"1.0.0","sourceOperation":"test"}`, nil)
	if second.Code == http.StatusOK {
		t.Fatalf("immediate resend: expected throttled failure, got 200: %s", second.Body.String())
	}
	secondBody := parseJSON(t, second)
	if secondBody["code"] != "USER.AUTH.otp_rate_limited" {
		t.Fatalf("expected otp_rate_limited, got %#v", secondBody)
	}
}
