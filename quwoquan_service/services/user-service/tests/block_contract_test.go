package tests

import (
	"net/http"
	"testing"
)

func TestBlock_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_1", "blocker1")

	rec := doRequest(t, http.MethodPost, "/v1/user/block/blocked_1", "", authHeaders("blocker_1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	rec = doRequest(t, http.MethodGet, "/v1/user/block/check/blocked_1", "", authHeaders("blocker_1"))
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

	doRequest(t, http.MethodPost, "/v1/user/block/blocked_2", "", authHeaders("blocker_2"))
	rec := doRequest(t, http.MethodPost, "/v1/user/block/blocked_2", "", authHeaders("blocker_2"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for idempotent block, got %d", rec.Code)
	}
}

func TestUnblock_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_3", "blocker3")

	doRequest(t, http.MethodPost, "/v1/user/block/blocked_3", "", authHeaders("blocker_3"))
	rec := doRequest(t, http.MethodDelete, "/v1/user/block/blocked_3", "", authHeaders("blocker_3"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	rec = doRequest(t, http.MethodGet, "/v1/user/block/check/blocked_3", "", authHeaders("blocker_3"))
	result := parseJSON(t, rec)
	if result["blocked"] != false {
		t.Errorf("expected blocked=false after unblock, got %v", result["blocked"])
	}
}

func TestListBlocked(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "blocker_4", "blocker4")

	doRequest(t, http.MethodPost, "/v1/user/block/victim_a", "", authHeaders("blocker_4"))
	doRequest(t, http.MethodPost, "/v1/user/block/victim_b", "", authHeaders("blocker_4"))

	rec := doRequest(t, http.MethodGet, "/v1/user/blocked", "", authHeaders("blocker_4"))
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
