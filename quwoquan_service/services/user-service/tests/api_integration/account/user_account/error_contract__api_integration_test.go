package api_integration

import (
	"net/http"
	"testing"
)

func TestErrorCode_MissingAuthenticatedAccountIsDeleted(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	headers := authHeaders("nonexistent_user")
	headers["X-Request-Id"] = "user-req-1"
	headers["X-Trace-Id"] = "user-trace-1"
	rec := doRequest(t, http.MethodGet, "/user/profile/nonexistent_user", "", headers)
	if rec.Code != http.StatusGone {
		t.Fatalf("expected 410, got %d", rec.Code)
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.AUTH.account_deleted" {
		t.Errorf("expected code=USER.AUTH.account_deleted, got %v", result["code"])
	}
	if result["userMessage"] != "账号已注销或进入删除流程，请更换手机号登录" {
		t.Errorf("unexpected account-deleted userMessage: %v", result["userMessage"])
	}
	if result["requestId"] != "user-req-1" || result["traceId"] != "user-trace-1" {
		t.Errorf("expected request/trace propagation, got request=%v trace=%v", result["requestId"], result["traceId"])
	}
	if rec.Header().Get("X-Request-Id") != "user-req-1" || rec.Header().Get("X-Trace-Id") != "user-trace-1" {
		t.Errorf("expected request/trace response headers, got request=%q trace=%q", rec.Header().Get("X-Request-Id"), rec.Header().Get("X-Trace-Id"))
	}
}

func TestErrorCode_InvalidArgument(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "error-owner", "error-owner")
	createTestPersonaFull(
		t,
		"error-persona-record",
		"error-owner",
		"error-persona",
		"错误契约分身",
		"open",
		true,
	)
	headers := authHeadersForPersona("error-owner", "error-persona")
	headers["X-Request-Id"] = "user-req-invalid-1"
	headers["X-Trace-Id"] = "user-trace-invalid-1"
	rec := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/error-persona/block",
		"",
		headers,
	)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.RELATIONSHIP.invalid_pair" {
		t.Errorf("expected code=USER.RELATIONSHIP.invalid_pair, got %v", result["code"])
	}
	if rec.Header().Get("X-Request-Id") != "user-req-invalid-1" || rec.Header().Get("X-Trace-Id") != "user-trace-invalid-1" {
		t.Errorf(
			"expected request/trace response headers, got request=%q trace=%q",
			rec.Header().Get("X-Request-Id"),
			rec.Header().Get("X-Trace-Id"),
		)
	}
}

func TestErrorCode_PrimaryGuard_RetirePrimary(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "err_user_1", "err_user1")
	createTestPersona(t, "err_pa_primary", "err_user_1", "Primary", true, true)

	createTestPersonaFull(t, "err_pa_other", "err_user_1", "err_pa_other_sa", "Other", "open", false, false)
	rec := doRequest(t, http.MethodPost, "/user/personas/err_pa_primary_sa/retire", "", authHeaders("err_user_1"))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.SUB_ACCOUNT.primary_guard" {
		t.Errorf("expected code=USER.SUB_ACCOUNT.primary_guard, got %v", result["code"])
	}
}

func TestHealthz(t *testing.T) {
	rec := doRequest(t, http.MethodGet, "/healthz", "", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
}
