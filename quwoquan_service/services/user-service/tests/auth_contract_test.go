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

	ownerID := "uo_01_ad_00aa_legacyanonymousowner00000001"
	subAccountID := "us_01_00aa_legacyanonymoussub000000001"
	createTestProfile(t, ownerID, "legacy-anon")
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE user_profiles
		    SET account_state = 'anonymous',
		        identity_origin = 'anonymous_device',
		        anonymous_retention_policy = 'preserve'
		  WHERE user_id = $1`,
		ownerID,
	); err != nil {
		t.Fatalf("update legacy anonymous profile: %v", err)
	}
	createTestPersonaFull(t, "", ownerID, subAccountID, "LegacyAnon", "open", true, true)
	createTestCredential(t, "cred_legacy_anonymous", ownerID, "anonymous_device", "fp_legacy_device")

	rec := doRequest(
		t,
		http.MethodPost,
		"/v1/auth/login/anonymous",
		`{"installId":"install-legacy-1","deviceFingerprintHash":"fp_legacy_device","platform":"android","appVersion":"2.0.0"}`,
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
		  WHERE device_fingerprint_hash = 'fp_legacy_device'`,
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
