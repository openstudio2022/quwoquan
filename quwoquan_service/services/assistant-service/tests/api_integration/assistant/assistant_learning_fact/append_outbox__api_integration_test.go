// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	learninghttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/adapters/inbound/http"
	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	learningpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/persistence"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
)

func TestAssistantLearningFactCommitsFactReceiptAndOutboxAtomically(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "assistant_learning_fact_api_integration")
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	store := learningpersistence.NewMongoStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure AssistantLearningFact indexes: %v", err)
	}
	_, err = runtime.Database.Collection("assistant_runs").InsertOne(startupCtx, bson.M{
		"_id": "run-learning-fact", "userId": "learning-owner",
		"personaId": "learning-owner:persona",
		"snapshot":  bson.M{"trigger": bson.M{"messageId": "message-learning-fact"}},
	})
	if err != nil {
		t.Fatalf("seed assistant run owner: %v", err)
	}
	service := learningapplication.NewService(
		store, runpersistence.NewMongoRunOwnerReader(runtime.Database), nil,
	)
	mux := http.NewServeMux()
	learninghttp.NewHandler(service).RegisterRoutes(mux)

	body := map[string]any{
		"eventId": "learning-event-1", "factType": "user_feedback",
		"assistantTurnId": "run-learning-fact", "triggerMessageId": "message-learning-fact",
		"referralSource": "article", "domainId": "assistant",
		"feedbackType": "useful", "actionType": "thumbs_up",
		"trainingEligible": false, "occurredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}
	accepted := learningFactRequest(t, mux, "learning-owner", body)
	if accepted.Code != http.StatusOK {
		t.Fatalf("append status=%d body=%s", accepted.Code, accepted.Body.String())
	}
	var first learningmodel.Receipt
	if err := json.Unmarshal(accepted.Body.Bytes(), &first); err != nil {
		t.Fatalf("decode learning receipt: %v", err)
	}
	if !first.Accepted || first.Deduplicated || first.AppendSequence != 1 || first.PayloadDigest == "" {
		t.Fatalf("unexpected first receipt: %+v", first)
	}
	replayed := learningFactRequest(t, mux, "learning-owner", body)
	if replayed.Code != http.StatusOK {
		t.Fatalf("replay status=%d body=%s", replayed.Code, replayed.Body.String())
	}
	var replay learningmodel.Receipt
	if err := json.Unmarshal(replayed.Body.Bytes(), &replay); err != nil {
		t.Fatalf("decode replay receipt: %v", err)
	}
	if !replay.Deduplicated || replay.EventID != first.EventID || replay.AppendSequence != first.AppendSequence || replay.PayloadDigest != first.PayloadDigest {
		t.Fatalf("replay drifted: first=%+v replay=%+v", first, replay)
	}
	assertLearningCount(t, runtime, "assistant_learning_facts", 1)
	assertLearningCount(t, runtime, "assistant_learning_fact_receipts", 1)
	assertLearningCount(t, runtime, "assistant_learning_fact_outbox", 1)

	conflictingBody := cloneLearningCommand(body)
	conflictingBody["actionType"] = "thumbs_down"
	conflict := learningFactRequest(t, mux, "learning-owner", conflictingBody)
	if conflict.Code != http.StatusConflict || !strings.Contains(conflict.Body.String(), "learning_fact_identity_conflict") {
		t.Fatalf("identity conflict status=%d body=%s", conflict.Code, conflict.Body.String())
	}
	assertLearningCount(t, runtime, "assistant_learning_facts", 1)
	assertLearningCount(t, runtime, "assistant_learning_fact_receipts", 1)
	assertLearningCount(t, runtime, "assistant_learning_fact_outbox", 1)

	foreign := learningFactRequest(t, mux, "learning-other", map[string]any{
		"eventId": "learning-event-foreign", "factType": "user_feedback",
		"assistantTurnId": "run-learning-fact", "triggerMessageId": "message-learning-fact",
		"referralSource": "article", "domainId": "assistant",
		"feedbackType": "useful", "actionType": "thumbs_up",
		"trainingEligible": false, "occurredAt": time.Now().UTC().Format(time.RFC3339Nano),
	})
	if foreign.Code != http.StatusForbidden {
		t.Fatalf("foreign owner status=%d body=%s", foreign.Code, foreign.Body.String())
	}
}

func learningFactRequest(t *testing.T, handler http.Handler, accountID string, body any) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal learning fact request: %v", err)
	}
	request := httptest.NewRequest(http.MethodPost, "/assistant/learning/facts", bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: accountID, PersonaID: accountID + ":persona"},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func cloneLearningCommand(source map[string]any) map[string]any {
	result := make(map[string]any, len(source))
	for key, value := range source {
		result[key] = value
	}
	return result
}

func assertLearningCount(t *testing.T, runtime *testinfra.RealMongo, collection string, want int64) {
	t.Helper()
	count, err := runtime.Database.Collection(collection).CountDocuments(t.Context(), bson.M{})
	if err != nil || count != want {
		t.Fatalf("%s count=%d err=%v want=%d", collection, count, err, want)
	}
}
