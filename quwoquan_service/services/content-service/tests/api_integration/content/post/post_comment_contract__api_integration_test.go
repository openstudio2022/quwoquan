package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rtoperation "quwoquan_service/runtime/operation"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	contenhttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
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

func TestCommentListEnforcesServerProjectedBlockFacts(t *testing.T) {
	ctx := context.Background()
	relationships := requireMongoDB(t).Collection("persona_follow_projection")
	viewerID := "comment_block_viewer"
	postOwnerID := "comment_block_post_owner"
	blockedCommenterID := "comment_block_author"
	cleanup := func() {
		cleanPosts(t)
		_, _ = relationships.DeleteMany(ctx, bson.M{
			"$or": []bson.M{
				{"sourcePersonaId": viewerID},
				{"targetPersonaId": viewerID},
			},
		})
	}
	cleanup()
	t.Cleanup(cleanup)

	postID := createCommentTestPost(t, postOwnerID)
	visible := createCommentThroughAPI(
		t,
		postID,
		"comment_visible_author",
		"visible comment",
		"",
	)
	createCommentThroughAPI(
		t,
		postID,
		blockedCommenterID,
		"blocked comment",
		"",
	)
	projector := recinfra.NewPersonaRelationshipProjection(requireMongoDB(t))
	if err := projector.Apply(ctx, recinfra.PersonaRelationshipProjectionEvent{
		EventID:         "comment_block_author_event",
		EventName:       recinfra.PersonaBlocked,
		PairID:          "comment_block_author_pair",
		SourcePersonaID: viewerID,
		TargetPersonaID: blockedCommenterID,
		Version:         1,
		OccurredAt:      time.Now().UTC(),
	}); err != nil {
		t.Fatalf("project commenter block event: %v", err)
	}

	page := listCommentsThroughAPI(t, postID, viewerID, "", 20)
	if len(page.Items) != 1 || page.Items[0].ID != visible.ID || page.Total != 1 {
		t.Fatalf("blocked commenter leaked into Comment page: %+v", page)
	}

	if err := projector.Apply(ctx, recinfra.PersonaRelationshipProjectionEvent{
		EventID:         "comment_block_owner_event",
		EventName:       recinfra.PersonaBlocked,
		PairID:          "comment_block_owner_pair",
		SourcePersonaID: viewerID,
		TargetPersonaID: postOwnerID,
		Version:         1,
		OccurredAt:      time.Now().UTC().Add(time.Second),
	}); err != nil {
		t.Fatalf("project post owner block event: %v", err)
	}
	page = listCommentsThroughAPI(t, postID, viewerID, "", 20)
	if len(page.Items) != 0 || page.Total != 0 {
		t.Fatalf("blocked Post owner must hide the entire Comment page: %+v", page)
	}
}

func TestDeleteComment(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "delete-post-owner")
	created := createCommentThroughAPI(t, postID, "comment-owner", "to be deleted", "")

	deleted := commentAPIRequest(t, http.MethodDelete,
		"/content/posts/"+postID+"/comments/"+created.ID,
		"comment-owner", nil)
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
		"/content/posts/"+postID+"/counters", "viewer", nil)
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
		"/content/posts/"+postID+"/counters", "viewer", nil)
	var counters map[string]any
	decodeCommentResponse(t, counterRecorder, &counters)
	if page.Total != 1 || numberAsInt64(counters["comment"]) != page.Total {
		t.Fatalf("Comment reader/Post projection mismatch: page=%+v counters=%+v", page, counters)
	}

	deleteRecorder := commentAPIRequest(t, http.MethodDelete,
		"/content/posts/"+postID+"/comments/"+created.ID,
		"consistency-commenter", nil)
	if deleteRecorder.Code != http.StatusOK {
		t.Fatalf("delete status=%d body=%s", deleteRecorder.Code, deleteRecorder.Body.String())
	}
	page = listCommentsThroughAPI(t, postID, "viewer", "", 20)
	counterRecorder = commentAPIRequest(t, http.MethodGet,
		"/content/posts/"+postID+"/counters", "viewer", nil)
	decodeCommentResponse(t, counterRecorder, &counters)
	if page.Total != 0 || numberAsInt64(counters["comment"]) != 0 {
		t.Fatalf("Comment deletion projection mismatch: page=%+v counters=%+v", page, counters)
	}
}

func TestPostDeletionTombstonesCommentThreadAndConvergesCount(
	t *testing.T,
) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	const postOwnerID = "comment-tombstone-post-owner"
	postID := createCommentTestPost(t, postOwnerID)
	root := createCommentThroughAPI(
		t,
		postID,
		"comment-tombstone-root-author",
		"root before Post deletion",
		"",
	)
	createCommentThroughAPI(
		t,
		postID,
		"comment-tombstone-reply-author",
		"reply before Post deletion",
		root.ID,
	)
	if err := drainCommentOutboxForHarness(context.Background()); err != nil {
		t.Fatalf("drain Comment count before Post deletion: %v", err)
	}
	assertCommentCounter(t, postID, 2)

	req := httptest.NewRequest(http.MethodDelete, "/content/posts/"+postID, nil)
	req.Header.Set("X-Client-User-Id", postOwnerID)
	ensureIdempotencyHeader(req, "delete-post-with-comment-thread")
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, req)
	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"delete Post with Comment thread status=%d body=%s",
			recorder.Code,
			recorder.Body.String(),
		)
	}
	drainPostOutbox(t)
	if err := drainCommentOutboxForHarness(context.Background()); err != nil {
		t.Fatalf("drain CommentsTombstoned outbox: %v", err)
	}

	comments := requireMongoDB(t).Collection("comments")
	tombstoned, err := comments.CountDocuments(
		context.Background(),
		bson.M{"postId": postID, "status": "tombstoned"},
	)
	if err != nil {
		t.Fatalf("count tombstoned Comments: %v", err)
	}
	active, err := comments.CountDocuments(
		context.Background(),
		bson.M{"postId": postID, "status": "active"},
	)
	if err != nil {
		t.Fatalf("count active Comments after Post deletion: %v", err)
	}
	if tombstoned != 2 || active != 0 {
		t.Fatalf(
			"Post deletion Comment lifecycle drifted: tombstoned=%d active=%d",
			tombstoned,
			active,
		)
	}

	var post struct {
		CommentCount int64 `bson:"commentCount"`
	}
	if err := requireMongoDB(t).Collection("posts").FindOne(
		context.Background(),
		bson.M{"_id": postID},
	).Decode(&post); err != nil {
		t.Fatalf("read deleted Post count projection: %v", err)
	}
	if post.CommentCount != 0 {
		t.Fatalf("deleted Post commentCount=%d, want 0", post.CommentCount)
	}

	events := eventSpy.EventsOfType("CommentsTombstoned")
	if len(events) != 1 ||
		events[0].AggregateID != postID ||
		numberAsInt64(events[0].Payload["tombstonedCount"]) != 2 {
		t.Fatalf("unexpected CommentsTombstoned event: %+v", events)
	}
}

func TestCommentModerationLifecycleApiIntegration(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "moderation-post-owner")
	commentAuthorID := "moderation-comment-author"
	created := createCommentThroughAPI(
		t,
		postID,
		commentAuthorID,
		"real Mongo moderation target",
		"",
	)
	handler := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("content"),
	)(contenhttp.NewContentHandler(
		nil,
		nil,
		nil,
		commentapp.BindFacades(testCommentService),
		reactionapp.BindFacades(testReactionService),
		nil,
		nil,
	).Routes())
	operator := rtauth.Principal{
		Claims: rtauth.Claims{
			Subject:     "comment-moderation-operator",
			Scope:       "ops.case.write",
			Roles:       []string{"operator"},
			Permissions: []string{"content.moderation.decide"},
		},
		Actor: rtoperation.ActorContext{AccountID: "comment-moderation-operator"},
	}

	hide := commentModerationAPIRequest(
		t,
		handler,
		"/internal/content/comments/"+created.ID+":hide",
		`{"reason":"confirmed abuse"}`,
		"comment-moderation-api-hide",
		operator,
	)
	if hide.Code != http.StatusOK {
		t.Fatalf("HideComment status=%d body=%s", hide.Code, hide.Body.String())
	}
	var hidden commentapp.CommentCommandResult
	decodeCommentResponse(t, hide, &hidden)
	if hidden.Status != "hidden" || hidden.Version != created.Version+1 || hidden.Replayed {
		t.Fatalf("unexpected HideComment result: %+v", hidden)
	}
	replay := commentModerationAPIRequest(
		t,
		handler,
		"/internal/content/comments/"+created.ID+":hide",
		`{"reason":"confirmed abuse"}`,
		"comment-moderation-api-hide",
		operator,
	)
	if replay.Code != http.StatusOK {
		t.Fatalf("replay HideComment status=%d body=%s", replay.Code, replay.Body.String())
	}
	var replayed commentapp.CommentCommandResult
	decodeCommentResponse(t, replay, &replayed)
	if !replayed.Replayed || replayed.Version != hidden.Version {
		t.Fatalf("HideComment receipt replay drifted: %+v", replayed)
	}
	if err := drainCommentOutboxForHarness(context.Background()); err != nil {
		t.Fatalf("drain HideComment outbox: %v", err)
	}
	assertPersistedCommentModerationState(
		t,
		created.ID,
		"hidden",
		true,
	)
	hiddenPage := listCommentsThroughAPI(t, postID, "viewer", "", 20)
	if hiddenPage.Total != 0 || len(hiddenPage.Items) != 0 {
		t.Fatalf("hidden Comment leaked into active Mongo page: %+v", hiddenPage)
	}
	assertCommentCounter(t, postID, 0)
	authorRecorder := commentAPIRequest(
		t,
		http.MethodGet,
		"/content/users/me/comments?limit=20",
		commentAuthorID,
		nil,
	)
	if authorRecorder.Code != http.StatusOK {
		t.Fatalf(
			"hidden author Comment page status=%d body=%s",
			authorRecorder.Code,
			authorRecorder.Body.String(),
		)
	}
	var authorPage commentapp.AuthorCommentPageSlice
	decodeCommentResponse(t, authorRecorder, &authorPage)
	if len(authorPage.Items) != 1 ||
		authorPage.Items[0].ID != created.ID ||
		string(authorPage.Items[0].Status) != "hidden" {
		t.Fatalf("author private projection lost hidden Comment: %+v", authorPage)
	}
	events := eventSpy.EventsOfType("CommentModerated")
	if len(events) != 1 ||
		events[0].Payload["operatorId"] != "comment-moderation-operator" ||
		events[0].Payload["action"] != "hide" ||
		events[0].Payload["reason"] != "confirmed abuse" {
		t.Fatalf("unexpected HideComment durable event: %+v", events)
	}

	restore := commentModerationAPIRequest(
		t,
		handler,
		"/internal/content/comments/"+created.ID+":restore",
		`{"reason":"review cleared"}`,
		"comment-moderation-api-restore",
		operator,
	)
	if restore.Code != http.StatusOK {
		t.Fatalf("RestoreComment status=%d body=%s", restore.Code, restore.Body.String())
	}
	var restored commentapp.CommentCommandResult
	decodeCommentResponse(t, restore, &restored)
	if restored.Status != "active" || restored.Version != hidden.Version+1 {
		t.Fatalf("unexpected RestoreComment result: %+v", restored)
	}
	if err := drainCommentOutboxForHarness(context.Background()); err != nil {
		t.Fatalf("drain RestoreComment outbox: %v", err)
	}
	assertPersistedCommentModerationState(
		t,
		created.ID,
		"active",
		false,
	)
	restoredPage := listCommentsThroughAPI(t, postID, "viewer", "", 20)
	if restoredPage.Total != 1 ||
		len(restoredPage.Items) != 1 ||
		restoredPage.Items[0].ID != created.ID {
		t.Fatalf("restored Comment did not return to active Mongo page: %+v", restoredPage)
	}
	assertCommentCounter(t, postID, 1)
	events = eventSpy.EventsOfType("CommentModerated")
	if len(events) != 2 ||
		events[1].Payload["operatorId"] != "comment-moderation-operator" ||
		events[1].Payload["action"] != "restore" ||
		events[1].Payload["reason"] != "review cleared" {
		t.Fatalf("unexpected RestoreComment durable event: %+v", events)
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
		"/content/comments/"+comment.ID+"/reaction",
		"viewer", map[string]any{"viewerReaction": "like"})
	if unsupported.Code != http.StatusBadRequest {
		t.Fatalf("unsupported reaction alias must be rejected, status=%d body=%s", unsupported.Code, unsupported.Body.String())
	}
	missing := commentAPIRequest(t, http.MethodPost,
		"/content/comments/missing-comment/reaction",
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
		"/content/users/me/comments?limit=20", "comment-page-author", nil)
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
		"/content/users/me/received-comments?limit=20", "received-post-owner", nil)
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
	created := submitPublishedPostWithAuthor(t, ownerID,
		`{"contentType":"image","title":"Comment object target"}`)
	postID, _ := created["postId"].(string)
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
		"/content/posts/"+postID+"/comments", actorID,
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
	path := fmt.Sprintf("/content/posts/%s/comments?limit=%d", postID, limit)
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
		"/content/comments/"+commentID+"/reaction", actorID,
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
	request.Header.Set("X-Client-Persona-Id", actorID)
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

func commentModerationAPIRequest(
	t *testing.T,
	handler http.Handler,
	path string,
	body string,
	idempotencyKey string,
	principal rtauth.Principal,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodPost,
		path,
		bytes.NewBufferString(body),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertPersistedCommentModerationState(
	t *testing.T,
	commentID string,
	wantStatus string,
	wantHiddenAt bool,
) {
	t.Helper()
	var document struct {
		Status   string `bson:"status"`
		HiddenAt any    `bson:"hiddenAt,omitempty"`
	}
	if err := mongoDB.Collection("comments").FindOne(
		context.Background(),
		bson.M{"_id": commentID},
	).Decode(&document); err != nil {
		t.Fatalf("load persisted Comment moderation state: %v", err)
	}
	if document.Status != wantStatus || (document.HiddenAt != nil) != wantHiddenAt {
		t.Fatalf(
			"persisted Comment state=%+v want status=%q hiddenAt=%v",
			document,
			wantStatus,
			wantHiddenAt,
		)
	}
}

func assertCommentCounter(t *testing.T, postID string, want int64) {
	t.Helper()
	recorder := commentAPIRequest(
		t,
		http.MethodGet,
		"/content/posts/"+postID+"/counters",
		"viewer",
		nil,
	)
	if recorder.Code != http.StatusOK {
		t.Fatalf("get counters status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var counters map[string]any
	decodeCommentResponse(t, recorder, &counters)
	if got := numberAsInt64(counters["comment"]); got != want {
		t.Fatalf("Comment count projection=%d want=%d payload=%+v", got, want, counters)
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
