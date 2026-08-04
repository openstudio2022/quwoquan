// spec_ref: specs/feature-tree/circle-community/in-circle-recommendation-loop/behavior-ingestion/spec.md#gwt-001
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/application"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestAppendCircleBehaviorFactHTTPCommitsFactAndOutboxAtomically(t *testing.T) {
	database := testsupport.StartRealMongo(t, "circle_behavior_fact_object_api")
	if _, err := database.Collection("circles").InsertOne(context.Background(), bson.M{
		"_id": "circle-behavior-object", "status": "active",
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAppendSink(database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatal(err)
	}
	handler := httpadapter.NewHandler(app.NewWriter(store, store))
	request := testsupport.Request(t, http.MethodPost, "/circles/behaviors", map[string]any{
		"circleId": "circle-behavior-object", "eventType": "impression",
	}, "circle.circle_behavior_fact.AppendCircleBehaviorFact", "persona-behavior", "behavior-object-1")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("append status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var appended app.AppendResult
	if err := json.NewDecoder(recorder.Body).Decode(&appended); err != nil {
		t.Fatal(err)
	}
	if appended.FactID == "" || appended.IdempotentReplay {
		t.Fatalf("append result=%+v", appended)
	}

	replayRequest := testsupport.Request(t, http.MethodPost, "/circles/behaviors", map[string]any{
		"circleId": "circle-behavior-object", "eventType": "impression",
	}, "circle.circle_behavior_fact.AppendCircleBehaviorFact", "persona-behavior", "behavior-object-1")
	replay := httptest.NewRecorder()
	handler.ServeHTTP(replay, replayRequest)
	if replay.Code != http.StatusOK {
		t.Fatalf("replay status=%d body=%s", replay.Code, replay.Body.String())
	}
	var replayed app.AppendResult
	if err := json.NewDecoder(replay.Body).Decode(&replayed); err != nil {
		t.Fatal(err)
	}
	if replayed.FactID != appended.FactID || !replayed.IdempotentReplay {
		t.Fatalf("replay result=%+v appended=%+v", replayed, appended)
	}
	testsupport.AssertCollectionCount(t, database, "circle_behavior_facts", 1)
	testsupport.AssertCollectionCount(t, database, "circle_behavior_fact_outbox", 1)
}
