package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func testDerivedMediaFileServer(localRoot string) http.Handler {
	root := filepath.Clean(strings.TrimSpace(localRoot))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		rel := strings.TrimPrefix(r.URL.Path, "/media/")
		rel = strings.Trim(rel, "/")
		if rel == "" || strings.Contains(rel, "..") {
			http.Error(w, "bad path", http.StatusBadRequest)
			return
		}
		full := filepath.Join(root, filepath.FromSlash(rel))
		cleanRoot := root
		cleanFull := filepath.Clean(full)
		sep := string(filepath.Separator)
		if cleanFull != cleanRoot && !strings.HasPrefix(cleanFull, cleanRoot+sep) {
			http.Error(w, "bad path", http.StatusBadRequest)
			return
		}
		fi, err := os.Stat(cleanFull)
		if err != nil || fi.IsDir() {
			http.NotFound(w, r)
			return
		}
		http.ServeFile(w, r, cleanFull)
	})
}

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

func doPut(t *testing.T, path, payload, userId string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPut, path, strings.NewReader(payload))
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
