// L2 契约测试：Post 业务对象 — 评论 CRUD、分页、三态反应、排序、个人主页、App Config
package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/content-service/internal/application"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
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

func TestCommentCountersStayConsistentAcrossReadModels(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(
		t,
		`{"contentType":"image","title":"Comment counters consistency","mediaUrls":["https://example.com/img.jpg"]}`,
	)
	postID, _ := created["_id"].(string)

	createReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+"/comments",
		strings.NewReader(`{"content":"一致性评论"}`),
	)
	createReq.Header.Set("Content-Type", "application/json")
	createReq.Header.Set("X-Client-User-Id", "comment_consistency_user")
	createRec := httptest.NewRecorder()
	testHandler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("create comment: expected 201, got %d: %s", createRec.Code, createRec.Body.String())
	}
	var createResp map[string]any
	if err := json.Unmarshal(createRec.Body.Bytes(), &createResp); err != nil {
		t.Fatalf("decode create comment: %v", err)
	}
	commentCount, _ := createResp["commentCount"].(float64)
	if commentCount != 1 {
		t.Fatalf("expected create response commentCount=1, got %v", createResp["commentCount"])
	}
	comment, _ := createResp["comment"].(map[string]any)
	commentID, _ := comment["_id"].(string)

	counterReq := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/posts/"+postID+"/counters",
		nil,
	)
	counterRec := httptest.NewRecorder()
	testHandler.ServeHTTP(counterRec, counterReq)
	if counterRec.Code != http.StatusOK {
		t.Fatalf("get counters: expected 200, got %d", counterRec.Code)
	}
	var counterResp map[string]any
	if err := json.Unmarshal(counterRec.Body.Bytes(), &counterResp); err != nil {
		t.Fatalf("decode counters: %v", err)
	}
	if counterResp["comment"] != float64(1) {
		t.Fatalf("expected counters.comment=1, got %v", counterResp["comment"])
	}

	postReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	postRec := httptest.NewRecorder()
	testHandler.ServeHTTP(postRec, postReq)
	if postRec.Code != http.StatusOK {
		t.Fatalf("get post: expected 200, got %d", postRec.Code)
	}
	var postResp map[string]any
	if err := json.Unmarshal(postRec.Body.Bytes(), &postResp); err != nil {
		t.Fatalf("decode post: %v", err)
	}
	if postResp["commentCount"] != float64(1) {
		t.Fatalf("expected post.commentCount=1, got %v", postResp["commentCount"])
	}

	deleteReq := httptest.NewRequest(
		http.MethodDelete,
		"/v1/content/posts/"+postID+"/comments/"+commentID,
		nil,
	)
	deleteReq.Header.Set("X-Client-User-Id", "comment_consistency_user")
	deleteRec := httptest.NewRecorder()
	testHandler.ServeHTTP(deleteRec, deleteReq)
	if deleteRec.Code != http.StatusNoContent {
		t.Fatalf("delete comment: expected 204, got %d", deleteRec.Code)
	}

	counterRec = httptest.NewRecorder()
	testHandler.ServeHTTP(counterRec, counterReq)
	if counterRec.Code != http.StatusOK {
		t.Fatalf("get counters after delete: expected 200, got %d", counterRec.Code)
	}
	counterResp = map[string]any{}
	if err := json.Unmarshal(counterRec.Body.Bytes(), &counterResp); err != nil {
		t.Fatalf("decode counters after delete: %v", err)
	}
	if counterResp["comment"] != float64(0) {
		t.Fatalf("expected counters.comment=0 after delete, got %v", counterResp["comment"])
	}
}

func TestShareCountersStayAuthoritativeAndIdempotent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(
		t,
		`{"contentType":"image","title":"Share counters consistency","mediaUrls":["https://example.com/img.jpg"]}`,
	)
	postID, _ := created["_id"].(string)

	shareReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+"/share",
		strings.NewReader(`{}`),
	)
	shareReq.Header.Set("Content-Type", "application/json")
	shareReq.Header.Set("X-Client-User-Id", "share_counter_user")
	shareRec := httptest.NewRecorder()
	testHandler.ServeHTTP(shareRec, shareReq)
	if shareRec.Code != http.StatusOK {
		t.Fatalf("share post: expected 200, got %d: %s", shareRec.Code, shareRec.Body.String())
	}
	var shareResp map[string]any
	if err := json.Unmarshal(shareRec.Body.Bytes(), &shareResp); err != nil {
		t.Fatalf("decode share response: %v", err)
	}
	if shareResp["changed"] != true {
		t.Fatalf("expected first share changed=true, got %v", shareResp["changed"])
	}
	if shareResp["shareCount"] != float64(1) {
		t.Fatalf("expected first shareCount=1, got %v", shareResp["shareCount"])
	}

	shareRec = httptest.NewRecorder()
	testHandler.ServeHTTP(shareRec, shareReq)
	if shareRec.Code != http.StatusOK {
		t.Fatalf("repeat share post: expected 200, got %d: %s", shareRec.Code, shareRec.Body.String())
	}
	shareResp = map[string]any{}
	if err := json.Unmarshal(shareRec.Body.Bytes(), &shareResp); err != nil {
		t.Fatalf("decode repeat share response: %v", err)
	}
	if shareResp["changed"] != false {
		t.Fatalf("expected repeated share changed=false, got %v", shareResp["changed"])
	}
	if shareResp["shareCount"] != float64(1) {
		t.Fatalf("expected repeated shareCount to remain 1, got %v", shareResp["shareCount"])
	}

	reactionReq := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/posts/"+postID+"/reactions",
		nil,
	)
	reactionReq.Header.Set("X-Client-User-Id", "share_counter_user")
	reactionRec := httptest.NewRecorder()
	testHandler.ServeHTTP(reactionRec, reactionReq)
	if reactionRec.Code != http.StatusOK {
		t.Fatalf("get reaction state: expected 200, got %d", reactionRec.Code)
	}
	var reactionResp map[string]any
	if err := json.Unmarshal(reactionRec.Body.Bytes(), &reactionResp); err != nil {
		t.Fatalf("decode reaction state: %v", err)
	}
	if reactionResp["shared"] != true {
		t.Fatalf("expected reaction.shared=true, got %v", reactionResp["shared"])
	}

	counterReq := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/posts/"+postID+"/counters",
		nil,
	)
	counterRec := httptest.NewRecorder()
	testHandler.ServeHTTP(counterRec, counterReq)
	if counterRec.Code != http.StatusOK {
		t.Fatalf("get counters: expected 200, got %d", counterRec.Code)
	}
	var counterResp map[string]any
	if err := json.Unmarshal(counterRec.Body.Bytes(), &counterResp); err != nil {
		t.Fatalf("decode counters: %v", err)
	}
	if counterResp["share"] != float64(1) {
		t.Fatalf("expected counters.share=1, got %v", counterResp["share"])
	}

	postReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	postRec := httptest.NewRecorder()
	testHandler.ServeHTTP(postRec, postReq)
	if postRec.Code != http.StatusOK {
		t.Fatalf("get post: expected 200, got %d", postRec.Code)
	}
	var postResp map[string]any
	if err := json.Unmarshal(postRec.Body.Bytes(), &postResp); err != nil {
		t.Fatalf("decode post: %v", err)
	}
	if postResp["shareCount"] != float64(1) {
		t.Fatalf("expected post.shareCount=1, got %v", postResp["shareCount"])
	}

	unshareReq := httptest.NewRequest(
		http.MethodDelete,
		"/v1/content/posts/"+postID+"/share",
		nil,
	)
	unshareReq.Header.Set("X-Client-User-Id", "share_counter_user")
	unshareRec := httptest.NewRecorder()
	testHandler.ServeHTTP(unshareRec, unshareReq)
	if unshareRec.Code != http.StatusOK {
		t.Fatalf("unshare post: expected 200, got %d: %s", unshareRec.Code, unshareRec.Body.String())
	}
	var unshareResp map[string]any
	if err := json.Unmarshal(unshareRec.Body.Bytes(), &unshareResp); err != nil {
		t.Fatalf("decode unshare response: %v", err)
	}
	if unshareResp["changed"] != true {
		t.Fatalf("expected unshare changed=true, got %v", unshareResp["changed"])
	}
	if unshareResp["shareCount"] != float64(0) {
		t.Fatalf("expected unshare shareCount=0, got %v", unshareResp["shareCount"])
	}

	reactionRec = httptest.NewRecorder()
	testHandler.ServeHTTP(reactionRec, reactionReq)
	if reactionRec.Code != http.StatusOK {
		t.Fatalf("get reaction state after unshare: expected 200, got %d", reactionRec.Code)
	}
	reactionResp = map[string]any{}
	if err := json.Unmarshal(reactionRec.Body.Bytes(), &reactionResp); err != nil {
		t.Fatalf("decode reaction state after unshare: %v", err)
	}
	if reactionResp["shared"] != false {
		t.Fatalf("expected reaction.shared=false after unshare, got %v", reactionResp["shared"])
	}
}

func TestCommentUsesSubAccountHeader(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Persona comment","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	commentBody := `{"content":"分身评论"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(commentBody))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_persona_test")
	req.Header.Set("X-Client-Sub-Account-Id", "sub_commenter_abc")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &resp)
	comment, _ := resp["comment"].(map[string]any)
	if comment["authorId"] != "sub_commenter_abc" {
		t.Errorf("expected authorId=sub_commenter_abc, got %v", comment["authorId"])
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

func TestReactToCommentThreeStateContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"React comment","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	commentBody := `{"content":"三态反应测试"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(commentBody))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var createResp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &createResp)
	comment, _ := createResp["comment"].(map[string]any)
	commentID, _ := comment["_id"].(string)

	likeReq := httptest.NewRequest(http.MethodPost, "/v1/content/comments/"+commentID+"/reaction", strings.NewReader(`{"reaction":"like"}`))
	likeReq.Header.Set("Content-Type", "application/json")
	likeReq.Header.Set("X-Client-User-Id", "user_liker")
	likeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(likeRec, likeReq)
	if likeRec.Code != http.StatusOK {
		t.Fatalf("react like: expected 200, got %d: %s", likeRec.Code, likeRec.Body.String())
	}
	var likeResp map[string]any
	json.Unmarshal(likeRec.Body.Bytes(), &likeResp)
	likedComment, _ := likeResp["comment"].(map[string]any)
	if likedComment["viewerReaction"] != "like" {
		t.Errorf("expected viewerReaction=like, got %v", likedComment["viewerReaction"])
	}
	likeCount, _ := likedComment["likeCount"].(float64)
	if likeCount != 1 {
		t.Errorf("expected likeCount=1, got %v", likeCount)
	}

	dislikeReq := httptest.NewRequest(http.MethodPost, "/v1/content/comments/"+commentID+"/reaction", strings.NewReader(`{"reaction":"dislike"}`))
	dislikeReq.Header.Set("Content-Type", "application/json")
	dislikeReq.Header.Set("X-Client-User-Id", "user_liker")
	dislikeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(dislikeRec, dislikeReq)
	if dislikeRec.Code != http.StatusOK {
		t.Fatalf("react dislike: expected 200, got %d: %s", dislikeRec.Code, dislikeRec.Body.String())
	}
	var dislikeResp map[string]any
	json.Unmarshal(dislikeRec.Body.Bytes(), &dislikeResp)
	dislikedComment, _ := dislikeResp["comment"].(map[string]any)
	if dislikedComment["viewerReaction"] != "dislike" {
		t.Errorf("expected viewerReaction=dislike, got %v", dislikedComment["viewerReaction"])
	}
	if dislikedComment["likeCount"].(float64) != 0 || dislikedComment["dislikeCount"].(float64) != 1 {
		t.Errorf("expected like/dislike counts 0/1, got %v/%v", dislikedComment["likeCount"], dislikedComment["dislikeCount"])
	}

	noneReq := httptest.NewRequest(http.MethodPost, "/v1/content/comments/"+commentID+"/reaction", strings.NewReader(`{"reaction":"none"}`))
	noneReq.Header.Set("Content-Type", "application/json")
	noneReq.Header.Set("X-Client-User-Id", "user_liker")
	noneRec := httptest.NewRecorder()
	testHandler.ServeHTTP(noneRec, noneReq)
	if noneRec.Code != http.StatusOK {
		t.Fatalf("react none: expected 200, got %d: %s", noneRec.Code, noneRec.Body.String())
	}
	var noneResp map[string]any
	json.Unmarshal(noneRec.Body.Bytes(), &noneResp)
	noneComment, _ := noneResp["comment"].(map[string]any)
	if noneComment["viewerReaction"] != "none" {
		t.Errorf("expected viewerReaction=none, got %v", noneComment["viewerReaction"])
	}
}

func TestReactToCommentContract(t *testing.T) {
	TestReactToCommentThreeStateContract(t)
}

func TestCommentMostLikedSort(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Most liked sort","mediaUrls":["https://example.com/img.jpg"]}`)
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
	mostLikedCommentID := createComment("高赞评论")

	for i := 0; i < 3; i++ {
		likeReq := httptest.NewRequest(http.MethodPost, "/v1/content/comments/"+mostLikedCommentID+"/reaction", strings.NewReader(`{"reaction":"like"}`))
		likeReq.Header.Set("Content-Type", "application/json")
		likeReq.Header.Set("X-Client-User-Id", "liker_"+strings.Repeat("x", i))
		likeRec := httptest.NewRecorder()
		testHandler.ServeHTTP(likeRec, likeReq)
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/comments?sort=most_liked&limit=10", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("list most_liked comments: expected 200, got %d", rec.Code)
	}
	var resp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &resp)
	items, _ := resp["items"].([]any)
	if len(items) < 2 {
		t.Fatalf("expected >=2 comments, got %d", len(items))
	}
	firstItem, _ := items[0].(map[string]any)
	if firstItem["_id"] != mostLikedCommentID {
		t.Errorf("most_liked sort: expected most liked comment first, got %v", firstItem["_id"])
	}
}

func TestCommentListRecommendedLatestMostLiked(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Comment sort matrix","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("missing post id for comment sort matrix test")
	}

	createComment := func(authorID, content string) string {
		t.Helper()
		req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(`{"content":"`+content+`"}`))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Client-User-Id", authorID)
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusCreated {
			t.Fatalf("create comment %s: expected 201, got %d: %s", content, rec.Code, rec.Body.String())
		}
		var resp map[string]any
		if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
			t.Fatalf("decode create comment response: %v", err)
		}
		comment, _ := resp["comment"].(map[string]any)
		commentID, _ := comment["_id"].(string)
		if commentID == "" {
			t.Fatalf("missing comment id for %s", content)
		}
		return commentID
	}

	likeComment := func(commentID, userID string) {
		t.Helper()
		req := httptest.NewRequest(http.MethodPost, "/v1/content/comments/"+commentID+"/reaction", strings.NewReader(`{"reaction":"like"}`))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Client-User-Id", userID)
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("like comment %s: expected 200, got %d: %s", commentID, rec.Code, rec.Body.String())
		}
	}

	listComments := func(sort string) []map[string]any {
		t.Helper()
		req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/comments?sort="+sort+"&limit=10", nil)
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("list comments sort=%s: expected 200, got %d: %s", sort, rec.Code, rec.Body.String())
		}
		var resp map[string]any
		if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
			t.Fatalf("decode list comments sort=%s: %v", sort, err)
		}
		items, _ := resp["items"].([]any)
		out := make([]map[string]any, 0, len(items))
		for _, item := range items {
			if mapped, ok := item.(map[string]any); ok {
				out = append(out, mapped)
			}
		}
		return out
	}

	olderID := createComment("sort_author_old", "较早评论")
	time.Sleep(1100 * time.Millisecond)
	newerID := createComment("sort_author_new", "较新评论")
	likeComment(olderID, "sort_liker_1")
	likeComment(olderID, "sort_liker_2")

	recommended := listComments("recommended")
	if len(recommended) != 2 {
		t.Fatalf("expected 2 recommended comments, got %d", len(recommended))
	}
	if recommended[0]["_id"] != olderID {
		t.Fatalf("expected recommended sort to keep the high-score older comment first, got %v", recommended[0]["_id"])
	}
	if recommended[1]["_id"] != newerID {
		t.Fatalf("expected recommended sort to keep the newer comment second, got %v", recommended[1]["_id"])
	}

	latest := listComments("latest")
	if len(latest) != 2 {
		t.Fatalf("expected 2 latest comments, got %d", len(latest))
	}
	if latest[0]["_id"] != newerID {
		t.Fatalf("expected latest sort to return newer comment first, got %v", latest[0]["_id"])
	}
	if latest[1]["_id"] != olderID {
		t.Fatalf("expected latest sort to return older comment second, got %v", latest[1]["_id"])
	}

	mostLiked := listComments("most_liked")
	if len(mostLiked) != 2 {
		t.Fatalf("expected 2 most_liked comments, got %d", len(mostLiked))
	}
	if mostLiked[0]["_id"] != olderID {
		t.Fatalf("expected most_liked sort to return liked older comment first, got %v", mostLiked[0]["_id"])
	}
	if mostLiked[1]["_id"] != newerID {
		t.Fatalf("expected most_liked sort to return newer comment second, got %v", mostLiked[1]["_id"])
	}
}

func TestCreateCommentWithAttachmentAndMentions(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Comment attachment mention","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("missing post id for attachment mention test")
	}

	mediaInitReq := httptest.NewRequest(http.MethodPost, "/v1/content/media/uploads:init", strings.NewReader(`{"mediaType":"image","assetScope":"comment"}`))
	mediaInitReq.Header.Set("Content-Type", "application/json")
	mediaInitReq.Header.Set("X-Client-User-Id", "comment_media_author")
	mediaInitRec := httptest.NewRecorder()
	testHandler.ServeHTTP(mediaInitRec, mediaInitReq)
	if mediaInitRec.Code != http.StatusOK {
		t.Fatalf("init media: expected 200, got %d: %s", mediaInitRec.Code, mediaInitRec.Body.String())
	}
	var mediaInitResp map[string]any
	if err := json.Unmarshal(mediaInitRec.Body.Bytes(), &mediaInitResp); err != nil {
		t.Fatalf("decode media init response: %v", err)
	}
	sessionID := asTestString(mediaInitResp["sessionId"])
	mediaID := asTestString(mediaInitResp["mediaId"])
	if sessionID == "" || mediaID == "" {
		t.Fatalf("missing media session or id: sessionID=%q mediaID=%q", sessionID, mediaID)
	}

	completeReq := httptest.NewRequest(http.MethodPost, "/v1/content/media/uploads/"+sessionID+":complete", nil)
	completeReq.Header.Set("X-Client-User-Id", "comment_media_author")
	completeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(completeRec, completeReq)
	if completeRec.Code != http.StatusOK {
		t.Fatalf("complete media: expected 200, got %d: %s", completeRec.Code, completeRec.Body.String())
	}

	commentBody := `{"content":"附件和提及评论","attachmentMediaIds":["` + mediaID + `"],"mentions":[{"type":"assistant","targetId":"assistant_xiaoqu","displayName":"小趣"}]}`
	commentReq := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(commentBody))
	commentReq.Header.Set("Content-Type", "application/json")
	commentReq.Header.Set("X-Client-User-Id", "comment_media_author")
	commentRec := httptest.NewRecorder()
	testHandler.ServeHTTP(commentRec, commentReq)
	if commentRec.Code != http.StatusCreated {
		t.Fatalf("create comment: expected 201, got %d: %s", commentRec.Code, commentRec.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(commentRec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode create comment response: %v", err)
	}
	comment, _ := resp["comment"].(map[string]any)
	if comment == nil {
		t.Fatal("create comment response missing comment object")
	}
	if comment["assistantMentioned"] != true {
		t.Fatalf("expected assistantMentioned=true, got %v", comment["assistantMentioned"])
	}
	if comment["content"] != "附件和提及评论" {
		t.Fatalf("expected comment content to round-trip, got %v", comment["content"])
	}
	attachmentIDs, _ := comment["attachmentMediaIds"].([]any)
	if len(attachmentIDs) != 1 || attachmentIDs[0] != mediaID {
		t.Fatalf("expected attachmentMediaIds to contain %q, got %v", mediaID, comment["attachmentMediaIds"])
	}
	attachments, _ := comment["attachments"].([]any)
	if len(attachments) != 1 {
		t.Fatalf("expected one attachment snapshot, got %d", len(attachments))
	}
	attachment, _ := attachments[0].(map[string]any)
	if attachment["mediaId"] != mediaID {
		t.Fatalf("expected attachment mediaId=%q, got %v", mediaID, attachment["mediaId"])
	}
	mentions, _ := comment["mentions"].([]any)
	if len(mentions) != 1 {
		t.Fatalf("expected one mention snapshot, got %d", len(mentions))
	}
	mention, _ := mentions[0].(map[string]any)
	if mention["type"] != "assistant" || mention["targetId"] != "assistant_xiaoqu" || mention["displayName"] != "小趣" {
		t.Fatalf("unexpected mention snapshot: %+v", mention)
	}
}

func TestCommentReplyPreviewAndExpandContract(t *testing.T) {
	TestCommentRepliesAttachmentsAndMentionsContract(t)
}

func TestCommentRepliesAttachmentsAndMentionsContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Reply contract","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	parentReq := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(`{"content":"父评论","mentions":[{"type":"assistant","targetId":"assistant_xiaoqu","displayName":"小趣"}]}`))
	parentReq.Header.Set("Content-Type", "application/json")
	parentReq.Header.Set("X-Client-User-Id", "author_parent")
	parentRec := httptest.NewRecorder()
	testHandler.ServeHTTP(parentRec, parentReq)
	if parentRec.Code != http.StatusCreated {
		t.Fatalf("create parent comment: expected 201, got %d: %s", parentRec.Code, parentRec.Body.String())
	}
	var parentResp map[string]any
	json.Unmarshal(parentRec.Body.Bytes(), &parentResp)
	parent, _ := parentResp["comment"].(map[string]any)
	parentID, _ := parent["_id"].(string)
	if parent["assistantMentioned"] != true {
		t.Fatalf("expected assistantMentioned=true on assistant mention parent, got %v", parent["assistantMentioned"])
	}

	mediaInitReq := httptest.NewRequest(http.MethodPost, "/v1/content/media/uploads:init", strings.NewReader(`{"mediaType":"image","assetScope":"comment"}`))
	mediaInitReq.Header.Set("Content-Type", "application/json")
	mediaInitReq.Header.Set("X-Client-User-Id", "author_reply")
	mediaInitRec := httptest.NewRecorder()
	testHandler.ServeHTTP(mediaInitRec, mediaInitReq)
	if mediaInitRec.Code != http.StatusOK {
		t.Fatalf("init media: expected 200, got %d: %s", mediaInitRec.Code, mediaInitRec.Body.String())
	}
	var mediaInitResp map[string]any
	json.Unmarshal(mediaInitRec.Body.Bytes(), &mediaInitResp)
	sessionID, _ := mediaInitResp["sessionId"].(string)
	mediaID, _ := mediaInitResp["mediaId"].(string)
	completeReq := httptest.NewRequest(http.MethodPost, "/v1/content/media/uploads/"+sessionID+":complete", nil)
	completeReq.Header.Set("X-Client-User-Id", "author_reply")
	completeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(completeRec, completeReq)
	if completeRec.Code != http.StatusOK {
		t.Fatalf("complete media: expected 200, got %d: %s", completeRec.Code, completeRec.Body.String())
	}

	replyBody := `{"content":"回复带图和提及","replyToCommentId":"` + parentID + `","attachmentMediaIds":["` + mediaID + `"],"mentions":[{"type":"user","targetId":"user_target","displayName":"目标用户"}]}`
	replyReq := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(replyBody))
	replyReq.Header.Set("Content-Type", "application/json")
	replyReq.Header.Set("X-Client-User-Id", "author_reply")
	replyRec := httptest.NewRecorder()
	testHandler.ServeHTTP(replyRec, replyReq)
	if replyRec.Code != http.StatusCreated {
		t.Fatalf("create reply: expected 201, got %d: %s", replyRec.Code, replyRec.Body.String())
	}

	listReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/comments?sort=recommended&limit=10", nil)
	listReq.Header.Set("X-Client-User-Id", "viewer_one")
	listRec := httptest.NewRecorder()
	testHandler.ServeHTTP(listRec, listReq)
	if listRec.Code != http.StatusOK {
		t.Fatalf("list root comments: expected 200, got %d: %s", listRec.Code, listRec.Body.String())
	}
	var listResp map[string]any
	json.Unmarshal(listRec.Body.Bytes(), &listResp)
	items, _ := listResp["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected only root comments in ListComments, got %d", len(items))
	}
	root, _ := items[0].(map[string]any)
	if root["replyCount"].(float64) != 1 {
		t.Errorf("expected replyCount=1, got %v", root["replyCount"])
	}
	preview, _ := root["replyPreview"].([]any)
	if len(preview) != 1 {
		t.Fatalf("expected one reply preview, got %d", len(preview))
	}

	repliesReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/comments/"+parentID+"/replies?limit=10", nil)
	repliesReq.Header.Set("X-Client-User-Id", "viewer_one")
	repliesRec := httptest.NewRecorder()
	testHandler.ServeHTTP(repliesRec, repliesReq)
	if repliesRec.Code != http.StatusOK {
		t.Fatalf("list replies: expected 200, got %d: %s", repliesRec.Code, repliesRec.Body.String())
	}
	var repliesResp map[string]any
	json.Unmarshal(repliesRec.Body.Bytes(), &repliesResp)
	replies, _ := repliesResp["items"].([]any)
	if len(replies) != 1 {
		t.Fatalf("expected one reply, got %d", len(replies))
	}
	reply, _ := replies[0].(map[string]any)
	attachments, _ := reply["attachments"].([]any)
	if len(attachments) != 1 {
		t.Errorf("expected one attachment, got %d", len(attachments))
	}
	mentions, _ := reply["mentions"].([]any)
	if len(mentions) != 1 {
		t.Errorf("expected one mention, got %d", len(mentions))
	}
	if reply["viewerReaction"] != "none" {
		t.Errorf("expected default viewerReaction=none, got %v", reply["viewerReaction"])
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
	if resp["schemaVersion"] != "app_remote_config.v1" {
		t.Fatalf("expected schemaVersion app_remote_config.v1, got %v", resp["schemaVersion"])
	}
	if resp["packageVersion"] == "" {
		t.Fatal("missing packageVersion")
	}
	configHash, _ := resp["configHash"].(string)
	if !strings.HasPrefix(configHash, "sha256:") {
		t.Fatalf("expected sha256 configHash, got %v", resp["configHash"])
	}
	if rec.Header().Get("ETag") != configHash {
		t.Fatalf("expected ETag to match configHash, got %q", rec.Header().Get("ETag"))
	}
	if resp["maxAgeSec"] != float64(21600) {
		t.Fatalf("expected maxAgeSec=21600, got %v", resp["maxAgeSec"])
	}
	activationPolicy, _ := resp["activationPolicy"].(map[string]any)
	if activationPolicy["default"] != "next_session" {
		t.Fatalf("expected activation default next_session, got %v", activationPolicy["default"])
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
	// 二级回复分层展开契约（对齐 content_app_config_client.yaml#comment_defaults，
	// 端 CommentRemoteConfig 消费）：默认回显 1 条、首展 5 条、续展 10 条。
	if comment["reply_preview_count"] != float64(1) {
		t.Errorf("expected reply_preview_count=1, got %v", comment["reply_preview_count"])
	}
	if comment["reply_first_expand_page_size"] != float64(5) {
		t.Errorf("expected reply_first_expand_page_size=5, got %v", comment["reply_first_expand_page_size"])
	}
	if comment["reply_expand_page_size"] != float64(10) {
		t.Errorf("expected reply_expand_page_size=10, got %v", comment["reply_expand_page_size"])
	}
	if comment["fold_line_count"] != float64(3) {
		t.Errorf("expected fold_line_count=3, got %v", comment["fold_line_count"])
	}
	attachment, _ := comment["attachment"].(map[string]any)
	if attachment["max_images"] != float64(1) {
		t.Fatalf("expected attachment.max_images=1, got %v", attachment["max_images"])
	}
	if _, ok := comment["attachment_max_count"]; ok {
		t.Fatalf("did not expect comment.attachment_max_count in app config")
	}
	featureFlags, _ := content["feature_flags"].(map[string]any)
	if featureFlags == nil {
		t.Fatal("missing 'content.feature_flags' in app config")
	}
	for _, key := range []string{
		"enable_create_action_entry",
		"enable_unified_create_editor",
		"enable_identity_based_surfaces",
		"enable_identity_share_template",
		"enable_assistant_content_identity_index",
	} {
		if featureFlags[key] != true {
			t.Fatalf("expected feature flag %s=true, got %v", key, featureFlags[key])
		}
	}
	grayRelease, _ := content["gray_release"].(map[string]any)
	if grayRelease == nil {
		t.Fatal("missing 'content.gray_release' in app config")
	}
	if grayRelease["current_stage"] != "100%" {
		t.Fatalf("expected current_stage=100%%, got %v", grayRelease["current_stage"])
	}

	notModifiedReq := httptest.NewRequest(http.MethodGet, "/v1/config/app", nil)
	notModifiedReq.Header.Set("If-None-Match", configHash)
	notModifiedRec := httptest.NewRecorder()
	testHandler.ServeHTTP(notModifiedRec, notModifiedReq)
	if notModifiedRec.Code != http.StatusNotModified {
		t.Fatalf("expected 304 for matching ETag, got %d", notModifiedRec.Code)
	}
}

func TestGetAppConfigRuntimeOverrides(t *testing.T) {
	service := application.NewPostService(
		persistence.NewPostStore(nil),
		application.WithStoryRuntimeConfig(application.StoryRuntimeConfig{
			FeatureFlags: map[string]bool{
				"enable_identity_share_template":          false,
				"enable_assistant_content_identity_index": false,
			},
			ExperimentBucket: "rollout_20",
			CurrentStage:     "20%",
			CanaryMatrix: []application.StoryCanaryStage{
				{Stage: "5%", RolloutPercent: 5},
				{Stage: "20%", RolloutPercent: 20},
			},
		}),
	)

	resp := service.GetAppConfig()
	content, _ := resp["content"].(map[string]any)
	if content == nil {
		t.Fatal("missing content config")
	}
	featureFlags, _ := content["feature_flags"].(map[string]any)
	if featureFlags == nil {
		t.Fatal("missing feature flags")
	}
	if featureFlags["enable_identity_share_template"] != false {
		t.Fatalf(
			"expected enable_identity_share_template=false, got %v",
			featureFlags["enable_identity_share_template"],
		)
	}
	if featureFlags["enable_create_action_entry"] != true {
		t.Fatalf(
			"expected unspecified kill switch fallback to true, got %v",
			featureFlags["enable_create_action_entry"],
		)
	}

	grayRelease, _ := content["gray_release"].(map[string]any)
	if grayRelease == nil {
		t.Fatal("missing gray release config")
	}
	if grayRelease["experiment_bucket"] != "rollout_20" {
		t.Fatalf(
			"expected experiment_bucket=rollout_20, got %v",
			grayRelease["experiment_bucket"],
		)
	}
	if grayRelease["current_stage"] != "20%" {
		t.Fatalf("expected current_stage=20%%, got %v", grayRelease["current_stage"])
	}
	canaryMatrix, _ := grayRelease["canary_matrix"].([]any)
	if len(canaryMatrix) != 2 {
		t.Fatalf("expected 2 canary stages, got %d", len(canaryMatrix))
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
