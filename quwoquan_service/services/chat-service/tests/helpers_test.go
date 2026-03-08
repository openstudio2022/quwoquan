package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func createConversation(t *testing.T, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/v1/chat/conversations", payload, "user_test_001", http.StatusCreated)
}

func createConversationAs(t *testing.T, userId, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/v1/chat/conversations", payload, userId, http.StatusCreated)
}

func sendMessage(t *testing.T, conversationId, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/v1/chat/conversations/"+conversationId+"/messages", payload, "user_test_001", http.StatusCreated)
}

func sendMessageAs(t *testing.T, userId, conversationId, payload string) map[string]any {
	t.Helper()
	return doPost(t, "/v1/chat/conversations/"+conversationId+"/messages", payload, userId, http.StatusCreated)
}

func doPost(t *testing.T, path, payload, userId string, expectedStatus int) map[string]any {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", userId)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != expectedStatus {
		t.Fatalf("doPost %s: expected %d, got %d: %s", path, expectedStatus, rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("doPost %s: decode response: %v", path, err)
	}
	return result
}

func doGet(t *testing.T, path, userId string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("X-Client-User-Id", userId)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

func doPatch(t *testing.T, path, payload, userId string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPatch, path, strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", userId)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

func doDelete(t *testing.T, path, userId string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodDelete, path, nil)
	req.Header.Set("X-Client-User-Id", userId)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}
