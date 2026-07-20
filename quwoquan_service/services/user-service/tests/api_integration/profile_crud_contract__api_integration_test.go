package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"testing"
)

func createProfileUpdateFixture(
	t *testing.T,
	ownerID string,
	nickname string,
) string {
	t.Helper()
	createTestProfile(t, ownerID, nickname)
	personaID := ownerID + "_persona"
	createTestPersona(t, personaID, ownerID, nickname, true, true)
	return personaID + "_sa"
}

func TestGetProfile_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "user_001", "alice")
	createTestPersona(t, "p_001", "user_001", "Alice Primary", true, true)

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/profile/user_001",
		"",
		authHeaders("user_001"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	profile, ok := result["profile"].(map[string]any)
	if !ok {
		t.Fatal("response missing profile field")
	}
	if profile["userId"] != "user_001" {
		t.Errorf("expected userId=user_001, got %v", profile["userId"])
	}
	if profile["nickname"] != "alice" {
		t.Errorf("expected nickname=alice, got %v", profile["nickname"])
	}
}

func TestGetProfile_NotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	rec := doRequest(
		t,
		http.MethodGet,
		"/user/profile/nonexistent",
		"",
		authHeaders("nonexistent"),
	)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.USER.not_found" {
		t.Errorf("expected USER.USER.not_found, got %v", result["code"])
	}
}

func TestUpdateProfile_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	personaID := createProfileUpdateFixture(t, "user_002", "bob")

	rec := doRequest(t, http.MethodPatch, "/user/profile",
		`{"nickname":"bob_updated","bio":"hello world","backgroundAssetId":"asset_bg_user_002","backgroundUrl":"https://cdn.example.com/bg-user-002.png"}`,
		authHeadersForPersona("user_002", personaID))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["nickname"] != "bob_updated" {
		t.Errorf("expected nickname=bob_updated, got %v", result["nickname"])
	}
	pv, _ := result["profileVersion"].(float64)
	if pv < 2 {
		t.Errorf("expected profileVersion >= 2, got %v", pv)
	}
	if result["nicknameCustomized"] != true {
		t.Errorf("expected nicknameCustomized=true after explicit rename, got %v", result["nicknameCustomized"])
	}
	if result["backgroundUrl"] != "https://cdn.example.com/bg-user-002.png" {
		t.Errorf("expected backgroundUrl to round-trip, got %v", result["backgroundUrl"])
	}
	if result["backgroundAssetId"] != "asset_bg_user_002" {
		t.Errorf("expected backgroundAssetId to round-trip, got %v", result["backgroundAssetId"])
	}
}

func TestUpdateProfile_RegionTagRefUpdatesDerivedDisplay(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	personaID := createProfileUpdateFixture(t, "region_owner", "region_user")

	rec := doRequest(t, http.MethodPatch, "/user/profile",
		`{"regionTagRef":"Topic/地理/行政区/中国/广东省/深圳市"}`,
		authHeadersForPersona("region_owner", personaID))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["region"] != "广东 深圳" || result["regionTagRef"] != "Topic/地理/行政区/中国/广东省/深圳市" {
		t.Fatalf("expected derived region + regionTagRef, got %#v", result)
	}
	if _, exists := result["regionCode"]; exists {
		t.Fatalf("regionCode must not be exposed in update response, got %#v", result)
	}
}

func TestUpdateProfile_InvalidRegionTagRefReturnsInvalidRegion(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	personaID := createProfileUpdateFixture(
		t,
		"invalid_region_owner",
		"invalid_region_user",
	)

	rec := doRequest(t, http.MethodPatch, "/user/profile",
		`{"regionTagRef":"Topic/旅行/城市/深圳"}`,
		authHeadersForPersona("invalid_region_owner", personaID))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.PROFILE.invalid_region" {
		t.Fatalf("expected USER.PROFILE.invalid_region, got %#v", result)
	}
}

func TestUpdateProfile_RejectsClientRegionDisplayWithoutTagRef(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	personaID := createProfileUpdateFixture(
		t,
		"display_region_owner",
		"display_region_user",
	)

	rec := doRequest(t, http.MethodPatch, "/user/profile",
		`{"region":"广东 深圳"}`,
		authHeadersForPersona("display_region_owner", personaID))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.PROFILE.invalid_region" {
		t.Fatalf("expected USER.PROFILE.invalid_region, got %#v", result)
	}
}

func TestUpdateProfile_DuplicateNicknameAllowed(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "user_003", "charlie")
	personaID := createProfileUpdateFixture(t, "user_004", "david")

	rec := doRequest(t, http.MethodPatch, "/user/profile",
		`{"nickname":"charlie"}`,
		authHeadersForPersona("user_004", personaID))
	if rec.Code != http.StatusOK {
		t.Fatalf("duplicate nickname should be allowed, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["nickname"] != "charlie" {
		t.Fatalf("expected duplicate nickname to persist, got %v", result["nickname"])
	}
	if result["nicknameCustomized"] != true {
		t.Fatalf("expected nicknameCustomized=true after rename, got %v", result["nicknameCustomized"])
	}
}

func TestUpdateProfile_RejectsBareBackgroundURL(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	personaID := createProfileUpdateFixture(
		t,
		"user_bare_cover",
		"bare_cover",
	)

	rec := doRequest(t, http.MethodPatch, "/user/profile",
		`{"backgroundUrl":"https://cdn.example.com/bare-cover.png"}`,
		authHeadersForPersona("user_bare_cover", personaID))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.PROFILE.invalid_media_asset" {
		t.Fatalf("expected invalid_media_asset, got %#v", result)
	}
}

func TestGetProfileEditSnapshot_ReturnsCommercialFields(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "profile_edit_owner", "owner_name")
	createTestPersonaFull(t, "profile_edit_persona", "profile_edit_owner", "profile_edit_sa", "Owner Persona", "open", true, true)
	createTestCredential(t, "cred_profile_edit_phone", "profile_edit_owner", "phone", "13800000001")
	_, err := pgPool.Exec(context.Background(), `
		UPDATE user_profiles
		SET avatar_asset_id=$2,
		    background_asset_id=$3,
		    gender=$4,
		    birth_date=$5,
		    region=$6,
		    region_code=$7,
		    bio=$8,
		    identity_tags=$9
		WHERE user_id=$1`,
		"profile_edit_owner",
		"asset_avatar_edit",
		"asset_cover_edit",
		"female",
		"1990-01-02",
		"广东 深圳",
		"Topic/地理/行政区/中国/广东省/深圳市",
		"签名",
		"{Audience/用户/职业/产品运营/产品经理,Audience/用户/兴趣偏好/旅行摄影/摄影}",
	)
	if err != nil {
		t.Fatalf("seed profile edit fields: %v", err)
	}
	_, err = pgPool.Exec(context.Background(),
		`UPDATE personas SET user_handle=$1 WHERE sub_account_id=$2`,
		"qw_profile_edit", "profile_edit_sa")
	if err != nil {
		t.Fatalf("seed persona handle: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/profile/edit-snapshot",
		"",
		authHeadersForPersona("profile_edit_owner", "profile_edit_sa"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["avatarAssetId"] != "asset_avatar_edit" {
		t.Fatalf("expected avatarAssetId, got %#v", result["avatarAssetId"])
	}
	if result["backgroundAssetId"] != "asset_cover_edit" || result["regionTagRef"] != "Topic/地理/行政区/中国/广东省/深圳市" {
		t.Fatalf("expected backgroundAssetId/regionTagRef, got %#v", result)
	}
	if _, exists := result["regionCode"]; exists {
		t.Fatalf("regionCode must not be exposed in edit snapshot, got %#v", result)
	}
	if result["userHandle"] != "qw_profile_edit" {
		t.Fatalf("expected readonly userHandle, got %v", result["userHandle"])
	}
	if result["occupationTagRef"] != "Audience/用户/职业/产品运营/产品经理" {
		t.Fatalf("expected occupation tag, got %v", result["occupationTagRef"])
	}
	interestRefs, ok := result["interestTagRefs"].([]any)
	if !ok || len(interestRefs) != 1 || interestRefs[0] != "Audience/用户/兴趣偏好/旅行摄影/摄影" {
		t.Fatalf("expected interest tag refs, got %#v", result["interestTagRefs"])
	}
	phone, ok := result["phoneCredential"].(map[string]any)
	if !ok || phone["credentialType"] != "phone" || phone["isBound"] != true {
		t.Fatalf("expected phone credential summary, got %#v", result["phoneCredential"])
	}
	qrCard, ok := result["qrCard"].(map[string]any)
	if !ok || !strings.Contains(strings.TrimSpace(fmt.Sprint(qrCard["qrPayload"])), "/u/qw_profile_edit?qr=") {
		t.Fatalf("expected qr card with token payload, got %#v", result["qrCard"])
	}
}

func TestGetProfileQRCard_IssuesOpaqueResolvableToken(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "qr_owner", "qr_owner_name")
	createTestPersonaFull(t, "qr_persona", "qr_owner", "qr_sa", "QR Persona", "open", true, true)
	_, err := pgPool.Exec(context.Background(),
		`UPDATE personas SET user_handle=$1 WHERE sub_account_id=$2`,
		"qw_qr_handle", "qr_sa")
	if err != nil {
		t.Fatalf("seed qr handle: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/profile/qr-card",
		"",
		authHeadersForPersona("qr_owner", "qr_sa"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	card := parseJSON(t, rec)
	payload := strings.TrimSpace(fmt.Sprint(card["qrPayload"]))
	if !strings.HasPrefix(payload, "https://") || !strings.Contains(payload, "/u/qw_qr_handle?qr=") {
		t.Fatalf("expected https qr payload with handle and token, got %q", payload)
	}
	if strings.Contains(payload, "qr_owner") || strings.Contains(payload, "138") {
		t.Fatalf("qr payload must not expose owner id or phone: %q", payload)
	}
	parsed, err := url.Parse(payload)
	if err != nil {
		t.Fatalf("parse qr payload: %v", err)
	}
	rawToken := parsed.Query().Get("qr")
	if rawToken == "" {
		t.Fatalf("expected opaque token in payload: %q", payload)
	}
	var tokenHash string
	if err := pgPool.QueryRow(context.Background(),
		`SELECT token_hash FROM profile_qr_tokens WHERE token_id=$1`,
		fmt.Sprint(card["qrTokenId"]),
	).Scan(&tokenHash); err != nil {
		t.Fatalf("query token hash: %v", err)
	}
	if tokenHash == "" || tokenHash == rawToken {
		t.Fatalf("expected stored hash, got tokenHash=%q raw=%q", tokenHash, rawToken)
	}

	resolveURL := "/public/profile/qr/resolve?handle=qw_qr_handle&qr=" + url.QueryEscape(rawToken)
	resolveRec := doRequest(t, http.MethodGet, resolveURL, "", nil)
	if resolveRec.Code != http.StatusOK {
		t.Fatalf("expected resolve 200, got %d: %s", resolveRec.Code, resolveRec.Body.String())
	}
	resolved := parseJSON(t, resolveRec)
	if resolved["subAccountId"] != "qr_sa" || resolved["userHandle"] != "qw_qr_handle" || resolved["scanStatus"] != "accepted" {
		t.Fatalf("unexpected resolve payload: %#v", resolved)
	}
}

func TestResolveProfileQRToken_InvalidToken(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	rec := doRequest(t, http.MethodGet, "/public/profile/qr/resolve?handle=missing&qr=invalid", "", nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.PROFILE.qr_token_invalid" {
		t.Fatalf("expected qr_token_invalid, got %#v", result)
	}
}

func TestGetProfile_CacheHit(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "user_005", "eve")

	rec1 := doRequest(
		t,
		http.MethodGet,
		"/user/profile/user_005",
		"",
		authHeaders("user_005"),
	)
	if rec1.Code != http.StatusOK {
		t.Fatalf("first GET: expected 200, got %d", rec1.Code)
	}

	rec2 := doRequest(
		t,
		http.MethodGet,
		"/user/profile/user_005",
		"",
		authHeaders("user_005"),
	)
	if rec2.Code != http.StatusOK {
		t.Fatalf("second GET (cache hit): expected 200, got %d", rec2.Code)
	}
}
