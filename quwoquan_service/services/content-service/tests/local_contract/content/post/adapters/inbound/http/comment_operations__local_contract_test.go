package http_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	"testing"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commenttestsupport "quwoquan_service/services/content-service/internal/content/comment/infrastructure/testsupport"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
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
		commentStore,
		commentStore,
	)))
	reactionService := reactionapp.BindFacades(reactionapp.NewService(reactionapp.BindDataPorts(reactionStore, reactionStore)))
	handler := NewContentHandler(nil, nil, nil, commentService, reactionService, nil, nil).Routes()

	created := performCommentRequest(t, handler, http.MethodPost,
		"/content/posts/post-comment-http/comments",
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
		"/content/posts/post-comment-http/comments",
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
		"/content/posts/post-comment-http/comments", nil, "", "comment-author")
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
		"/content/posts/post-comment-http/comments/"+createResult.ID+"/replies",
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
		"/content/comments/"+createResult.ID+"/reaction",
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
		"/content/posts/post-comment-http/comments", nil, "", "comment-viewer")
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
		"/content/posts/post-comment-http/comments", nil, "", "post-owner")
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

	deleted := performCommentRequest(t, handler, http.MethodDelete,
		"/content/posts/post-comment-http/comments/"+createResult.ID,
		nil, "comment-http-delete", "comment-author")
	if deleted.Code != http.StatusOK {
		t.Fatalf("delete status=%d body=%s", deleted.Code, deleted.Body.String())
	}
}

func TestCommentModerationHTTPRequiresGeneratedOperatorAuthorization(t *testing.T) {
	commentStore := commenttestsupport.NewStore()
	commentStore.SeedPost("post-comment-moderation-http", "post-owner")
	reactionStore := testsupport.NewReactionStore()
	commentService := commentapp.BindFacades(commentapp.NewCommentService(commentapp.BindDataPorts(
		commentStore,
		commentStore,
		reactionStore,
		commentStore,
		commentStore,
	)))
	baseHandler := NewContentHandler(
		nil,
		nil,
		nil,
		commentService,
		reactionapp.BindFacades(reactionapp.NewService(
			reactionapp.BindDataPorts(reactionStore, reactionStore),
		)),
		nil,
		nil,
	).Routes()
	createdRecorder := performCommentRequest(
		t,
		baseHandler,
		http.MethodPost,
		"/content/posts/post-comment-moderation-http/comments",
		map[string]any{"content": "moderation target", "mentions": []any{}},
		"comment-moderation-http-create",
		"comment-author",
	)
	if createdRecorder.Code != http.StatusCreated {
		t.Fatalf(
			"create moderation target status=%d body=%s",
			createdRecorder.Code,
			createdRecorder.Body.String(),
		)
	}
	var created commentapp.CommentCommandResult
	if err := json.Unmarshal(createdRecorder.Body.Bytes(), &created); err != nil {
		t.Fatal(err)
	}
	handler := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("content"),
	)(baseHandler)
	path := "/internal/content/comments/" + created.ID + ":hide"

	forged := httptest.NewRequest(
		http.MethodPost,
		path,
		bytes.NewBufferString(`{"reason":"forged headers"}`),
	)
	forged.Header.Set("Idempotency-Key", "comment-moderation-forged")
	forged.Header.Set("X-Client-Role", "operator")
	forged.Header.Set("X-Client-Scope", "ops.case.write")
	forged.Header.Set("X-Client-Permission", "content.moderation.decide")
	forgedRecorder := httptest.NewRecorder()
	handler.ServeHTTP(forgedRecorder, forged)
	if forgedRecorder.Code != http.StatusUnauthorized {
		t.Fatalf(
			"forged operator headers status=%d want=%d body=%s",
			forgedRecorder.Code,
			http.StatusUnauthorized,
			forgedRecorder.Body.String(),
		)
	}

	for _, testCase := range []struct {
		name       string
		claims     rtauth.Claims
		wantStatus int
	}{
		{
			name: "regular account",
			claims: rtauth.Claims{
				Subject:     "regular-account",
				Scope:       "ops.case.write",
				Permissions: []string{"content.moderation.decide"},
			},
			wantStatus: http.StatusForbidden,
		},
		{
			name: "operator missing scope",
			claims: rtauth.Claims{
				Subject:     "operator-missing-scope",
				Roles:       []string{"operator"},
				Permissions: []string{"content.moderation.decide"},
			},
			wantStatus: http.StatusForbidden,
		},
		{
			name: "operator missing permission",
			claims: rtauth.Claims{
				Subject: "operator-missing-permission",
				Scope:   "ops.case.write",
				Roles:   []string{"operator"},
			},
			wantStatus: http.StatusForbidden,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodPost,
				path,
				bytes.NewBufferString(`{"reason":"not authorized"}`),
			)
			request.Header.Set("Idempotency-Key", "comment-moderation-"+testCase.name)
			request = request.WithContext(rtauth.WithPrincipal(
				request.Context(),
				rtauth.Principal{
					Claims: testCase.claims,
					Actor: operation.ActorContext{
						AccountID: testCase.claims.Subject,
					},
				},
			))
			recorder := httptest.NewRecorder()
			handler.ServeHTTP(recorder, request)
			if recorder.Code != testCase.wantStatus {
				t.Fatalf(
					"status=%d want=%d body=%s",
					recorder.Code,
					testCase.wantStatus,
					recorder.Body.String(),
				)
			}
		})
	}

	operator := rtauth.Principal{
		Claims: rtauth.Claims{
			Subject:     "comment-moderation-operator",
			Scope:       "ops.case.write",
			Roles:       []string{"operator"},
			Permissions: []string{"content.moderation.decide"},
		},
		Actor: operation.ActorContext{AccountID: "comment-moderation-operator"},
	}
	firstHide := performCommentOperatorRequest(
		t,
		handler,
		http.MethodPost,
		path,
		`{"reason":"confirmed abuse"}`,
		"comment-moderation-hide",
		operator,
	)
	if firstHide.Code != http.StatusOK {
		t.Fatalf("HideComment status=%d body=%s", firstHide.Code, firstHide.Body.String())
	}
	var hidden commentapp.CommentCommandResult
	if err := json.Unmarshal(firstHide.Body.Bytes(), &hidden); err != nil {
		t.Fatal(err)
	}
	if hidden.Status != "hidden" || hidden.Version != created.Version+1 || hidden.Replayed {
		t.Fatalf("unexpected HideComment result: %+v", hidden)
	}
	replayedHide := performCommentOperatorRequest(
		t,
		handler,
		http.MethodPost,
		path,
		`{"reason":"confirmed abuse"}`,
		"comment-moderation-hide",
		operator,
	)
	if replayedHide.Code != http.StatusOK {
		t.Fatalf(
			"replay HideComment status=%d body=%s",
			replayedHide.Code,
			replayedHide.Body.String(),
		)
	}
	var replayed commentapp.CommentCommandResult
	if err := json.Unmarshal(replayedHide.Body.Bytes(), &replayed); err != nil {
		t.Fatal(err)
	}
	if !replayed.Replayed || replayed.Version != hidden.Version {
		t.Fatalf("HideComment HTTP replay drifted: %+v", replayed)
	}

	restoredRecorder := performCommentOperatorRequest(
		t,
		handler,
		http.MethodPost,
		"/internal/content/comments/"+created.ID+":restore",
		`{"reason":"review cleared"}`,
		"comment-moderation-restore",
		operator,
	)
	if restoredRecorder.Code != http.StatusOK {
		t.Fatalf(
			"RestoreComment status=%d body=%s",
			restoredRecorder.Code,
			restoredRecorder.Body.String(),
		)
	}
	var restored commentapp.CommentCommandResult
	if err := json.Unmarshal(restoredRecorder.Body.Bytes(), &restored); err != nil {
		t.Fatal(err)
	}
	if restored.Status != "active" || restored.Version != hidden.Version+1 {
		t.Fatalf("unexpected RestoreComment result: %+v", restored)
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

func performCommentOperatorRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body string,
	idempotencyKey string,
	principal rtauth.Principal,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, bytes.NewBufferString(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
