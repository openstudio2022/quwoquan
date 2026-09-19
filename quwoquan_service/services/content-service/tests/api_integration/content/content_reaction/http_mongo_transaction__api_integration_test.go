// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-006
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-006.t1
// readiness_case: like-post-api
// readiness_case: unlike-post-api
// readiness_case: react-to-comment-api
// readiness_case: get-content-reaction-state-api
package content_reaction_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/commandmeta"
	"quwoquan_service/runtime/operation"
	reactionhttp "quwoquan_service/services/content-service/internal/content/content_reaction/adapters/inbound/http"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionpersistence "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
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
	signer, err := reactionpersistence.NewReactionMutationBasisSigner("content-service.test", "test", []reactionpersistence.ReactionMutationBasisKey{{ID: "test", Material: []byte(strings.Repeat("k", 32))}})
	if err != nil {
		t.Fatal(err)
	}
	service := reactionapp.NewService(reactionapp.BindDataPorts(store, liveTargetReader{}), signer)
	handler := reactionhttp.NewHandler(reactionapp.BindFacades(service))

	actor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-reactor")
	postIdentity, _ := reactiondomain.NewPostIdentity("post-reaction", actor)
	postBasis, err := service.GetContentReactionMutationBasis(context.Background(), reactionapp.GetContentReactionMutationBasisQuery{Identity: postIdentity})
	if err != nil {
		t.Fatal(err)
	}
	likeBody := fmt.Sprintf(`{"mutationBasis":%q,"expectedVersion":%d}`, postBasis.MutationBasis, postBasis.ExpectedVersion)
	request := httptest.NewRequest(http.MethodPost, "/content/posts/post-reaction/like", strings.NewReader(likeBody))
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

	replayRequest := httptest.NewRequest(http.MethodPost, "/content/posts/post-reaction/like", strings.NewReader(likeBody)).WithContext(request.Context())
	replay := httptest.NewRecorder()
	handler.LikePost(replay, replayRequest, "post-reaction")
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

	requestFor := func(method, target, key, body string) *http.Request {
		request := httptest.NewRequest(method, target, strings.NewReader(body))
		request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
			OperationID:    "content.content_reaction.readiness",
			RequestID:      "request-" + key,
			TraceID:        "trace-" + key,
			IdempotencyKey: key,
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
		if key != "" {
			request = request.WithContext(commandmeta.WithIdempotencyKey(request.Context(), key))
		}
		return request
	}

	stateRecorder := httptest.NewRecorder()
	handler.GetContentReactionState(
		stateRecorder,
		requestFor(http.MethodGet, "/content/posts/post-reaction/reactions", "", ""),
		"post-reaction",
	)
	if stateRecorder.Code != http.StatusOK ||
		!strings.Contains(stateRecorder.Body.String(), `"liked":true`) {
		t.Fatalf("GetContentReactionState liked status=%d body=%s", stateRecorder.Code, stateRecorder.Body.String())
	}

	postBasis, err = service.GetContentReactionMutationBasis(context.Background(), reactionapp.GetContentReactionMutationBasisQuery{Identity: postIdentity})
	if err != nil {
		t.Fatal(err)
	}
	unlikeBody := fmt.Sprintf(`{"mutationBasis":%q,"expectedVersion":%d}`, postBasis.MutationBasis, postBasis.ExpectedVersion)
	unlikeRecorder := httptest.NewRecorder()
	handler.UnlikePost(
		unlikeRecorder,
		requestFor(http.MethodDelete, "/content/posts/post-reaction/like", "reaction-unlike-once", unlikeBody),
		"post-reaction",
	)
	if unlikeRecorder.Code != http.StatusOK ||
		!strings.Contains(unlikeRecorder.Body.String(), `"liked":false`) {
		t.Fatalf("UnlikePost status=%d body=%s", unlikeRecorder.Code, unlikeRecorder.Body.String())
	}

	clearedStateRecorder := httptest.NewRecorder()
	handler.GetContentReactionState(
		clearedStateRecorder,
		requestFor(http.MethodGet, "/content/posts/post-reaction/reactions", "", ""),
		"post-reaction",
	)
	if clearedStateRecorder.Code != http.StatusOK ||
		!strings.Contains(clearedStateRecorder.Body.String(), `"liked":false`) {
		t.Fatalf("GetContentReactionState cleared status=%d body=%s", clearedStateRecorder.Code, clearedStateRecorder.Body.String())
	}

	commentActor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-reactor")
	commentIdentity, _ := reactiondomain.NewCommentIdentity("comment-reaction", commentActor)
	commentBasis, err := service.GetContentReactionMutationBasis(context.Background(), reactionapp.GetContentReactionMutationBasisQuery{Identity: commentIdentity})
	if err != nil {
		t.Fatal(err)
	}
	commentBody := fmt.Sprintf(`{"reaction":"like","mutationBasis":%q,"expectedVersion":%d}`, commentBasis.MutationBasis, commentBasis.ExpectedVersion)
	commentRecorder := httptest.NewRecorder()
	handler.ReactToComment(
		commentRecorder,
		requestFor(
			http.MethodPost,
			"/content/comments/comment-reaction/reaction",
			"comment-reaction-like-once",
			commentBody,
		),
		"comment-reaction",
	)
	if commentRecorder.Code != http.StatusOK ||
		!strings.Contains(commentRecorder.Body.String(), `"reaction":"like"`) ||
		!strings.Contains(commentRecorder.Body.String(), `"likeCount":1`) {
		t.Fatalf("ReactToComment status=%d body=%s", commentRecorder.Code, commentRecorder.Body.String())
	}

	for collection, want := range map[string]int64{
		"content_reaction_aggregates":       2,
		"content_reaction_command_receipts": 3,
		"content_reaction_outbox":           3,
	} {
		count, countErr := runtime.Database.Collection(collection).CountDocuments(
			context.Background(),
			bson.M{},
		)
		if countErr != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, countErr)
		}
	}
}
