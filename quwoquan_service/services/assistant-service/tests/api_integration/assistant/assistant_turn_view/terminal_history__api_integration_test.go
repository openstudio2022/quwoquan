// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	sessionpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	turnviewhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/adapters/inbound/http"
	turnviewapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/application"
	turnviewmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/domain/model"
	turnviewpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/infrastructure/persistence"
)

func TestAssistantTurnViewReturnsOnlyTerminalOwnerHistoryWithStableCursor(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "assistant_turn_view_api_integration")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	now := time.Now().UTC().Truncate(time.Millisecond)
	sessions := sessionpersistence.NewMongoSessionStore(runtime.Database)
	for _, session := range []assistant.AssistantSession{
		{SessionID: "session-owner", UserID: "turn-owner", State: "active", ClientRequestID: "session-owner-request", CreatedAt: now, UpdatedAt: now},
		{SessionID: "session-other", UserID: "turn-other", State: "active", ClientRequestID: "session-other-request", CreatedAt: now, UpdatedAt: now},
	} {
		if _, _, err := sessions.InsertSession(startupCtx, session); err != nil {
			t.Fatalf("seed session %s: %v", session.SessionID, err)
		}
	}
	runs := runpersistence.NewMongoRunRepository(runtime.Database)
	for _, run := range []runruntime.Run{
		terminalRun("turn-new", "session-owner", "turn-owner", "new", generated.AssistantRunStateCompleted, now),
		terminalRun("turn-old", "session-owner", "turn-owner", "old", generated.AssistantRunStateFailed, now.Add(-time.Minute)),
		terminalRun("turn-secret", "session-other", "turn-other", "secret", generated.AssistantRunStateCompleted, now.Add(2*time.Minute)),
	} {
		if err := runs.Commit(startupCtx, 0, run, []runruntime.JournalEvent{{
			EventID:   run.RunID + ":terminal",
			RunID:     run.RunID,
			Sequence:  1,
			Revision:  1,
			Kind:      "run_terminal",
			Payload:   map[string]any{"status": run.State.WireName()},
			CreatedAt: run.UpdatedAt,
		}}, nil); err != nil {
			t.Fatalf("seed canonical run %s: %v", run.RunID, err)
		}
	}
	turnViews := turnviewpersistence.NewMongoStore(runtime.Database)
	if err := turnViews.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure turn view indexes: %v", err)
	}
	projector := turnviewapplication.NewProjector(runs, turnViews)

	mux := http.NewServeMux()
	turnviewhttp.NewHandler(turnviewapplication.NewQueryFacade(
		turnViews,
		sessions,
		projector,
	)).RegisterRoutes(mux)

	first := turnViewRequest(mux, "/assistant/sessions/session-owner/turns?limit=1", "turn-owner")
	if first.Code != http.StatusOK {
		t.Fatalf("first page status=%d body=%s", first.Code, first.Body.String())
	}
	var firstView turnviewmodel.AssistantTurnListView
	if err := json.Unmarshal(first.Body.Bytes(), &firstView); err != nil {
		t.Fatalf("decode first page: %v", err)
	}
	if len(firstView.Items) != 1 || firstView.Items[0].TurnID != "turn-new" || firstView.NextCursor == "" {
		t.Fatalf("unexpected first page: %+v", firstView)
	}
	second := turnViewRequest(mux, "/assistant/sessions/session-owner/turns?limit=1&cursor="+firstView.NextCursor, "turn-owner")
	if second.Code != http.StatusOK {
		t.Fatalf("second page status=%d body=%s", second.Code, second.Body.String())
	}
	var secondView turnviewmodel.AssistantTurnListView
	if err := json.Unmarshal(second.Body.Bytes(), &secondView); err != nil {
		t.Fatalf("decode second page: %v", err)
	}
	if len(secondView.Items) != 1 || secondView.Items[0].TurnID != "turn-old" || secondView.NextCursor != "" {
		t.Fatalf("unexpected second page: %+v", secondView)
	}

	foreign := turnViewRequest(mux, "/assistant/sessions/session-owner/turns", "turn-other")
	if foreign.Code != http.StatusNotFound {
		t.Fatalf("foreign history status=%d body=%s", foreign.Code, foreign.Body.String())
	}
	untrustedRequest := httptest.NewRequest(http.MethodGet, "/assistant/sessions/session-owner/turns", nil)
	untrustedRequest.Header.Set("X-Client-User-Id", "turn-owner")
	untrusted := httptest.NewRecorder()
	mux.ServeHTTP(untrusted, untrustedRequest)
	if untrusted.Code != http.StatusUnauthorized {
		t.Fatalf("untrusted identity header status=%d body=%s", untrusted.Code, untrusted.Body.String())
	}
}

func terminalRun(
	runID string,
	sessionID string,
	userID string,
	input string,
	state generated.AssistantRunState,
	at time.Time,
) runruntime.Run {
	completedAt := at.UTC()
	snapshot := runmodel.AssistantRunTerminalSnapshot{
		AnswerText: input + " answer",
		Processes:  []runmodel.AssistantRunVisibleProcess{},
	}
	if state == generated.AssistantRunStateFailed {
		snapshot.Failure = &runmodel.AssistantRunTerminalFailure{
			Code:   "ASSISTANT.SYSTEM.run_execution_failed",
			Origin: "system",
			Kind:   "internal",
			Nature: "transient",
		}
	}
	return runruntime.Run{
		RunID:            runID,
		UserID:           userID,
		SessionID:        sessionID,
		ClientRequestID:  runID + ":request",
		InputText:        input,
		Revision:         1,
		JournalSequence:  1,
		State:            state,
		TerminalSnapshot: snapshot.Clone(),
		CreatedAt:        at.UTC(),
		UpdatedAt:        at.UTC(),
		CompletedAt:      &completedAt,
	}
}

func turnViewRequest(handler http.Handler, path, accountID string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodGet, path, nil)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: accountID, PersonaID: accountID + ":persona"},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
