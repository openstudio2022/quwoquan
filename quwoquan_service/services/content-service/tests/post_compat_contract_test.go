// L2 契约测试：Post 业务对象 — 向后兼容性
//
// 守护：响应字段不缩减；私有字段不泄露；可写字段约束稳定。
package tests

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestPost_ResponseShape_NoPrivateFields verifies that GET /v1/content/posts/:id
// does not expose internal fields (embedding, moderationStatus).
// Fields classified privacy:never_expose must never appear in public responses.
func TestPost_ResponseShape_NoPrivateFields(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Privacy check","body":"public content","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("created post has no _id")
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if _, hasEmbedding := result["embedding"]; hasEmbedding {
		t.Error("response must not expose embedding field (privacy: never_expose)")
	}
	if _, hasMod := result["moderationStatus"]; hasMod {
		t.Error("response must not expose moderationStatus (visibility: platform-ops only)")
	}
}

// TestPost_WritableFields_UnknownFieldRejected verifies that POST /v1/content/posts
// rejects requests with unknown fields, returning 400 with structured error.
// This protects against field injection attacks and enforces the field contract.
func TestPost_WritableFields_UnknownFieldRejected(t *testing.T) {
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts",
		bytes.NewBufferString(`{"unknownField":"x","contentType":"image","mediaUrls":["https://example.com/img.jpg"]}`),
	)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
	var errResp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	if errResp["code"] == nil {
		t.Error("error response missing code field")
	}
}

// TestPost_NewFieldBackfill_OldRecordsStillReadable creates a post with minimal fields
// and verifies it can still be retrieved. This simulates backward compatibility when
// new required fields are added to the schema — older records should not break.
func TestPost_NewFieldBackfill_OldRecordsStillReadable(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"micro","body":"minimal post"}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("old minimal record should still be readable, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if result["_id"] != postID {
		t.Errorf("expected _id=%s, got %v", postID, result["_id"])
	}
}
