package comment_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/commandmeta"
	referencefence "quwoquan_service/runtime/media/referencefence"
	"quwoquan_service/runtime/operation"
	commenthttp "quwoquan_service/services/content-service/internal/content/comment/adapters/inbound/http"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentpersistence "quwoquan_service/services/content-service/internal/content/comment/infrastructure/persistence"
	commenttestsupport "quwoquan_service/services/content-service/internal/content/comment/infrastructure/testsupport"
	reactiontestsupport "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

type noAttachmentReferenceFence struct{}

func (noAttachmentReferenceFence) AllowReferences(
	context.Context,
	[]referencefence.Reference,
) error {
	return nil
}

func TestCreateCommentHTTPCommitsAggregateReceiptAndOutboxInRealMongoTransaction(t *testing.T) {
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
	handler := commenthttp.NewHandler(commentapp.BindFacades(service))

	request := httptest.NewRequest(
		http.MethodPost,
		"/content/posts/post-comment/comments",
		strings.NewReader(`{"content":"transactional Comment","mentions":[]}`),
	)
	request.Header.Set("Content-Type", "application/json")
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
	request = request.WithContext(commandmeta.WithIdempotencyKey(
		request.Context(),
		"comment-create-once",
	))
	recorder := httptest.NewRecorder()

	handler.CreateComment(recorder, request, "post-comment")
	if recorder.Code != http.StatusCreated {
		t.Fatalf("CreateComment status=%d body=%s", recorder.Code, recorder.Body.String())
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
}
