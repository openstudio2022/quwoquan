package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// createPost is a shared test helper: POST /v1/content/posts and return the parsed response body.
func createPost(t *testing.T, payload string) map[string]any {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("createPost helper: expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("createPost helper: decode response: %v", err)
	}
	return result
}
