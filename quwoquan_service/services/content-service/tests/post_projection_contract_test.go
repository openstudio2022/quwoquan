// L2 契约测试：Post 业务对象 — 投影一致性与辅助阅读
package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGetHelperRead_Article(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{
		"contentType":"article",
		"title":"深度解析 Go 并发模型",
		"body":"Go 语言的并发模型基于 goroutine 和 channel，它提供了轻量级的并发原语..."
	}`)
	postID, _ := created["_id"].(string)

	req := httptest.NewRequest(http.MethodGet, "/v1/content/helper-read/"+postID, nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &resp)
	if resp["postId"] != postID {
		t.Errorf("postId mismatch: %v", resp["postId"])
	}
	summary, _ := resp["summary"].(string)
	if summary == "" {
		t.Error("summary should not be empty")
	}
}

func TestGetHelperRead_NonArticle_Returns404(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"photo","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	req := httptest.NewRequest(http.MethodGet, "/v1/content/helper-read/"+postID, nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code == http.StatusOK {
		t.Fatalf("helper-read for non-article should not return 200")
	}
}

func TestCreatePostResponseShape_NoPrivateFields(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"micro","body":"hello world"}`)
	postID, _ := created["_id"].(string)

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	var resp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &resp)
	if _, found := resp["embedding"]; found {
		t.Error("embedding field must not be exposed to client")
	}
	if _, found := resp["moderationStatus"]; found {
		t.Error("moderationStatus field must not be exposed to client")
	}
}
