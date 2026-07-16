package http

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
	"quwoquan_service/services/content-service/internal/testsupport"
	commenttestsupport "quwoquan_service/services/content-service/internal/testsupport/comment"
)

func TestCommentHTTPUsesTypedObjectFacadesAndVersionCAS(t *testing.T) {
	t.Parallel()
	commentStore := commenttestsupport.NewStore()
	commentStore.SeedPost("post-comment-http", "post-owner")
	reactionStore := testsupport.NewReactionStore()
	commentService := commentapp.BindFacades(commentapp.NewCommentService(commentapp.BindDataPorts(
		commentStore,
		commentStore,
		reactionStore,
	)))
	reactionService := reactionapp.BindFacades(reactionapp.NewService(reactionapp.BindDataPorts(reactionStore, reactionStore)))
	handler := NewContentHandler(nil, nil, nil, commentService, reactionService, nil, nil).Routes()

	created := performCommentRequest(t, handler, http.MethodPost,
		"/v1/content/posts/post-comment-http/comments",
		map[string]any{"content": "typed comment", "mentions": []any{}},
		"comment-http-create", "comment-author")
	if created.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", created.Code, created.Body.String())
	}
	var createResult commentapp.CommentCommandResult
	if err := json.Unmarshal(created.Body.Bytes(), &createResult); err != nil {
		t.Fatal(err)
	}
	if createResult.ID == "" || createResult.Version != 1 {
		t.Fatalf("create result=%+v", createResult)
	}
	replied := performCommentRequest(t, handler, http.MethodPost,
		"/v1/content/posts/post-comment-http/comments",
		map[string]any{
			"content":            "typed reply",
			"replyToCommentId":   createResult.ID,
			"attachmentMediaIds": []any{},
			"mentions":           []any{},
		},
		"comment-http-reply", "reply-author")
	if replied.Code != http.StatusCreated {
		t.Fatalf("reply status=%d body=%s", replied.Code, replied.Body.String())
	}

	listed := performCommentRequest(t, handler, http.MethodGet,
		"/v1/content/posts/post-comment-http/comments", nil, "", "comment-author")
	if listed.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listed.Code, listed.Body.String())
	}
	var page commentapp.CommentPageSlice
	if err := json.Unmarshal(listed.Body.Bytes(), &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Items) != 1 || page.Items[0].Version != createResult.Version {
		t.Fatalf("list page=%+v", page)
	}
	item := page.Items[0]
	if !item.IsAuthor || !item.CanDelete || !item.CanReply || item.CanReport || item.CanPin {
		t.Fatalf("author capabilities must be derived by the service: %+v", item)
	}
	if item.ReplyCount != 1 || len(item.ReplyPreview) != 1 ||
		item.ReplyPreview[0].ID == "" || item.ReplyPreview[0].ParentCommentID != createResult.ID {
		t.Fatalf("reply summary must be a typed projection: %+v", item)
	}

	replies := performCommentRequest(t, handler, http.MethodGet,
		"/v1/content/posts/post-comment-http/comments/"+createResult.ID+"/replies",
		nil, "", "comment-author")
	if replies.Code != http.StatusOK {
		t.Fatalf("reply page status=%d body=%s", replies.Code, replies.Body.String())
	}
	var replyPage commentapp.ReplyPageSlice
	if err := json.Unmarshal(replies.Body.Bytes(), &replyPage); err != nil {
		t.Fatal(err)
	}
	if replyPage.Total != 1 || len(replyPage.Items) != 1 ||
		replyPage.Items[0].ParentCommentID != createResult.ID {
		t.Fatalf("reply page=%+v", replyPage)
	}

	reacted := performCommentRequest(t, handler, http.MethodPost,
		"/v1/content/comments/"+createResult.ID+"/reaction",
		map[string]any{"reaction": "dislike"}, "comment-http-react", "comment-viewer")
	if reacted.Code != http.StatusOK {
		t.Fatalf("react status=%d body=%s", reacted.Code, reacted.Body.String())
	}
	var reactionResult reactionapp.CommentReactionCommandResult
	if err := json.Unmarshal(reacted.Body.Bytes(), &reactionResult); err != nil {
		t.Fatal(err)
	}
	if reactionResult.DislikeCount != 1 || reactionResult.LikeCount != 0 {
		t.Fatalf("reaction=%+v", reactionResult)
	}

	viewerList := performCommentRequest(t, handler, http.MethodGet,
		"/v1/content/posts/post-comment-http/comments", nil, "", "comment-viewer")
	if viewerList.Code != http.StatusOK {
		t.Fatalf("viewer list status=%d body=%s", viewerList.Code, viewerList.Body.String())
	}
	var viewerPage commentapp.CommentPageSlice
	if err := json.Unmarshal(viewerList.Body.Bytes(), &viewerPage); err != nil {
		t.Fatal(err)
	}
	if len(viewerPage.Items) != 1 || viewerPage.Items[0].ViewerReaction != "dislike" ||
		viewerPage.Items[0].LikeCount != 0 || viewerPage.Items[0].DislikeCount != 1 ||
		viewerPage.Items[0].IsAuthor || viewerPage.Items[0].CanDelete ||
		!viewerPage.Items[0].CanReply || !viewerPage.Items[0].CanReport {
		t.Fatalf("viewer reaction/capabilities projection=%+v", viewerPage)
	}

	ownerList := performCommentRequest(t, handler, http.MethodGet,
		"/v1/content/posts/post-comment-http/comments", nil, "", "post-owner")
	if ownerList.Code != http.StatusOK {
		t.Fatalf("post-owner list status=%d body=%s", ownerList.Code, ownerList.Body.String())
	}
	var ownerPage commentapp.CommentPageSlice
	if err := json.Unmarshal(ownerList.Body.Bytes(), &ownerPage); err != nil {
		t.Fatal(err)
	}
	if len(ownerPage.Items) != 1 || !ownerPage.Items[0].CanPin {
		t.Fatalf("post owner must receive canPin capability: %+v", ownerPage)
	}

	staleDelete := performCommentRequest(t, handler, http.MethodDelete,
		"/v1/content/posts/post-comment-http/comments/"+createResult.ID,
		map[string]any{"version": 2}, "comment-http-delete-stale", "comment-author")
	if staleDelete.Code != http.StatusConflict {
		t.Fatalf("stale delete status=%d body=%s", staleDelete.Code, staleDelete.Body.String())
	}

	deleted := performCommentRequest(t, handler, http.MethodDelete,
		"/v1/content/posts/post-comment-http/comments/"+createResult.ID,
		map[string]any{"version": createResult.Version}, "comment-http-delete", "comment-author")
	if deleted.Code != http.StatusOK {
		t.Fatalf("delete status=%d body=%s", deleted.Code, deleted.Body.String())
	}
}

func performCommentRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body map[string]any,
	idempotencyKey string,
	personaID string,
) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	if body != nil {
		payload, _ = json.Marshal(body)
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	request = request.WithContext(rtauth.WithPrincipal(context.Background(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
