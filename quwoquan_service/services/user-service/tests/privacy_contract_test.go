package tests

import (
	"context"
	"net/http"
	"reflect"
	"testing"
)

func TestPrivacySettings_BlockedKeywordsRoundTrip(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "privacy_user_1", "privacy1")

	patchResp := doRequest(
		t,
		http.MethodPatch,
		"/v1/user/settings/privacy",
		`{"blockedKeywords":[" api_contract_kw ","mute_me","api_contract_kw",""]}`,
		authHeaders("privacy_user_1"),
	)
	if patchResp.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", patchResp.Code, patchResp.Body.String())
	}

	var stored []string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT blocked_keywords FROM user_settings WHERE user_id = $1`,
		"privacy_user_1",
	).Scan(&stored); err != nil {
		t.Fatalf("query blocked keywords: %v", err)
	}
	want := []string{"api_contract_kw", "mute_me"}
	if !reflect.DeepEqual(stored, want) {
		t.Fatalf("expected stored blocked keywords %v, got %v", want, stored)
	}

	getResp := doRequest(
		t,
		http.MethodGet,
		"/v1/user/settings/privacy",
		"",
		authHeaders("privacy_user_1"),
	)
	if getResp.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", getResp.Code, getResp.Body.String())
	}
	body := parseJSON(t, getResp)
	items, ok := body["blockedKeywords"].([]any)
	if !ok {
		t.Fatalf("expected blockedKeywords array, got %T (%v)", body["blockedKeywords"], body["blockedKeywords"])
	}
	got := make([]string, 0, len(items))
	for _, item := range items {
		text, ok := item.(string)
		if !ok {
			t.Fatalf("expected blocked keyword string, got %T (%v)", item, item)
		}
		got = append(got, text)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expected response blocked keywords %v, got %v", want, got)
	}
}

func TestPrivacySettings_PatchLegacyNullDefaultIncomingCallRingtoneID(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "privacy_user_legacy", "privacylegacy")

	if _, err := pgPool.Exec(
		context.Background(),
		`INSERT INTO user_settings (user_id, enable_push, enable_marketing, quiet_hours_start, quiet_hours_end,
		    default_incoming_call_ringtone_id, allow_stranger_msg, profile_visibility,
		    content_language, feed_preference, assistant_enabled, updated_at)
		VALUES ($1, true, false, NULL, NULL, NULL, true, 'public', NULL, NULL, true, NOW())`,
		"privacy_user_legacy",
	); err != nil {
		t.Fatalf("seed legacy user settings: %v", err)
	}

	patchResp := doRequest(
		t,
		http.MethodPatch,
		"/v1/user/settings/privacy",
		`{"blockedKeywords":["legacy_kw"]}`,
		authHeaders("privacy_user_legacy"),
	)
	if patchResp.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", patchResp.Code, patchResp.Body.String())
	}

	var stored []string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT blocked_keywords FROM user_settings WHERE user_id = $1`,
		"privacy_user_legacy",
	).Scan(&stored); err != nil {
		t.Fatalf("query blocked keywords: %v", err)
	}
	want := []string{"legacy_kw"}
	if !reflect.DeepEqual(stored, want) {
		t.Fatalf("expected stored blocked keywords %v, got %v", want, stored)
	}
}
