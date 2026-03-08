// L2 契约测试：Post 业务对象 — 评论 CRUD、分页、点赞、排序、个人主页、App Config
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
	if comment["status"] != "visible" {
		t.Errorf("expected status=visible, got %v", comment["status"])
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

func TestCommentWithPersonaId(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Persona comment","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	commentBody := `{"content":"分身评论","personaId":"persona_abc"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(commentBody))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_persona_test")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &resp)
	comment, _ := resp["comment"].(map[string]any)
	if comment["personaId"] != "persona_abc" {
		t.Errorf("expected personaId=persona_abc, got %v", comment["personaId"])
	}
}

func TestCommentTooLong(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Long comment","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	longContent := strings.Repeat("超", 501)
	commentBody := `{"content":"` + longContent + `"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(commentBody))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code == http.StatusCreated {
		t.Fatal("expected rejection for comment exceeding 500 chars")
	}
}

func TestLikeComment(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Like comment","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	commentBody := `{"content":"点赞测试"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(commentBody))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var createResp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &createResp)
	comment, _ := createResp["comment"].(map[string]any)
	commentID, _ := comment["_id"].(string)

	likeReq := httptest.NewRequest(http.MethodPost, "/v1/content/comments/"+commentID+"/like", nil)
	likeReq.Header.Set("X-Client-User-Id", "user_liker")
	likeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(likeRec, likeReq)
	if likeRec.Code != http.StatusOK {
		t.Fatalf("like comment: expected 200, got %d: %s", likeRec.Code, likeRec.Body.String())
	}
	var likeResp map[string]any
	json.Unmarshal(likeRec.Body.Bytes(), &likeResp)
	if likeResp["liked"] != true {
		t.Error("expected liked=true")
	}
	likeCount, _ := likeResp["likeCount"].(float64)
	if likeCount != 1 {
		t.Errorf("expected likeCount=1, got %v", likeCount)
	}

	unlikeReq := httptest.NewRequest(http.MethodDelete, "/v1/content/comments/"+commentID+"/like", nil)
	unlikeReq.Header.Set("X-Client-User-Id", "user_liker")
	unlikeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(unlikeRec, unlikeReq)
	if unlikeRec.Code != http.StatusOK {
		t.Fatalf("unlike comment: expected 200, got %d", unlikeRec.Code)
	}
}

func TestCommentHotSort(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Hot sort","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	createComment := func(content string) string {
		body := `{"content":"` + content + `"}`
		req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		var resp map[string]any
		json.Unmarshal(rec.Body.Bytes(), &resp)
		c, _ := resp["comment"].(map[string]any)
		id, _ := c["_id"].(string)
		return id
	}

	createComment("普通评论")
	hotCommentID := createComment("热评")

	for i := 0; i < 3; i++ {
		likeReq := httptest.NewRequest(http.MethodPost, "/v1/content/comments/"+hotCommentID+"/like", nil)
		likeReq.Header.Set("X-Client-User-Id", "liker_"+strings.Repeat("x", i))
		likeRec := httptest.NewRecorder()
		testHandler.ServeHTTP(likeRec, likeReq)
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/comments?sort=hot&limit=10", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("list hot comments: expected 200, got %d", rec.Code)
	}
	var resp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &resp)
	items, _ := resp["items"].([]any)
	if len(items) < 2 {
		t.Fatalf("expected >=2 comments, got %d", len(items))
	}
	firstItem, _ := items[0].(map[string]any)
	if firstItem["_id"] != hotCommentID {
		t.Errorf("hot sort: expected hot comment first, got %v", firstItem["_id"])
	}
}

func TestGetAppConfig(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/v1/config/app", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("get app config: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	content, _ := resp["content"].(map[string]any)
	if content == nil {
		t.Fatal("missing 'content' in app config")
	}
	comment, _ := content["comment"].(map[string]any)
	if comment == nil {
		t.Fatal("missing 'content.comment' in app config")
	}
	maxLen, _ := comment["max_length"].(float64)
	if maxLen != 500 {
		t.Errorf("expected max_length=500, got %v", maxLen)
	}
}

func TestDeleteComment_ForbiddenForOtherUser(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Forbidden delete","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	body := `{"content":"someone else's comment"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_owner")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var createResp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &createResp)
	comment, _ := createResp["comment"].(map[string]any)
	commentID, _ := comment["_id"].(string)

	delReq := httptest.NewRequest(http.MethodDelete, "/v1/content/posts/"+postID+"/comments/"+commentID, nil)
	delReq.Header.Set("X-Client-User-Id", "user_other")
	delRec := httptest.NewRecorder()
	testHandler.ServeHTTP(delRec, delReq)
	if delRec.Code == http.StatusNoContent {
		t.Fatal("expected forbidden for other user deleting comment")
	}
}

func TestListCommentsByAuthor(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"My comments","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	body := `{"content":"我的评论"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_author_test")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	listReq := httptest.NewRequest(http.MethodGet, "/v1/content/users/me/comments?limit=20", nil)
	listReq.Header.Set("X-Client-User-Id", "user_author_test")
	listRec := httptest.NewRecorder()
	testHandler.ServeHTTP(listRec, listReq)
	if listRec.Code != http.StatusOK {
		t.Fatalf("list my comments: expected 200, got %d", listRec.Code)
	}
	var resp map[string]any
	json.Unmarshal(listRec.Body.Bytes(), &resp)
	items, _ := resp["items"].([]any)
	if len(items) != 1 {
		t.Errorf("expected 1 comment by author, got %d", len(items))
	}
}
