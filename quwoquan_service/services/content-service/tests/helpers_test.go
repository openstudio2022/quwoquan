package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// createPost is a shared test helper: create draft then publish it, returning
// the published response body. Most feed/profile/comment contracts need a
// published post instead of a raw draft.
func createPost(t *testing.T, payload string) map[string]any {
	t.Helper()
	return createPostWithAuthor(t, "", payload)
}

// createPostWithAuthor creates a draft as the given author and immediately
// publishes it. Use distinct authors when tests need multiple items to pass
// recommendation rerank (maxAuthorPerFeed limits items per author).
func createPostWithAuthor(t *testing.T, authorID string, payload string) map[string]any {
	t.Helper()
	created := createDraftPostWithAuthor(t, authorID, payload)
	postID, _ := created["_id"].(string)
	if postID == "" {
		postID, _ = created["id"].(string)
	}
	if postID == "" {
		t.Fatalf("createPostWithAuthor: missing post id in draft response: %+v", created)
	}
	published := publishPostWithAuthor(t, authorID, postID, `{}`)
	for key, value := range created {
		if _, exists := published[key]; !exists {
			published[key] = value
		}
	}
	return published
}

// createDraftPost creates a raw draft and returns the parsed response body.
func createDraftPost(t *testing.T, payload string) map[string]any {
	t.Helper()
	return createDraftPostWithAuthor(t, "", payload)
}

// createDraftPostWithAuthor creates a draft as the given author
// (sets X-Client-User-Id and X-Client-Sub-Account-Id) and returns the draft payload.
func createDraftPostWithAuthor(t *testing.T, authorID string, payload string) map[string]any {
	t.Helper()
	payload = normalizeCreatePostPayloadForTest(t, payload)
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	if authorID != "" {
		req.Header.Set("X-Client-User-Id", authorID)
		req.Header.Set("X-Client-Sub-Account-Id", authorID)
	}
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

func normalizeCreatePostPayloadForTest(t *testing.T, payload string) string {
	t.Helper()
	var body map[string]any
	if err := json.Unmarshal([]byte(payload), &body); err != nil {
		t.Fatalf("normalize create post payload: %v", err)
	}
	if strings.TrimSpace(asTestString(body["contentType"])) == "article" && body["articleDocument"] == nil {
		body["articleDocument"] = map[string]any{
			"title": asTestString(body["title"]),
			"body":  asTestString(body["body"]),
		}
	}
	normalized, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal normalized create post payload: %v", err)
	}
	return string(normalized)
}

func asTestString(value any) string {
	if s, ok := value.(string); ok {
		return s
	}
	return ""
}

func publishPostWithAuthor(
	t *testing.T,
	authorID string,
	postID string,
	payload string,
) map[string]any {
	t.Helper()
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+"/publish",
		strings.NewReader(payload),
	)
	req.Header.Set("Content-Type", "application/json")
	if authorID != "" {
		req.Header.Set("X-Client-User-Id", authorID)
		req.Header.Set("X-Client-Sub-Account-Id", authorID)
	}
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("publishPostWithAuthor: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("publishPostWithAuthor: decode response: %v", err)
	}
	return result
}
