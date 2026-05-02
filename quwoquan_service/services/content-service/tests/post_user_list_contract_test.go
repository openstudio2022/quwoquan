// L2 契约测试：Post 业务对象 — 用户创作列表
package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestListUserPosts(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	authorID := "author_list_test"
	for i := 0; i < 3; i++ {
		createPostWithAuthor(t, authorID, `{"contentType":"image","title":"user post","mediaUrls":["https://example.com/img.jpg"]}`)
	}
	createPostWithAuthor(t, "other_author", `{"contentType":"image","title":"other post","mediaUrls":["https://example.com/img.jpg"]}`)

	req := httptest.NewRequest(http.MethodGet, "/v1/content/profile-subjects/"+authorID+"/posts?limit=20", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	items, _ := resp["items"].([]any)
	if len(items) != 3 {
		t.Errorf("expected 3 user posts, got %d", len(items))
	}
}

func TestListUserPostsEmpty(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	req := httptest.NewRequest(http.MethodGet, "/v1/content/profile-subjects/nonexistent_user/posts?limit=20", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &resp)
	items, _ := resp["items"].([]any)
	if len(items) != 0 {
		t.Errorf("expected 0 posts for nonexistent user, got %d", len(items))
	}
}
