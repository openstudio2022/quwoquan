package gathering_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/operation"
	gatheringhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering/adapters/inbound/http"
	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	gatheringmodel "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	gatheringpersistence "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/persistence"
)

type targetReader struct{}

func (targetReader) RequireNavigable(_ context.Context, target gatheringmodel.TargetRef) error {
	if target.ObjectTypeRef == "circle" && target.ObjectID == "circle-1" && target.RouteID == "circleDetail" {
		return nil
	}
	return errors.New("target not navigable")
}

type chatProjection struct {
	failMembership bool
	projectCalls   int
}

func (projection *chatProjection) EnsureGroupConversation(
	_ context.Context,
	_, _, _ string,
	_ int64,
	_ string,
) (string, error) {
	return "conversation-gathering-1", nil
}

func (projection *chatProjection) ProjectParticipant(
	_ context.Context,
	_, _, _ string,
	state string,
	_ int64,
	_ string,
) error {
	if projection.failMembership && state == "joined" {
		return errors.New("Chat unavailable")
	}
	projection.projectCalls++
	return nil
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestGatheringHTTPPersistsAtomicReceiptsOutboxAndDurableReconciliation(t *testing.T) {
	ctx := context.Background()
	runtime, err := testinfra.StartRealMongo(ctx, "circle_gathering_api_integration")
	if err != nil {
		t.Fatalf("start real Mongo replica set: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real Mongo: %v", closeErr)
		}
	})

	store := gatheringpersistence.NewMongoAggregateStore(runtime.Database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure Gathering indexes: %v", err)
	}
	chat := &chatProjection{}
	commands := gatheringapp.NewCommandFacade(store, targetReader{}, chat)
	queries := gatheringapp.NewQueryFacade(store)
	mux := http.NewServeMux()
	gatheringhttp.NewHandler(commands, queries).Register(mux)

	createBody := map[string]any{
		"title": "贡嘎日落同行",
		"targetRef": map[string]any{
			"objectTypeRef": "circle", "objectId": "circle-1", "routeId": "circleDetail",
		},
		"startAt":    time.Now().UTC().Add(time.Hour).Format(time.RFC3339Nano),
		"capacity":   2,
		"joinPolicy": "open",
	}
	created := execute(t, mux, http.MethodPost, "/gatherings", createBody, "persona-owner", "create-1")
	if created.Code != http.StatusCreated {
		t.Fatalf("create Gathering status=%d body=%s", created.Code, created.Body.String())
	}
	createdBody := decode(t, created)
	gatheringID, _ := createdBody["gatheringId"].(string)
	if gatheringID == "" || createdBody["status"] != "open" || createdBody["conversationId"] != "conversation-gathering-1" {
		t.Fatalf("create Gathering response drift: %#v", createdBody)
	}

	replay := execute(t, mux, http.MethodPost, "/gatherings", createBody, "persona-owner", "create-1")
	if replay.Code != http.StatusCreated || decode(t, replay)["idempotentReplay"] != true {
		t.Fatalf("create replay status=%d body=%s", replay.Code, replay.Body.String())
	}
	assertCollectionCount(t, runtime, "gatherings", 1)
	assertCollectionCount(t, runtime, "gathering_command_receipts", 2)
	assertCollectionCount(t, runtime, "gathering_outbox", 2)

	chat.failMembership = true
	failedJoin := execute(t, mux, http.MethodPost, "/gatherings/"+gatheringID+":join", nil, "persona-member", "join-1")
	if failedJoin.Code != http.StatusServiceUnavailable {
		t.Fatalf("failed join status=%d body=%s", failedJoin.Code, failedJoin.Body.String())
	}
	stored, found, err := store.Load(ctx, gatheringID)
	if err != nil || !found || participantState(stored, "persona-member") != gatheringmodel.ParticipantStatePending {
		t.Fatalf("failed join must persist pending intent: found=%v value=%+v err=%v", found, stored, err)
	}

	chat.failMembership = false
	reconciler := gatheringapp.NewReconciler(store, store, chat)
	if count, err := reconciler.ReconcileOnce(ctx, 10); err != nil || count != 1 {
		t.Fatalf("reconcile Gathering count=%d err=%v", count, err)
	}
	stored, found, err = store.Load(ctx, gatheringID)
	if err != nil || !found || participantState(stored, "persona-member") != gatheringmodel.ParticipantStateJoined {
		t.Fatalf("reconciled join drift: found=%v value=%+v err=%v", found, stored, err)
	}
	assertCollectionCount(t, runtime, "gathering_command_receipts", 4)
	assertCollectionCount(t, runtime, "gathering_outbox", 4)
	assertCollectionCount(t, runtime, "gathering_reconciliation_checkpoints", 1)

	projectCalls := chat.projectCalls
	if count, err := reconciler.ReconcileOnce(ctx, 10); err != nil || count != 0 {
		t.Fatalf("settled reconcile count=%d err=%v", count, err)
	}
	if chat.projectCalls != projectCalls {
		t.Fatal("durable checkpoint must prevent duplicate Chat projection")
	}
}

func execute(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body any,
	personaID string,
	idempotencyKey string,
) *httptest.ResponseRecorder {
	t.Helper()
	var encoded bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&encoded).Encode(body); err != nil {
			t.Fatal(err)
		}
	}
	request := httptest.NewRequest(method, path, &encoded)
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
		OperationID:    "circle.gathering.api-integration",
		RequestID:      "request-" + idempotencyKey,
		TraceID:        "trace-" + idempotencyKey,
		IdempotencyKey: idempotencyKey,
		Actor:          operation.ActorContext{PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func decode(t *testing.T, recorder *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var value map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &value); err != nil {
		t.Fatalf("decode response: %v body=%s", err, recorder.Body.String())
	}
	return value
}

func participantState(value gatheringmodel.Gathering, personaID string) gatheringmodel.ParticipantState {
	for _, participant := range value.Participants {
		if participant.PersonaID == personaID {
			return participant.State
		}
	}
	return gatheringmodel.ParticipantState("")
}

func assertCollectionCount(t *testing.T, runtime *testinfra.RealMongo, collection string, want int64) {
	t.Helper()
	count, err := runtime.Database.Collection(collection).CountDocuments(context.Background(), bson.M{})
	if err != nil || count != want {
		t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, err)
	}
}
