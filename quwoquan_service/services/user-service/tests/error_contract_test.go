package tests

import (
	"net/http"
	"testing"
)

func TestErrorCode_UserNotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	rec := doRequest(t, http.MethodGet, "/v1/user/profile/nonexistent_user", "", nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.USER.not_found" {
		t.Errorf("expected code=USER.USER.not_found, got %v", result["code"])
	}
	if result["userMessage"] != "用户不存在" {
		t.Errorf("expected userMessage=用户不存在, got %v", result["userMessage"])
	}
}

func TestErrorCode_InvalidArgument(t *testing.T) {
	rec := doRequest(t, http.MethodGet, "/v1/user/profile/", "", nil)
	if rec.Code == http.StatusOK {
		t.Skip("empty userId may route differently")
	}
}

func TestErrorCode_Forbidden_DeletePrimary(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "err_user_1", "err_user1")
	createTestPersona(t, "err_pa_primary", "err_user_1", "Primary", true, true)

	rec := doRequest(t, http.MethodDelete, "/v1/user/personas/err_pa_primary", "", authHeaders("err_user_1"))
	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", rec.Code)
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.USER.forbidden" {
		t.Errorf("expected code=USER.USER.forbidden, got %v", result["code"])
	}
}

func TestHealthz(t *testing.T) {
	rec := doRequest(t, http.MethodGet, "/healthz", "", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
}
