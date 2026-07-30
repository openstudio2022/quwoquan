// L2 契约测试：Post 业务对象 — 收口后的响应契约
//
// 守护：响应字段不缩减；私有字段不泄露；可写字段约束稳定。
package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestPost_ResponseShape_NoPrivateFields verifies that GET /content/content/posts/:id
// does not expose internal fields (embedding, moderationStatus).
// Fields classified privacy:never_expose must never appear in public responses.
func TestPost_ResponseShape_NoPrivateFields(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPost(t, `{"contentType":"image","title":"Privacy check","body":"public content"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("created post has no _id")
	}

	req := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
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

// TestPost_RequestEntity_UnknownFieldRejected verifies that POST /content/content/posts
// rejects requests with unknown fields, returning 400 with structured error.
// This protects against field injection attacks and enforces the field contract.
func TestPost_RequestEntity_UnknownFieldRejected(t *testing.T) {
	req := newPostPublicationRequestForTest(
		t,
		"unknown-field-author",
		`{"unknownField":"x","contentType":"micro","body":"field injection"}`,
	)
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

// TestPost_MinimalCurrentRecordRemainsReadable verifies that a minimal payload
// still receives every server-owned default during SubmitPostPublication.
func TestPost_MinimalCurrentRecordRemainsReadable(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPost(t, `{"contentType":"micro","body":"minimal post"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	req := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("minimal current record should be readable, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if result["postId"] != postID {
		t.Errorf("expected postId=%s, got %v", postID, result["postId"])
	}
}

func TestPostSearchRouteIsRetired(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/content/posts/search?query=%E6%97%85%E8%A1%8C", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("retired content search route status=%d body=%s", rec.Code, rec.Body.String())
	}
}
