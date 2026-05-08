package tests

import (
	"net/http"
	"testing"
)

func TestBlock_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_1", "blocker1")
	createTestPersonaFull(t, "blocker_1_persona", "blocker_1", "ps_blocker_1", "blocker1", "default", true)

	rec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/sub-accounts/blocked_1/block",
		"",
		authHeadersForPersona("blocker_1", "ps_blocker_1"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	rec = doRequest(
		t,
		http.MethodGet,
		"/v1/user/sub-accounts/blocked_1/block/check",
		"",
		authHeadersForPersona("blocker_1", "ps_blocker_1"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	result := parseJSON(t, rec)
	if result["blocked"] != true {
		t.Errorf("expected blocked=true, got %v", result["blocked"])
	}
}

func TestBlock_Idempotent(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_2", "blocker2")
	createTestPersonaFull(t, "blocker_2_persona", "blocker_2", "ps_blocker_2", "blocker2", "default", true)

	doRequest(
		t,
		http.MethodPost,
		"/v1/user/sub-accounts/blocked_2/block",
		"",
		authHeadersForPersona("blocker_2", "ps_blocker_2"),
	)
	rec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/sub-accounts/blocked_2/block",
		"",
		authHeadersForPersona("blocker_2", "ps_blocker_2"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for idempotent block, got %d", rec.Code)
	}
}

func TestUnblock_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_3", "blocker3")
	createTestPersonaFull(t, "blocker_3_persona", "blocker_3", "ps_blocker_3", "blocker3", "default", true)

	doRequest(
		t,
		http.MethodPost,
		"/v1/user/sub-accounts/blocked_3/block",
		"",
		authHeadersForPersona("blocker_3", "ps_blocker_3"),
	)
	rec := doRequest(
		t,
		http.MethodDelete,
		"/v1/user/sub-accounts/blocked_3/block",
		"",
		authHeadersForPersona("blocker_3", "ps_blocker_3"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	rec = doRequest(
		t,
		http.MethodGet,
		"/v1/user/sub-accounts/blocked_3/block/check",
		"",
		authHeadersForPersona("blocker_3", "ps_blocker_3"),
	)
	result := parseJSON(t, rec)
	if result["blocked"] != false {
		t.Errorf("expected blocked=false after unblock, got %v", result["blocked"])
	}
}

func TestListBlocked(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_4", "blocker4")
	createTestPersonaFull(t, "blocker_4_persona", "blocker_4", "ps_blocker_4", "blocker4", "default", true)

	doRequest(
		t,
		http.MethodPost,
		"/v1/user/sub-accounts/victim_a/block",
		"",
		authHeadersForPersona("blocker_4", "ps_blocker_4"),
	)
	doRequest(
		t,
		http.MethodPost,
		"/v1/user/sub-accounts/victim_b/block",
		"",
		authHeadersForPersona("blocker_4", "ps_blocker_4"),
	)

	rec := doRequest(t, http.MethodGet, "/v1/user/blocked", "", authHeadersForPersona("blocker_4", "ps_blocker_4"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("missing items")
	}
	if len(items) != 2 {
		t.Errorf("expected 2 blocked items, got %d", len(items))
	}
}
