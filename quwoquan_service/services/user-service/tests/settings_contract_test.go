package tests

import (
	"context"
	"net/http"
	"testing"
)

func TestPrivacySettings_BlockedKeywordsRoundTrip(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "settings_user_1", "settings_user_1")

	patchRec := doRequest(
		t,
		http.MethodPatch,
		"/v1/user/settings/privacy",
		`{"blockedKeywords":["alpha"," beta ","alpha"],"profileVisibility":"friends"}`,
		authHeaders("settings_user_1"),
	)
	if patchRec.Code != http.StatusOK {
		t.Fatalf("patch privacy settings: expected 200, got %d: %s", patchRec.Code, patchRec.Body.String())
	}

	getRec := doRequest(
		t,
		http.MethodGet,
		"/v1/user/settings/privacy",
		"",
		authHeaders("settings_user_1"),
	)
	if getRec.Code != http.StatusOK {
		t.Fatalf("get privacy settings: expected 200, got %d: %s", getRec.Code, getRec.Body.String())
	}
	body := parseJSON(t, getRec)
	if body["profileVisibility"] != "friends" {
		t.Fatalf("expected profileVisibility=friends, got %#v", body["profileVisibility"])
	}
	blocked, ok := body["blockedKeywords"].([]any)
	if !ok {
		t.Fatalf("expected blockedKeywords array, got %#v", body["blockedKeywords"])
	}
	if len(blocked) != 2 || blocked[0] != "alpha" || blocked[1] != "beta" {
		t.Fatalf("expected normalized blockedKeywords [alpha beta], got %#v", blocked)
	}
}

func TestPrivacySettings_PreexistingNullRingtoneRowRemainsCompatible(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "settings_user_2", "settings_user_2")

	if _, err := pgPool.Exec(
		context.Background(),
		`
			INSERT INTO user_settings (user_id, default_incoming_call_ringtone_id, allow_caller_ringtone_override, blocked_keywords, updated_at)
			VALUES ($1, NULL, true, $2, NOW())
		`,
		"settings_user_2",
		[]string{"before"},
	); err != nil {
		t.Fatalf("seed user_settings with null ringtone: %v", err)
	}

	getRec := doRequest(
		t,
		http.MethodGet,
		"/v1/user/settings/privacy",
		"",
		authHeaders("settings_user_2"),
	)
	if getRec.Code != http.StatusOK {
		t.Fatalf("get privacy settings with null ringtone: expected 200, got %d: %s", getRec.Code, getRec.Body.String())
	}

	patchRec := doRequest(
		t,
		http.MethodPatch,
		"/v1/user/settings/privacy",
		`{"blockedKeywords":["after"]}`,
		authHeaders("settings_user_2"),
	)
	if patchRec.Code != http.StatusOK {
		t.Fatalf("patch privacy settings with null ringtone row: expected 200, got %d: %s", patchRec.Code, patchRec.Body.String())
	}

	var blocked []string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT blocked_keywords FROM user_settings WHERE user_id = $1`,
		"settings_user_2",
	).Scan(&blocked); err != nil {
		t.Fatalf("query blocked_keywords: %v", err)
	}
	if len(blocked) != 1 || blocked[0] != "after" {
		t.Fatalf("expected blocked_keywords updated to [after], got %#v", blocked)
	}
}
