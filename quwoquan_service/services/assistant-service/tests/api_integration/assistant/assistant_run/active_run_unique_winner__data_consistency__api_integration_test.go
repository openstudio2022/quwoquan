// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
package assistant_run_integration

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	runhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
)

func TestMongoAssistantRunConcurrentStartHasOneActiveWinner(t *testing.T) {
	database := requirePublicWebMongo(t).Client().Database(
		fmt.Sprintf("assistant_run_active_winner_%d", time.Now().UnixNano()),
	)
	t.Cleanup(func() { _ = database.Drop(t.Context()) })
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	now := time.Date(2026, 8, 14, 10, 0, 0, 0, time.UTC)
	handler := runhttp.NewHandler(newAssistantRunControlService(repository, &now)).Routes()

	const writers = 12
	start := make(chan struct{})
	results := make(chan activeRunStartResult, writers)
	var wait sync.WaitGroup
	for index := 0; index < writers; index++ {
		index := index
		wait.Add(1)
		go func() {
			defer wait.Done()
			requestID := fmt.Sprintf("mongo-active-request-%02d", index)
			inputText := fmt.Sprintf("执行数据库并发意图 %02d", index)
			<-start
			results <- activeRunStartResult{
				requestID: requestID,
				inputText: inputText,
				response: activeRunStartRequest(
					t,
					handler,
					"mongo-active-owner",
					"mongo-active-session",
					requestID,
					inputText,
				),
			}
		}()
	}
	close(start)
	wait.Wait()
	close(results)

	var winner activeRunStartResult
	successes := 0
	conflicts := 0
	for result := range results {
		switch result.response.Code {
		case http.StatusCreated:
			successes++
			winner = result
		case http.StatusConflict:
			conflicts++
			assertAssistantRunControlError(
				t,
				result.response,
				http.StatusConflict,
				"ASSISTANT.USER.run_active_conflict",
			)
		default:
			t.Fatalf(
				"concurrent Start request=%s status=%d body=%s",
				result.requestID,
				result.response.Code,
				result.response.Body,
			)
		}
	}
	if successes != 1 || conflicts != writers-1 {
		t.Fatalf("successes=%d conflicts=%d", successes, conflicts)
	}
	winnerEnvelope := decodeActiveRunEnvelope(t, winner.response)
	assertOneMongoActiveRun(t, database, "mongo-active-session", winnerEnvelope.RunID)

	replay := activeRunStartRequest(
		t,
		handler,
		"mongo-active-owner",
		"mongo-active-session",
		winner.requestID,
		winner.inputText,
	)
	if replay.Code != http.StatusCreated || decodeActiveRunEnvelope(t, replay).RunID != winnerEnvelope.RunID {
		t.Fatalf("winner replay status=%d body=%s", replay.Code, replay.Body)
	}

	cancel := assistantRunControlRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/runs/"+winnerEnvelope.RunID+"/cancel",
		"mongo-active-owner",
		"mongo-active-cancel",
		nil,
	)
	if cancel.Code != http.StatusOK {
		t.Fatalf("cancel winner status=%d body=%s", cancel.Code, cancel.Body)
	}
	assertMongoRunHasNoActiveSessionKey(t, database, winnerEnvelope.RunID)

	secondRequestID := "mongo-active-request-next"
	secondResponse := activeRunStartRequest(
		t,
		handler,
		"mongo-active-owner",
		"mongo-active-session",
		secondRequestID,
		"终态之后启动新数据库意图",
	)
	if secondResponse.Code != http.StatusCreated {
		t.Fatalf("start after terminal status=%d body=%s", secondResponse.Code, secondResponse.Body)
	}
	secondEnvelope := decodeActiveRunEnvelope(t, secondResponse)
	assertOneMongoActiveRun(t, database, "mongo-active-session", secondEnvelope.RunID)

	oldReplay := activeRunStartRequest(
		t,
		handler,
		"mongo-active-owner",
		"mongo-active-session",
		winner.requestID,
		winner.inputText,
	)
	if oldReplay.Code != http.StatusCreated || decodeActiveRunEnvelope(t, oldReplay).RunID != winnerEnvelope.RunID {
		t.Fatalf("old winner replay status=%d body=%s", oldReplay.Code, oldReplay.Body)
	}
	assertOneMongoActiveRun(t, database, "mongo-active-session", secondEnvelope.RunID)

	oldTerminalReplay := assistantRunControlRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/runs/"+winnerEnvelope.RunID+"/cancel",
		"mongo-active-owner",
		"mongo-active-cancel",
		nil,
	)
	if oldTerminalReplay.Code != http.StatusOK {
		t.Fatalf("old terminal replay status=%d body=%s", oldTerminalReplay.Code, oldTerminalReplay.Body)
	}
	assertOneMongoActiveRun(t, database, "mongo-active-session", secondEnvelope.RunID)
}

func TestMongoAssistantRunActiveIndexFailsClosedOnExistingDuplicates(t *testing.T) {
	database := requirePublicWebMongo(t).Client().Database(
		fmt.Sprintf("assistant_run_duplicate_index_%d", time.Now().UnixNano()),
	)
	t.Cleanup(func() { _ = database.Drop(t.Context()) })
	collection := database.Collection("assistant_runs")
	for index := 0; index < 2; index++ {
		_, err := collection.InsertOne(t.Context(), bson.M{
			"_id":         fmt.Sprintf("legacy-active-%d", index),
			"userId":      "legacy-owner",
			"sessionId":   "legacy-duplicate-session",
			"status":      "accepted",
			"runRevision": int64(1),
		})
		if err != nil {
			t.Fatalf("seed legacy active Run %d: %v", index, err)
		}
	}
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err == nil {
		t.Fatal("EnsureIndexes accepted duplicate active Runs")
	}
}

type activeRunStartResult struct {
	requestID string
	inputText string
	response  *httptest.ResponseRecorder
}

type activeRunEnvelope struct {
	RunID string `json:"runId"`
}

func activeRunStartRequest(
	t *testing.T,
	handler http.Handler,
	userID string,
	sessionID string,
	requestID string,
	inputText string,
) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(map[string]any{
		"clientRequestId": requestID,
		"intent": map[string]any{
			"kind":   "answer",
			"answer": map[string]any{"text": inputText},
		},
	})
	if err != nil {
		t.Fatalf("marshal StartAssistantRun request: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/assistant/sessions/"+sessionID+"/runs",
		bytes.NewReader(payload),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", requestID)
	request.Header.Set("X-Client-User-Id", userID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: userID,
			PersonaID: userID + ":persona",
		}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func decodeActiveRunEnvelope(
	t *testing.T,
	response *httptest.ResponseRecorder,
) activeRunEnvelope {
	t.Helper()
	var envelope activeRunEnvelope
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode active Run envelope: %v body=%s", err, response.Body)
	}
	return envelope
}

func assertOneMongoActiveRun(
	t *testing.T,
	database *mongo.Database,
	sessionID string,
	wantRunID string,
) {
	t.Helper()
	count, err := database.Collection("assistant_runs").CountDocuments(
		t.Context(),
		bson.M{"activeSessionKey": sessionID},
	)
	if err != nil || count != 1 {
		t.Fatalf("active Run count=%d want=1 err=%v", count, err)
	}
	var document struct {
		ID string `bson:"_id"`
	}
	if err := database.Collection("assistant_runs").FindOne(
		t.Context(),
		bson.M{"activeSessionKey": sessionID},
	).Decode(&document); err != nil || document.ID != wantRunID {
		t.Fatalf("active winner=%s want=%s err=%v", document.ID, wantRunID, err)
	}
}

func assertMongoRunHasNoActiveSessionKey(
	t *testing.T,
	database *mongo.Database,
	runID string,
) {
	t.Helper()
	count, err := database.Collection("assistant_runs").CountDocuments(
		t.Context(),
		bson.M{"_id": runID, "activeSessionKey": bson.M{"$exists": true}},
	)
	if err != nil || count != 0 {
		t.Fatalf("terminal Run retained activeSessionKey: count=%d err=%v", count, err)
	}
}

var _ runruntime.Repository = (*runpersistence.MongoRunRepository)(nil)
