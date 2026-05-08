// L2 契约测试：Post 业务对象 — 评论 CRUD、分页、点赞、排序、个人主页、App Config
package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

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
	canaryMatrix, _ := grayRelease["canary_matrix"].([]map[string]any)
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
