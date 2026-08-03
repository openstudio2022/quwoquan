package content_reaction_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	reactionhttp "quwoquan_service/services/content-service/internal/content/content_reaction/adapters/inbound/http"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionpersistence "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
	"quwoquan_service/runtime/commandmeta"
)

type liveTargetReader struct{}

func (liveTargetReader) FindReactionTarget(
	context.Context,
	reactiondomain.Target,
) (reactionapp.ReactionTargetSlice, error) {
	return reactionapp.ReactionTargetSlice{Exists: true, AuthorID: "post-owner"}, nil
}

func TestLikePostHTTPCommitsAggregateReceiptAndOutboxInRealMongoTransaction(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "content_reaction_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	store := reactionpersistence.NewMongoContentReactionStore(runtime.Database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure ContentReaction indexes: %v", err)
	}
	handler := reactionhttp.NewHandler(reactionapp.BindFacades(reactionapp.NewService(
		reactionapp.BindDataPorts(store, liveTargetReader{}),
	)))

	request := httptest.NewRequest(http.MethodPost, "/content/posts/post-reaction/like", nil)
	request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
		OperationID:    "content.content_reaction.LikePost",
		RequestID:      "request-reaction-like",
		TraceID:        "trace-reaction-like",
		IdempotencyKey: "reaction-like-once",
		Actor: operation.ActorContext{
			AccountID: "account-reactor",
			PersonaID: "persona-reactor",
		},
	}))
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{
			AccountID: "account-reactor",
			PersonaID: "persona-reactor",
		},
	}))
	request = request.WithContext(commandmeta.WithIdempotencyKey(
		request.Context(),
		"reaction-like-once",
	))
	recorder := httptest.NewRecorder()

	handler.LikePost(recorder, request, "post-reaction")
	if recorder.Code != http.StatusOK {
		t.Fatalf("LikePost status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	for _, collection := range []string{
		"content_reaction_aggregates",
		"content_reaction_command_receipts",
		"content_reaction_outbox",
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

	replay := httptest.NewRecorder()
	handler.LikePost(replay, request, "post-reaction")
	if replay.Code != http.StatusOK {
		t.Fatalf("LikePost replay status=%d body=%s", replay.Code, replay.Body.String())
	}
	outboxCount, err := runtime.Database.Collection("content_reaction_outbox").CountDocuments(
		context.Background(),
		bson.M{},
	)
	if err != nil || outboxCount != 1 {
		t.Fatalf("replay outbox count=%d err=%v", outboxCount, err)
	}
}
