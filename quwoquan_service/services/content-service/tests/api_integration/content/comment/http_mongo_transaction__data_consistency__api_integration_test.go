// readiness_case: create-comment-api
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-015
// readiness_case: consume-comment-lifecycle-api
// readiness_case: delete-comment-api
// readiness_case: pin-comment-api
// readiness_case: unpin-comment-api
// readiness_case: bind-media-assets-to-comment-api
// readiness_case: list-comments-api
// readiness_case: list-comment-replies-api
// readiness_case: list-comments-by-author-api
// readiness_case: list-comments-for-post-author-api
// readiness_case: hide-comment-api
// readiness_case: restore-comment-api
package comment_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	referencefence "quwoquan_service/runtime/media/referencefence"
	"quwoquan_service/runtime/operation"
	commenthttp "quwoquan_service/services/content-service/internal/content/comment/adapters/inbound/http"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	commentpersistence "quwoquan_service/services/content-service/internal/content/comment/infrastructure/persistence"
	commenttestsupport "quwoquan_service/services/content-service/internal/content/comment/infrastructure/testsupport"
	reactionpersistence "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
	contenthttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	reactiontestsupport "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

type noAttachmentReferenceFence struct{}

func (noAttachmentReferenceFence) AllowReferences(
	context.Context,
	[]referencefence.Reference,
) error {
	return nil
}

func TestCommentHTTPCommitsAggregateReceiptOutboxAndEventLogInRealMongoTransaction(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "comment_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	if _, err := runtime.Database.Collection("posts").InsertOne(context.Background(), bson.M{
		"_id":      "post-comment",
		"authorId": "post-owner",
		"status":   "published",
	}); err != nil {
		t.Fatalf("seed authoritative Post relation: %v", err)
	}

	store := commentpersistence.NewMongoCommentDataAdapter(
		runtime.Database,
		noAttachmentReferenceFence{},
	)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure Comment indexes: %v", err)
	}
	auxiliary := commenttestsupport.NewStore()
	reactions := reactiontestsupport.NewReactionStore()
	service := commentapp.NewCommentService(commentapp.BindDataPorts(
		store,
		auxiliary,
		reactions,
		auxiliary,
		auxiliary,
	))
	handler := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("content"),
	)(contenthttp.NewContentHandler(
		nil,
		nil,
		nil,
		commenthttp.NewHandler(commentapp.BindFacades(service)),
		nil,
		nil,
		nil,
	).Routes())

	request := httptest.NewRequest(
		http.MethodPost,
		"/content/posts/post-comment/comments",
		strings.NewReader(`{"content":"transactional Comment","mentions":[]}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "comment-create-once")
	request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
		OperationID:    "content.comment.CreateComment",
		RequestID:      "request-comment-create",
		TraceID:        "trace-comment-create",
		IdempotencyKey: "comment-create-once",
		Actor: operation.ActorContext{
			AccountID: "account-comment-author",
			PersonaID: "comment-author",
		},
	}))
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{
			AccountID: "account-comment-author",
			PersonaID: "comment-author",
		},
	}))
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("CreateComment status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var created commentapp.CommentCommandResult
	if err := json.Unmarshal(recorder.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode CreateComment response: %v", err)
	}
	if created.ID == "" || created.Version != 1 {
		t.Fatalf("CreateComment result=%+v", created)
	}
	for _, collection := range []string{
		"comments",
		"comment_command_receipts",
		"comment_outbox",
	} {
		count, countErr := runtime.Database.Collection(collection).CountDocuments(
			context.Background(),
			bson.M{},
		)
		if countErr != nil {
			t.Fatalf("count %s: %v", collection, countErr)
		}
		if count != 1 {
			t.Fatalf("%s count=%d want=1", collection, count)
		}
	}

	persona := func(personaID string) rtauth.Principal {
		return rtauth.Principal{Actor: operation.ActorContext{
			AccountID: "account-" + personaID,
			PersonaID: personaID,
		}}
	}
	replied := performMongoCommentRequest(
		t,
		handler,
		http.MethodPost,
		"/content/posts/post-comment/comments",
		`{"content":"transactional reply","replyToCommentId":"`+created.ID+`","mentions":[]}`,
		"comment-reply-once",
		persona("reply-author"),
	)
	if replied.Code != http.StatusCreated {
		t.Fatalf("CreateComment reply status=%d body=%s", replied.Code, replied.Body.String())
	}

	listed := performMongoCommentRequest(
		t, handler, http.MethodGet, "/content/posts/post-comment/comments", "", "", persona("comment-author"),
	)
	if listed.Code != http.StatusOK {
		t.Fatalf("ListComments status=%d body=%s", listed.Code, listed.Body.String())
	}
	var page commentapp.CommentPageSlice
	if err := json.Unmarshal(listed.Body.Bytes(), &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Items) != 1 || page.Items[0].ID != created.ID || page.Items[0].ReplyCount != 1 {
		t.Fatalf("ListComments page=%+v", page)
	}

	replies := performMongoCommentRequest(
		t,
		handler,
		http.MethodGet,
		"/content/posts/post-comment/comments/"+created.ID+"/replies",
		"",
		"",
		persona("comment-author"),
	)
	if replies.Code != http.StatusOK {
		t.Fatalf("ListCommentReplies status=%d body=%s", replies.Code, replies.Body.String())
	}
	var replyPage commentapp.ReplyPageSlice
	if err := json.Unmarshal(replies.Body.Bytes(), &replyPage); err != nil {
		t.Fatal(err)
	}
	if len(replyPage.Items) != 1 || replyPage.Items[0].ParentCommentID != created.ID {
		t.Fatalf("ListCommentReplies page=%+v", replyPage)
	}

	pin := performMongoCommentRequest(
		t,
		handler,
		http.MethodPost,
		"/content/posts/post-comment/comments/"+created.ID+"/pin",
		"",
		"comment-pin-once",
		persona("post-owner"),
	)
	if pin.Code != http.StatusOK {
		t.Fatalf("PinComment status=%d body=%s", pin.Code, pin.Body.String())
	}
	unpin := performMongoCommentRequest(
		t,
		handler,
		http.MethodDelete,
		"/content/posts/post-comment/comments/"+created.ID+"/pin",
		"",
		"comment-unpin-once",
		persona("post-owner"),
	)
	if unpin.Code != http.StatusOK {
		t.Fatalf("UnpinComment status=%d body=%s", unpin.Code, unpin.Body.String())
	}

	bound := performMongoCommentRequest(
		t,
		handler,
		http.MethodPost,
		"/content/comments/"+created.ID+"/media:bind",
		`{"attachmentMediaIds":["media-comment-transaction"]}`,
		"comment-bind-once",
		persona("comment-author"),
	)
	if bound.Code != http.StatusOK {
		t.Fatalf("BindMediaAssetsToComment status=%d body=%s", bound.Code, bound.Body.String())
	}
	eventLogCount, err := runtime.Database.Collection("comment_event_log").CountDocuments(
		context.Background(),
		bson.M{"eventType": "CommentAttachmentsBound", "aggregateId": created.ID},
	)
	if err != nil {
		t.Fatalf("count CommentAttachmentsBound event log: %v", err)
	}
	if eventLogCount != 1 {
		t.Fatalf("CommentAttachmentsBound event log count=%d want=1", eventLogCount)
	}
	misroutedOutboxCount, err := runtime.Database.Collection("comment_outbox").CountDocuments(
		context.Background(),
		bson.M{"eventType": "CommentAttachmentsBound", "aggregateId": created.ID},
	)
	if err != nil {
		t.Fatalf("count misrouted CommentAttachmentsBound outbox facts: %v", err)
	}
	if misroutedOutboxCount != 0 {
		t.Fatalf("CommentAttachmentsBound must not be relayed from outbox: count=%d", misroutedOutboxCount)
	}

	authored := performMongoCommentRequest(
		t, handler, http.MethodGet, "/content/users/me/comments", "", "", persona("comment-author"),
	)
	if authored.Code != http.StatusOK {
		t.Fatalf("ListCommentsByAuthor status=%d body=%s", authored.Code, authored.Body.String())
	}
	var authoredPage commentapp.AuthorCommentPageSlice
	if err := json.Unmarshal(authored.Body.Bytes(), &authoredPage); err != nil {
		t.Fatal(err)
	}
	if len(authoredPage.Items) != 1 || authoredPage.Items[0].ID != created.ID ||
		len(authoredPage.Items[0].AttachmentMediaIDs) != 1 {
		t.Fatalf("ListCommentsByAuthor page=%+v", authoredPage)
	}

	received := performMongoCommentRequest(
		t, handler, http.MethodGet, "/content/users/me/received-comments", "", "", persona("post-owner"),
	)
	if received.Code != http.StatusOK {
		t.Fatalf("ListCommentsForPostAuthor status=%d body=%s", received.Code, received.Body.String())
	}
	var receivedPage commentapp.ReceivedCommentPageSlice
	if err := json.Unmarshal(received.Body.Bytes(), &receivedPage); err != nil {
		t.Fatal(err)
	}
	if len(receivedPage.Items) != 2 || receivedPage.Total != 2 {
		t.Fatalf("ListCommentsForPostAuthor page=%+v", receivedPage)
	}

	operator := rtauth.Principal{
		Claims: rtauth.Claims{
			Subject:     "comment-operator",
			Scope:       "ops.case.write",
			Roles:       []string{"operator"},
			Permissions: []string{"content.moderation.decide"},
		},
		Actor: operation.ActorContext{AccountID: "comment-operator"},
	}
	hidden := performMongoCommentRequest(
		t,
		handler,
		http.MethodPost,
		"/internal/content/comments/"+created.ID+":hide",
		`{"reason":"confirmed abuse"}`,
		"comment-hide-once",
		operator,
	)
	if hidden.Code != http.StatusOK {
		t.Fatalf("HideComment status=%d body=%s", hidden.Code, hidden.Body.String())
	}
	restored := performMongoCommentRequest(
		t,
		handler,
		http.MethodPost,
		"/internal/content/comments/"+created.ID+":restore",
		`{"reason":"review cleared"}`,
		"comment-restore-once",
		operator,
	)
	if restored.Code != http.StatusOK {
		t.Fatalf("RestoreComment status=%d body=%s", restored.Code, restored.Body.String())
	}

	deleted := performMongoCommentRequest(
		t,
		handler,
		http.MethodDelete,
		"/content/posts/post-comment/comments/"+created.ID,
		"",
		"comment-delete-once",
		persona("comment-author"),
	)
	if deleted.Code != http.StatusOK {
		t.Fatalf("DeleteComment status=%d body=%s", deleted.Code, deleted.Body.String())
	}
}

func performMongoCommentRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body string,
	idempotencyKey string,
	principal rtauth.Principal,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	if body != "" {
		request.Header.Set("Content-Type", "application/json")
	}
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func TestCommentLifecycleConsumerProjectsHotScoreIntoRealMongo(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "comment_lifecycle_consumer")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	commentStore := commentpersistence.NewMongoCommentDataAdapter(
		runtime.Database,
		noAttachmentReferenceFence{},
	)
	if err := commentStore.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure Comment indexes: %v", err)
	}
	reactionStore := reactionpersistence.NewMongoContentReactionStore(runtime.Database)
	if err := reactionStore.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure ContentReaction indexes: %v", err)
	}
	now := time.Date(2030, time.January, 2, 3, 4, 5, 0, time.UTC)
	if _, err := runtime.Database.Collection("comments").InsertMany(context.Background(), []any{
		bson.M{"_id": "comment-parent", "postId": "post-comment", "authorId": "parent-author", "status": "active", "createdAt": now, "hotScore": int64(0)},
		bson.M{"_id": "comment-reply", "postId": "post-comment", "authorId": "reply-author", "parentCommentId": "comment-parent", "status": "active", "createdAt": now.Add(time.Second)},
	}); err != nil {
		t.Fatalf("seed Comment projection source: %v", err)
	}
	projector := commentapp.NewCommentHotScoreProjectionHandler(
		commentStore,
		reactionStore,
		commentStore,
	)
	if err := projector.Publish(context.Background(), commentports.OutboxEvent{
		EventID: "comment-reply:1", EventType: "CommentCreated",
		AggregateID: "comment-reply", AggregateVersion: 1,
		Payload: []byte(`{"parentCommentId":"comment-parent"}`), OccurredAt: now.Add(time.Second),
	}); err != nil {
		t.Fatalf("project CommentCreated hot score: %v", err)
	}
	var projected struct {
		HotScore int64 `bson:"hotScore"`
	}
	if err := runtime.Database.Collection("comments").FindOne(
		context.Background(),
		bson.M{"_id": "comment-parent"},
	).Decode(&projected); err != nil {
		t.Fatalf("read projected Comment: %v", err)
	}
	if projected.HotScore != 2 {
		t.Fatalf("projected hotScore=%d, want 2", projected.HotScore)
	}
}
