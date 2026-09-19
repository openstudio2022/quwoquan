// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-003
// readiness_case: update-post-settings-api
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-009
// 发布后设置持久化与作者回读的服务侧证据；不代表完整端云设置旅程通过。
package api_integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"

	semanticfixture "quwoquan_service/services/content-service/tests/support/semanticfixture"
)

func TestSubmitPostPublicationPersistsContentTypeAndAssistantUsePolicy(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	for _, contentType := range []string{"image", "video", "article"} {
		t.Run(contentType, func(t *testing.T) {
			resp := submitPublishedPostWithAuthor(t, "content_type_author_"+contentType, `{
				"contentType":"`+contentType+`",
				"assistantUsePolicy":"exclude",
				"body":"发布后保留的正文"
			}`)
			if resp["contentType"] != contentType {
				t.Fatalf("expected contentType=%s, got %v", contentType, resp["contentType"])
			}
			if resp["assistantUsePolicy"] != "exclude" {
				t.Fatalf("expected assistantUsePolicy=exclude, got %v", resp["assistantUsePolicy"])
			}
			if resp["status"] != "published" {
				t.Fatalf("expected status=published after atomic publication, got %v", resp["status"])
			}
		})
	}
}

func TestUpdatePostSettingsContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPostWithAuthor(t, "settings_author", `{
		"contentType":"article",
		"title":"可调整设置的作品",
		"body":"发布内容保持不可变"
	}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("created post must have an id")
	}

	request := httptest.NewRequest(
		http.MethodPatch,
		"/content/posts/"+postID+"/settings",
		strings.NewReader(`{
			"visibility":"private",
			"assistantUsePolicy":"exclude"
		}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Client-User-Id", "settings_author")
	ensureIdempotencyHeader(request, "update-settings")
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("update settings status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	var updated map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &updated); err != nil {
		t.Fatalf("decode settings response: %v", err)
	}
	if updated["visibility"] != "private" || updated["assistantUsePolicy"] != "exclude" {
		t.Fatalf("updated settings drifted: %+v", updated)
	}

	ownerRequest := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	ownerRequest.Header.Set("X-Client-User-Id", "settings_author")
	ownerRecorder := httptest.NewRecorder()
	testHandler.ServeHTTP(ownerRecorder, ownerRequest)
	if ownerRecorder.Code != http.StatusOK {
		t.Fatalf("owner read after settings update status=%d body=%s", ownerRecorder.Code, ownerRecorder.Body.String())
	}
	var persisted map[string]any
	if err := json.Unmarshal(ownerRecorder.Body.Bytes(), &persisted); err != nil {
		t.Fatalf("decode persisted post: %v", err)
	}
	if persisted["visibility"] != "private" || persisted["assistantUsePolicy"] != "exclude" {
		t.Fatalf("persisted settings drifted: %+v", persisted)
	}
}

func TestUpdatePostSettingsRejectsRetiredCirclePlacementFields(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPostWithAuthor(t, "settings_author", `{
		"contentType":"image",
		"title":"初始作品"
	}`)
	postID, _ := created["postId"].(string)

	req := httptest.NewRequest(
		http.MethodPatch,
		"/content/posts/"+postID+"/settings",
		strings.NewReader(`{
			"visibility":"public",
			"circleIds":["circle_a","circle_b"],
			"assistantUsePolicy":"exclude"
		}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "settings_author")
	ensureIdempotencyHeader(req, "update-settings-retired-field")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("Post must reject CirclePostPlacement fields, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestRetiredPromoteRouteCannotMutateArticleCountersOrCommentThread(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPostWithAuthor(t, "promote_thread_author", `{
		"contentType":"article",
		"title":"不可变文章",
		"body":"旧入口不得改变的正文"
	}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("expected post id")
	}

	commentReq := httptest.NewRequest(
		http.MethodPost,
		"/content/posts/"+postID+"/comments",
		strings.NewReader(`{"content":"这条评论升级后也要保留"}`),
	)
	commentReq.Header.Set("Content-Type", "application/json")
	commentReq.Header.Set("X-Client-User-Id", "thread_commenter")
	commentReq.Header.Set("X-Client-Persona-Id", "thread_commenter")
	ensureIdempotencyHeader(commentReq, "promote-thread-comment")
	commentRec := httptest.NewRecorder()
	testHandler.ServeHTTP(commentRec, commentReq)
	if commentRec.Code != http.StatusCreated {
		t.Fatalf("expected 201 comment created, got %d: %s", commentRec.Code, commentRec.Body.String())
	}

	likeReq := httptest.NewRequest(http.MethodPost, "/content/posts/"+postID+"/like", nil)
	likeReq.Header.Set("X-Client-User-Id", "thread_liker")
	ensureIdempotencyHeader(likeReq, "promote-thread-like")
	likeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(likeRec, likeReq)
	if likeRec.Code != http.StatusOK {
		t.Fatalf("expected 200 like response, got %d: %s", likeRec.Code, likeRec.Body.String())
	}
	// 先经过 ContentReaction 的生产 outbox 收敛，再验证退役入口不能改变已有计数。
	drainReactionOutbox(t)
	beforeCountersReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID+"/counters", nil)
	beforeCountersRec := httptest.NewRecorder()
	testHandler.ServeHTTP(beforeCountersRec, beforeCountersReq)
	if beforeCountersRec.Code != http.StatusOK {
		t.Fatalf("read counters before retired request status=%d body=%s", beforeCountersRec.Code, beforeCountersRec.Body.String())
	}
	var beforeCounters map[string]any
	if err := json.Unmarshal(beforeCountersRec.Body.Bytes(), &beforeCounters); err != nil {
		t.Fatalf("decode counters before retired request: %v", err)
	}
	if beforeCounters["likeCount"] != float64(1) || beforeCounters["commentCount"] != float64(1) {
		t.Fatalf("must establish existing like and comment before retired request: %+v", beforeCounters)
	}

	promoteBody, err := json.Marshal(map[string]any{"contentType": "article", "title": "升级后的长文", "articleMarkdown": "# 升级后的长文\n\n升级后正文", "markdownDialect": "qwq-rich-md", "semanticDocument": semanticfixture.Map(t), "articleAssetManifest": map[string]any{"assets": []any{}}})
	if err != nil {
		t.Fatal(err)
	}
	promoteReq := httptest.NewRequest(http.MethodPost, "/content/posts/"+postID+":promoteToWork", bytes.NewReader(promoteBody))
	promoteReq.Header.Set("Content-Type", "application/json")
	promoteReq.Header.Set("X-Client-User-Id", "promote_thread_author")
	ensureIdempotencyHeader(promoteReq, "promote-thread")
	promoteRec := httptest.NewRecorder()
	testHandler.ServeHTTP(promoteRec, promoteReq)
	if promoteRec.Code != http.StatusNotFound {
		t.Fatalf("retired route must return 404, got %d: %s", promoteRec.Code, promoteRec.Body.String())
	}

	articleReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	articleReq.Header.Set("X-Client-User-Id", "promote_thread_author")
	articleRec := httptest.NewRecorder()
	testHandler.ServeHTTP(articleRec, articleReq)
	if articleRec.Code != http.StatusOK {
		t.Fatalf("read unchanged article status=%d body=%s", articleRec.Code, articleRec.Body.String())
	}
	var article map[string]any
	if err := json.Unmarshal(articleRec.Body.Bytes(), &article); err != nil {
		t.Fatalf("decode unchanged article: %v", err)
	}
	for _, field := range []string{"postId", "contentType", "title", "body", "articleMarkdown", "articleMarkdownDigest", "semanticDocument", "assistantUsePolicy"} {
		if !reflect.DeepEqual(article[field], created[field]) {
			t.Fatalf("retired route changed %s: before=%v after=%v", field, created[field], article[field])
		}
	}

	countersReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID+"/counters", nil)
	countersRec := httptest.NewRecorder()
	testHandler.ServeHTTP(countersRec, countersReq)
	if countersRec.Code != http.StatusOK {
		t.Fatalf("expected 200 counters response, got %d: %s", countersRec.Code, countersRec.Body.String())
	}
	var counters map[string]any
	if err := json.Unmarshal(countersRec.Body.Bytes(), &counters); err != nil {
		t.Fatalf("decode counters: %v", err)
	}
	if !reflect.DeepEqual(counters, beforeCounters) {
		t.Fatalf("retired route changed counters: before=%+v after=%+v", beforeCounters, counters)
	}
	if counters["likeCount"] != float64(1) {
		t.Fatalf("expected like counter preserved, got %v", counters["likeCount"])
	}
	if counters["commentCount"] != float64(1) {
		t.Fatalf("expected comment counter preserved, got %v", counters["commentCount"])
	}

	commentsReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID+"/comments?limit=20", nil)
	commentsRec := httptest.NewRecorder()
	testHandler.ServeHTTP(commentsRec, commentsReq)
	if commentsRec.Code != http.StatusOK {
		t.Fatalf("expected 200 comments response, got %d: %s", commentsRec.Code, commentsRec.Body.String())
	}
	var commentsResp struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(commentsRec.Body.Bytes(), &commentsResp); err != nil {
		t.Fatalf("decode comments response: %v", err)
	}
	if len(commentsResp.Items) != 1 {
		t.Fatalf("expected comment thread preserved, got %d comments", len(commentsResp.Items))
	}
	if commentsResp.Items[0]["content"] != "这条评论升级后也要保留" {
		t.Fatalf("expected preserved comment content, got %v", commentsResp.Items[0]["content"])
	}
}

func TestAssistantAccessRevokedAfterSettingsChange(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPostWithAuthor(t, "assistant_author", `{
		"contentType":"article",
		"title":"可被小趣引用的作品",
		"body":"初始正文"
	}`)
	postID, _ := created["postId"].(string)

	req := httptest.NewRequest(
		http.MethodPatch,
		"/content/posts/"+postID+"/settings",
		strings.NewReader(`{
			"visibility":"private",
			"assistantUsePolicy":"exclude"
		}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "assistant_author")
	ensureIdempotencyHeader(req, "assistant-settings")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	getReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	getReq.Header.Set("X-Client-User-Id", "assistant_author")
	getRec := httptest.NewRecorder()
	testHandler.ServeHTTP(getRec, getReq)
	if getRec.Code != http.StatusOK {
		t.Fatalf("expected 200 on get, got %d: %s", getRec.Code, getRec.Body.String())
	}
	var getResp map[string]any
	if err := json.Unmarshal(getRec.Body.Bytes(), &getResp); err != nil {
		t.Fatalf("decode get response: %v", err)
	}
	if getResp["visibility"] != "private" {
		t.Fatalf("expected visibility=private, got %v", getResp["visibility"])
	}
	if getResp["assistantUsePolicy"] != "exclude" {
		t.Fatalf("expected assistantUsePolicy=exclude, got %v", getResp["assistantUsePolicy"])
	}

	viewerReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	viewerReq.Header.Set("X-Client-User-Id", "assistant_viewer")
	viewerRec := httptest.NewRecorder()
	testHandler.ServeHTTP(viewerRec, viewerReq)
	if viewerRec.Code != http.StatusNotFound {
		t.Fatalf("expected non-disclosing 404 for revoked viewer access, got %d: %s", viewerRec.Code, viewerRec.Body.String())
	}
	assertStablePostNotFound(t, viewerRec.Body.Bytes())

}

func TestPrivatePostBlocksNonAuthorViewer(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPostWithAuthor(t, "private_author", `{
		"contentType":"article",
		"title":"私密作品",
		"body":"仅自己可见",
		"visibility":"private"
	}`)
	postID, _ := created["postId"].(string)

	req := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	req.Header.Set("X-Client-User-Id", "other_viewer")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected non-disclosing 404, got %d: %s", rec.Code, rec.Body.String())
	}
	assertStablePostNotFound(t, rec.Body.Bytes())
}

func assertStablePostNotFound(t *testing.T, raw []byte) {
	t.Helper()
	var failure struct {
		Code   string `json:"code"`
		Reason string `json:"reason"`
	}
	if err := json.Unmarshal(raw, &failure); err != nil {
		t.Fatalf("decode post visibility failure: %v", err)
	}
	if failure.Code != "CONTENT.USER.post_not_found" || failure.Reason != "not_found" {
		t.Fatalf("unexpected post visibility failure: %+v", failure)
	}
}

func TestPostCreateRejectsDirectCirclePlacement(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	payload := completePublicationFixturePrerequisites(t, "circle_author", `{
		"contentType":"article",
		"title":"圈内作品",
		"body":"仅圈成员可见",
		"articleMarkdown":"# 圈内作品\n\n仅圈成员可见",
		"markdownDialect":"qwq-rich-md",
		"articleAssetManifest":{"assets":[]},
		"visibility":"circle_visible",
		"circleIds":["circle_alpha"]
	}`)
	request := newPostPublicationRequestForTest(t, "circle_author", payload)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("Post cannot mutate CirclePostPlacement, got %d: %s", recorder.Code, recorder.Body.String())
	}
}

func TestListUserPostsByContentType(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	postIDs := make(map[string]any)
	for _, contentType := range []string{"image", "video", "article"} {
		created := submitPublishedPostWithAuthor(t, "content_type_feed_author", `{
			"contentType":"`+contentType+`",
			"title":"旅行记录",
			"body":"各类型独立筛选"
		}`)
		postIDs[contentType] = created["postId"]
	}
	for _, contentType := range []string{"image", "video", "article"} {
		t.Run(contentType, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet,
				"/content/personas/content_type_feed_author/posts?type="+contentType+"&limit=20", nil)
			rec := httptest.NewRecorder()
			testHandler.ServeHTTP(rec, req)
			if rec.Code != http.StatusOK {
				t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
			}
			var resp struct {
				Items []map[string]any `json:"items"`
			}
			if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
				t.Fatalf("decode response: %v", err)
			}
			if len(resp.Items) != 1 {
				t.Fatalf("expected one %s post among three types, got %d", contentType, len(resp.Items))
			}
			if resp.Items[0]["contentType"] != contentType || resp.Items[0]["postId"] != postIDs[contentType] {
				t.Fatalf("content type filter returned another post: %+v", resp.Items[0])
			}
		})
	}
}
