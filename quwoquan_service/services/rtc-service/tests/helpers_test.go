package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func authHeaders(userID string) map[string]string {
	return map[string]string{
		"Content-Type":     "application/json",
		"X-Client-User-Id": userID,
	}
}

func doPost(t *testing.T, path, payload, userID string, expectedStatus int) map[string]any {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(payload))
	for k, v := range authHeaders(userID) {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != expectedStatus {
		t.Fatalf("doPost %s: expected %d, got %d: %s", path, expectedStatus, rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("doPost %s: decode response: %v\nbody: %s", path, err, rec.Body.String())
	}
	return result
}

func doPostAny(t *testing.T, path, payload, userID string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(payload))
	for k, v := range authHeaders(userID) {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

func doGet(t *testing.T, path, userID string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("X-Client-User-Id", userID)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

func createTestCall(t *testing.T, userID string) map[string]any {
	t.Helper()
	payload := `{"callType":"audio","inviteeIds":["user_invitee_001"]}`
	return doPost(t, "/v1/rtc/calls", payload, userID, http.StatusCreated)
}

func extractSessionID(t *testing.T, resp map[string]any) string {
	t.Helper()
	session, ok := resp["session"].(map[string]any)
	if !ok {
		t.Fatal("response missing session object")
	}
	id, ok := session["_id"].(string)
	if !ok {
		t.Fatal("session missing _id")
	}
	return id
}

func extractSession(t *testing.T, resp map[string]any) map[string]any {
	t.Helper()
	session, ok := resp["session"].(map[string]any)
	if !ok {
		t.Fatal("response missing session object")
	}
	return session
}
