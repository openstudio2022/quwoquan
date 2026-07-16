package api_integration

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
)

// 本文件只验证 Comment / ContentReaction 对象 Facade 的正式 HTTP 契约。
// 不再承载 PostService 评论方法、旧 comment DTO、排序别名或响应兼容层。

func TestCommentWithNotification(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "comment-post-owner")

	result := createCommentThroughAPI(t, postID, "comment-author", "这张图真漂亮！", "")
	if result.ID == "" || result.Version != 1 || result.Status != "active" {
		t.Fatalf("unexpected Comment command result: %+v", result)
	}

	events := eventSpy.EventsOfType("CommentCreated")
	if len(events) != 1 {
		t.Fatalf("expected one durable CommentCreated delivery, got %d", len(events))
	}
	if events[0].AggregateID != result.ID || events[0].AggregateType != "Comment" {
		t.Fatalf("unexpected CommentCreated identity: %+v", events[0])
	}
}

func TestCommentListPagination(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "pagination-post-owner")

	for index := 0; index < 3; index++ {
		createCommentThroughAPI(t, postID, fmt.Sprintf("comment-author-%d", index), fmt.Sprintf("comment-%d", index), "")
	}
	first := listCommentsThroughAPI(t, postID, "viewer", "", 2)
	if len(first.Items) != 2 || first.NextCursor == "" || first.Total != 3 {
		t.Fatalf("unexpected first Comment page: %+v", first)
	}
	second := listCommentsThroughAPI(t, postID, "viewer", first.NextCursor, 2)
	if len(second.Items) != 1 || second.NextCursor != "" || second.Total != 3 {
		t.Fatalf("unexpected second Comment page: %+v", second)
	}
	if first.Items[0].ID == second.Items[0].ID || first.Items[1].ID == second.Items[0].ID {
		t.Fatalf("keyset pages overlap: first=%+v second=%+v", first, second)
	}
}

func TestDeleteComment(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "delete-post-owner")
	created := createCommentThroughAPI(t, postID, "comment-owner", "to be deleted", "")

	stale := commentAPIRequest(t, http.MethodDelete,
		"/v1/content/posts/"+postID+"/comments/"+created.ID,
		"comment-owner", map[string]any{"version": created.Version + 1})
	if stale.Code != http.StatusConflict {
		t.Fatalf("stale Comment delete status=%d body=%s", stale.Code, stale.Body.String())
	}

	deleted := commentAPIRequest(t, http.MethodDelete,
		"/v1/content/posts/"+postID+"/comments/"+created.ID,
		"comment-owner", map[string]any{"version": created.Version})
	if deleted.Code != http.StatusOK {
		t.Fatalf("delete Comment status=%d body=%s", deleted.Code, deleted.Body.String())
	}
	var result commentapp.CommentCommandResult
	decodeCommentResponse(t, deleted, &result)
	if result.Version != 2 || result.Status != "deleted" {
		t.Fatalf("unexpected deleted Comment result: %+v", result)
	}
	if page := listCommentsThroughAPI(t, postID, "viewer", "", 20); len(page.Items) != 0 || page.Total != 0 {
		t.Fatalf("deleted Comment leaked from active page: %+v", page)
	}
}

func TestGetCounters(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "counter-post-owner")
	createCommentThroughAPI(t, postID, "counter-commenter", "count me", "")

	recorder := commentAPIRequest(t, http.MethodGet,
		"/v1/content/posts/"+postID+"/counters", "viewer", nil)
	if recorder.Code != http.StatusOK {
		t.Fatalf("get counters status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var counters map[string]any
	decodeCommentResponse(t, recorder, &counters)
	if numberAsInt64(counters["comment"]) != 1 {
		t.Fatalf("Comment count projection is not converged: %+v", counters)
	}
}

func TestCommentCountersStayConsistentAcrossReadModels(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "consistency-post-owner")
	created := createCommentThroughAPI(t, postID, "consistency-commenter", "一致性评论", "")

	page := listCommentsThroughAPI(t, postID, "viewer", "", 20)
	counterRecorder := commentAPIRequest(t, http.MethodGet,
		"/v1/content/posts/"+postID+"/counters", "viewer", nil)
	var counters map[string]any
	decodeCommentResponse(t, counterRecorder, &counters)
	if page.Total != 1 || numberAsInt64(counters["comment"]) != page.Total {
		t.Fatalf("Comment reader/Post projection mismatch: page=%+v counters=%+v", page, counters)
	}

	deleteRecorder := commentAPIRequest(t, http.MethodDelete,
		"/v1/content/posts/"+postID+"/comments/"+created.ID,
		"consistency-commenter", map[string]any{"version": created.Version})
	if deleteRecorder.Code != http.StatusOK {
		t.Fatalf("delete status=%d body=%s", deleteRecorder.Code, deleteRecorder.Body.String())
	}
	page = listCommentsThroughAPI(t, postID, "viewer", "", 20)
	counterRecorder = commentAPIRequest(t, http.MethodGet,
		"/v1/content/posts/"+postID+"/counters", "viewer", nil)
	decodeCommentResponse(t, counterRecorder, &counters)
	if page.Total != 0 || numberAsInt64(counters["comment"]) != 0 {
		t.Fatalf("Comment deletion projection mismatch: page=%+v counters=%+v", page, counters)
	}
}

func TestReactToCommentThreeStateContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "reaction-post-owner")
	comment := createCommentThroughAPI(t, postID, "reaction-commenter", "reaction target", "")

	like := reactToCommentThroughAPI(t, comment.ID, "viewer-a", "like")
	if like.Reaction != "like" || like.LikeCount != 1 || like.DislikeCount != 0 {
		t.Fatalf("unexpected like transition: %+v", like)
	}
	dislike := reactToCommentThroughAPI(t, comment.ID, "viewer-a", "dislike")
	if dislike.Reaction != "dislike" || dislike.LikeCount != 0 || dislike.DislikeCount != 1 {
		t.Fatalf("unexpected dislike transition: %+v", dislike)
	}
	secondLike := reactToCommentThroughAPI(t, comment.ID, "viewer-b", "like")
	if secondLike.LikeCount != 1 || secondLike.DislikeCount != 1 {
		t.Fatalf("cross-actor counts must be exact: %+v", secondLike)
	}
	cleared := reactToCommentThroughAPI(t, comment.ID, "viewer-a", "none")
	if cleared.Reaction != "none" || cleared.LikeCount != 1 || cleared.DislikeCount != 0 {
		t.Fatalf("unexpected clear transition: %+v", cleared)
	}
}

func TestReactToCommentContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "reaction-strict-post-owner")
	comment := createCommentThroughAPI(t, postID, "reaction-strict-commenter", "strict target", "")

	unsupported := commentAPIRequest(t, http.MethodPost,
		"/v1/content/comments/"+comment.ID+"/reaction",
		"viewer", map[string]any{"viewerReaction": "like"})
	if unsupported.Code != http.StatusBadRequest {
		t.Fatalf("unsupported reaction alias must be rejected, status=%d body=%s", unsupported.Code, unsupported.Body.String())
	}
	missing := commentAPIRequest(t, http.MethodPost,
		"/v1/content/comments/missing-comment/reaction",
		"viewer", map[string]any{"reaction": "like"})
	if missing.Code != http.StatusNotFound {
		t.Fatalf("missing Comment reaction target status=%d body=%s", missing.Code, missing.Body.String())
	}
}

func TestListCommentsByAuthor(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "author-page-post-owner")
	created := createCommentThroughAPI(t, postID, "comment-page-author", "authored comment", "")
	recorder := commentAPIRequest(t, http.MethodGet,
		"/v1/content/users/me/comments?limit=20", "comment-page-author", nil)
	if recorder.Code != http.StatusOK {
		t.Fatalf("author Comment page status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var page commentapp.AuthorCommentPageSlice
	decodeCommentResponse(t, recorder, &page)
	if len(page.Items) != 1 || page.Items[0].ID != created.ID {
		t.Fatalf("unexpected author Comment page: %+v", page)
	}
}

func TestListCommentsForPostAuthorContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "received-post-owner")
	created := createCommentThroughAPI(t, postID, "received-commenter", "received comment", "")
	recorder := commentAPIRequest(t, http.MethodGet,
		"/v1/content/users/me/received-comments?limit=20", "received-post-owner", nil)
	if recorder.Code != http.StatusOK {
		t.Fatalf("received Comment page status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var page commentapp.ReceivedCommentPageSlice
	decodeCommentResponse(t, recorder, &page)
	if len(page.Items) != 1 || page.Items[0].ID != created.ID {
		t.Fatalf("unexpected received Comment page: %+v", page)
	}
}

func createCommentTestPost(t *testing.T, ownerID string) string {
	t.Helper()
	created := createPostWithAuthor(t, ownerID,
		`{"contentType":"image","title":"Comment object target","mediaUrls":["https://example.com/comment.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		postID, _ = created["id"].(string)
	}
	if postID == "" {
		t.Fatalf("Comment target Post response has no id: %+v", created)
	}
	return postID
}

func createCommentThroughAPI(
	t *testing.T,
	postID string,
	actorID string,
	content string,
	replyToCommentID string,
) commentapp.CommentCommandResult {
	t.Helper()
	recorder := commentAPIRequest(t, http.MethodPost,
		"/v1/content/posts/"+postID+"/comments", actorID,
		map[string]any{"content": content, "replyToCommentId": replyToCommentID, "mentions": []any{}})
	if recorder.Code != http.StatusCreated {
		t.Fatalf("create Comment status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var result commentapp.CommentCommandResult
	decodeCommentResponse(t, recorder, &result)
	return result
}

func listCommentsThroughAPI(
	t *testing.T,
	postID string,
	actorID string,
	cursor string,
	limit int,
) commentapp.CommentPageSlice {
	t.Helper()
	path := fmt.Sprintf("/v1/content/posts/%s/comments?limit=%d", postID, limit)
	if cursor != "" {
		path += "&cursor=" + cursor
	}
	recorder := commentAPIRequest(t, http.MethodGet, path, actorID, nil)
	if recorder.Code != http.StatusOK {
		t.Fatalf("list Comments status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var page commentapp.CommentPageSlice
	decodeCommentResponse(t, recorder, &page)
	return page
}

func reactToCommentThroughAPI(
	t *testing.T,
	commentID string,
	actorID string,
	reaction string,
) reactionapp.CommentReactionCommandResult {
	t.Helper()
	recorder := commentAPIRequest(t, http.MethodPost,
		"/v1/content/comments/"+commentID+"/reaction", actorID,
		map[string]any{"reaction": reaction})
	if recorder.Code != http.StatusOK {
		t.Fatalf("react to Comment status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var result reactionapp.CommentReactionCommandResult
	decodeCommentResponse(t, recorder, &result)
	return result
}

func commentAPIRequest(
	t *testing.T,
	method string,
	path string,
	actorID string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal Comment request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	request.Header.Set("X-Client-User-Id", actorID)
	request.Header.Set("X-Client-Sub-Account-Id", actorID)
	if method != http.MethodGet && method != http.MethodHead {
		ensureIdempotencyHeader(request,
			fmt.Sprintf("comment-%s-%d", t.Name(), helperRequestSequence.Add(1)))
	}
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	return recorder
}

func decodeCommentResponse(t *testing.T, recorder *httptest.ResponseRecorder, target any) {
	t.Helper()
	if err := json.Unmarshal(recorder.Body.Bytes(), target); err != nil {
		t.Fatalf("decode Comment response status=%d body=%s: %v", recorder.Code, recorder.Body.String(), err)
	}
}

func numberAsInt64(value any) int64 {
	switch typed := value.(type) {
	case int:
		return int64(typed)
	case int64:
		return typed
	case float64:
		return int64(typed)
	default:
		return 0
	}
}
