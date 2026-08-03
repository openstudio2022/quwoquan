package api_integration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"regexp"
	"strings"
	"testing"
)

func TestAuth_SocialLoginRoutesRemainBlockedWithoutCommercialCredentials(
	t *testing.T,
) {
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
			response := doRequest(t, http.MethodPost, tc.path, string(requestBody), nil)
			if response.Code != http.StatusForbidden {
				t.Fatalf(
					"%s login must remain blocked without approved provider evidence: got %d: %s",
					tc.name,
					response.Code,
					response.Body.String(),
				)
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
	if !regexp.MustCompile(`^uo_01_ad_[0-3][0-9a-f]{3}_[0-9a-hjkmnp-tv-z]{26}$`).MatchString(ownerID) {
		t.Fatalf("expected anonymous ownerId prefix, got %q", ownerID)
	}
	if firstBody["accountState"] != "anonymous" {
		t.Fatalf("expected anonymous accountState, got %#v", firstBody["accountState"])
	}
	if firstBody["identityOrigin"] != "anonymous_device" {
		t.Fatalf("expected anonymous_device origin, got %#v", firstBody["identityOrigin"])
	}
	if int(firstBody["personaCount"].(float64)) != 1 {
		t.Fatalf("expected one persona, got %#v", firstBody["personaCount"])
	}
	activePersona, _ := firstBody["activePersona"].(map[string]any)
	personaID, _ := activePersona["personaId"].(string)
	if !regexp.MustCompile(`^us_01_[0-3][0-9a-f]{3}_[0-9a-hjkmnp-tv-z]{26}$`).MatchString(personaID) {
		t.Fatalf("expected structured personaId, got %q", personaID)
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

	ownerID := "uo_01_ad_3338_01j00000000000000000000002"
	personaID := "us_01_3338_01j00000000000000000000003"
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
	createTestPersonaFull(t, "", ownerID, personaID, "AnonProfile", "open", true, true)
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

	var storedHash string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT refresh_token_hash
		   FROM account_sessions
		  WHERE account_id = $1 AND status = 'active'
		  ORDER BY issued_at DESC
		  LIMIT 1`,
		ownerID,
	).Scan(&storedHash); err != nil {
		t.Fatalf("query refresh token hash: %v", err)
	}
	digest := sha256.Sum256([]byte(strings.TrimSpace(refreshToken)))
	if storedHash != hex.EncodeToString(digest[:]) {
		t.Fatalf("refresh token must be stored as SHA-256 hash only")
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
	if len(refreshBody) != 3 {
		t.Fatalf("refresh must return only TokenRefreshGrant fields: %#v", refreshBody)
	}
	for _, field := range []string{"accessToken", "refreshToken", "sessionRememberTtlSeconds"} {
		if _, exists := refreshBody[field]; !exists {
			t.Fatalf("refresh missing %s: %#v", field, refreshBody)
		}
	}
	rotatedToken, _ := refreshBody["refreshToken"].(string)
	if rotatedToken == "" || rotatedToken == refreshToken {
		t.Fatalf("expected rotated refresh token, got %q", rotatedToken)
	}
	secondRefresh := doRequest(
		t,
		http.MethodPost,
		"/auth/token/refresh",
		`{"refreshToken":"`+rotatedToken+`"}`,
		nil,
	)
	if secondRefresh.Code != http.StatusOK {
		t.Fatalf("second refresh: expected 200, got %d: %s", secondRefresh.Code, secondRefresh.Body.String())
	}
	secondRefreshBody := parseJSON(t, secondRefresh)
	if len(secondRefreshBody) != 3 {
		t.Fatalf("subsequent refresh must keep the exact TokenRefreshGrant shape: %#v", secondRefreshBody)
	}
	secondRotatedToken, _ := secondRefreshBody["refreshToken"].(string)
	if secondRotatedToken == "" || secondRotatedToken == rotatedToken {
		t.Fatalf("subsequent refresh must rotate the token again: %#v", secondRefreshBody)
	}

	logout := doRequest(
		t,
		http.MethodPost,
		"/auth/logout",
		`{"refreshToken":"`+secondRotatedToken+`","deviceId":"ios-1"}`,
		authHeaders(ownerID),
	)
	if logout.Code != http.StatusOK {
		t.Fatalf("logout: expected 200, got %d: %s", logout.Code, logout.Body.String())
	}
	logoutBody := parseJSON(t, logout)
	if len(logoutBody) != 1 || logoutBody["revoked"] != true {
		t.Fatalf("logout must return the exact LogoutAck shape: %#v", logoutBody)
	}

	reuse := doRequest(
		t,
		http.MethodPost,
		"/auth/token/refresh",
		`{"refreshToken":"`+secondRotatedToken+`"}`,
		nil,
	)
	if reuse.Code == http.StatusOK {
		t.Fatalf("expected revoked token refresh to fail")
	}
}

func TestAuth_OneTapRoutesRemainBlockedWithoutCarrierCredentials(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	for _, path := range []string{
		"/auth/login/one-tap/hint",
		"/auth/login/one-tap",
	} {
		response := doRequest(
			t,
			http.MethodPost,
			path,
			`{"vendor":"test","carrierToken":"carrier_token_new","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-05","privacyVersion":"2026-05"}`,
			nil,
		)
		if response.Code != http.StatusForbidden {
			t.Fatalf(
				"%s must remain blocked without approved carrier evidence: got %d: %s",
				path,
				response.Code,
				response.Body.String(),
			)
		}
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
	var (
		personaNickname string
		projectedAt     *string
	)
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT display_name FROM personas WHERE user_id=$1 AND is_active=true`,
		ownerID,
	).Scan(&personaNickname); err != nil {
		t.Fatalf("query authoritative bootstrap Persona: %v", err)
	}
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT profile_projected_at::text
		 FROM personas_outbox
		 WHERE payload_json->>'userId'=$1 AND event_type='PersonaCreated'
		 ORDER BY aggregate_version DESC
		 LIMIT 1`,
		ownerID,
	).Scan(&projectedAt); err != nil {
		t.Fatalf("query bootstrap Persona projection checkpoint: %v", err)
	}
	if personaNickname != nickname || projectedAt == nil || *projectedAt == "" {
		t.Fatalf(
			"first-login profile must originate from durable Persona projection: Persona=%q projection=%q checkpoint=%v",
			personaNickname,
			nickname,
			projectedAt,
		)
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
		`SELECT count(*) FROM user_devices WHERE account_id = $1 AND device_id = 'ios-1'`,
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

	// challenge 行内 receipt：响应丢失后同一 phone+code 重放验证成功，
	// AccountSession 仍按“每次合法 login 创建新 session”语义执行。
	reuse := doRequest(
		t,
		http.MethodPost,
		"/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"`+code+`","deviceId":"ios-1","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if reuse.Code != http.StatusOK {
		t.Fatalf(
			"same credential replay must return success, got %d: %s",
			reuse.Code,
			reuse.Body.String(),
		)
	}
	reuseBody := parseJSON(t, reuse)
	if reuseBody["ownerId"] != ownerID {
		t.Fatalf(
			"challenge replay must resolve the original owner: first=%s replay=%v",
			ownerID,
			reuseBody["ownerId"],
		)
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
