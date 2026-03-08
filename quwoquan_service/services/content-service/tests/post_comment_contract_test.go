// L2 契约测试：Post 业务对象 — 评论 CRUD 与分页
package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCommentWithNotification(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	eventSpy.Reset()

	created := createPost(t, `{"contentType":"image","title":"Comment notification test","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	commentBody := `{"content":"这张图真漂亮！"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(commentBody))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_commenter_001")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	comment, _ := resp["comment"].(map[string]any)
	if comment == nil {
		t.Fatal("response missing comment object")
	}
	if comment["content"] != "这张图真漂亮！" {
		t.Errorf("comment content mismatch: %v", comment["content"])
	}
}

func TestCommentListPagination(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Comment pagination test","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	for i := 0; i < 3; i++ {
		body := `{"content":"comment ` + strings.Repeat("x", i) + `"}`
		req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusCreated {
			t.Fatalf("create comment %d failed: %d", i, rec.Code)
		}
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/comments?limit=5", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("list comments: expected 200, got %d", rec.Code)
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	items, _ := resp["items"].([]any)
	if len(items) != 3 {
		t.Errorf("expected 3 comments, got %d", len(items))
	}
}

func TestDeleteComment(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Delete comment test","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	body := `{"content":"to be deleted"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_deleter")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create comment failed: %d", rec.Code)
	}
	var createResp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &createResp)
	comment, _ := createResp["comment"].(map[string]any)
	commentID, _ := comment["_id"].(string)

	delReq := httptest.NewRequest(http.MethodDelete, "/v1/content/posts/"+postID+"/comments/"+commentID, nil)
	delReq.Header.Set("X-Client-User-Id", "user_deleter")
	delRec := httptest.NewRecorder()
	testHandler.ServeHTTP(delRec, delReq)
	if delRec.Code != http.StatusNoContent {
		t.Fatalf("delete comment: expected 204, got %d: %s", delRec.Code, delRec.Body.String())
	}

	listReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/comments?limit=20", nil)
	listRec := httptest.NewRecorder()
	testHandler.ServeHTTP(listRec, listReq)
	var listResp map[string]any
	json.Unmarshal(listRec.Body.Bytes(), &listResp)
	items, _ := listResp["items"].([]any)
	if len(items) != 0 {
		t.Errorf("expected 0 comments after delete, got %d", len(items))
	}
}

func TestGetCounters(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Counters test","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/counters", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("get counters: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if _, ok := resp["like"]; !ok {
		t.Error("missing 'like' counter")
	}
	if _, ok := resp["comment"]; !ok {
		t.Error("missing 'comment' counter")
	}
}
