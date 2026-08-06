// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rtstreaming "quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	"quwoquan_service/services/assistant-service/tests/support/assistantingress"
)

func TestAssistantRunHTTPUsesOneMongoAggregateAndJournal(t *testing.T) {
	ctx := context.Background()
	service := newIntegrationAssistantService()
	session, err := service.CreateSession(ctx, "run-owner", assistant.CreateSessionInput{
		Summary:         "AssistantRun single truth",
		ClientRequestID: "session-single-truth",
	})
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	commands := runruntime.NewCommandService(
		integrationRunRepository,
		runruntime.SessionResolverFunc(func(
			ctx context.Context,
			userID string,
			sessionID string,
		) (runruntime.SessionContinuity, error) {
			_, err := service.GetSession(ctx, userID, sessionID)
			return runruntime.SessionContinuity{}, err
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(integrationRunPolicyResolver()),
	)
	handler := assistantingress.Routes(
		service,
		assistantingress.WithRunCommandService(commands),
	)
	startBody := map[string]any{
		"clientRequestId": "run-single-truth",
		"intent": map[string]any{
			"kind":   "answer",
			"answer": map[string]any{"text": "核对公开资料后回答"},
		},
		"reasoningProfile": "balanced",
		"definitionOfDone": map[string]any{
			"outcome":                  "返回可回查答案",
			"verificationRequirements": []string{"answer_present"},
		},
	}

	started := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"run-owner",
		startBody,
	)
	if started.Code != http.StatusCreated {
		t.Fatalf("start status=%d body=%s", started.Code, started.Body.String())
	}
	var envelope map[string]any
	if err := json.Unmarshal(started.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode start envelope: %v", err)
	}
	runID, _ := envelope["runId"].(string)
	if !strings.HasPrefix(runID, "arn_") {
		t.Fatalf("unexpected runId: %#v", envelope)
	}
	if _, legacy := envelope["turnId"]; legacy {
		t.Fatalf("run envelope leaked legacy turnId: %#v", envelope)
	}
	replayed := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"run-owner",
		startBody,
	)
	var replayEnvelope map[string]any
	if err := json.Unmarshal(replayed.Body.Bytes(), &replayEnvelope); err != nil {
		t.Fatalf("decode replay envelope: %v", err)
	}
	if replayEnvelope["runId"] != runID {
		t.Fatalf("idempotency replay changed run: %#v", replayEnvelope)
	}

	paused := assistantRunCommandRequest(
		t,
		handler,
		"/assistant/runs/"+runID+"/pause",
		"run-owner",
		"pause-single-truth",
		map[string]any{"reason": "稍后继续"},
	)
	assertRunStatus(t, paused, "paused")
	resumed := assistantRunCommandRequest(
		t,
		handler,
		"/assistant/runs/"+runID+"/resume",
		"run-owner",
		"resume-single-truth",
		nil,
	)
	assertRunStatus(t, resumed, "orienting")
	steered := assistantRunCommandRequest(
		t,
		handler,
		"/assistant/runs/"+runID+"/steer",
		"run-owner",
		"steer-single-truth",
		map[string]any{"instruction": "只采用可回查来源"},
	)
	assertRunStatus(t, steered, "orienting")
	cancelled := assistantRunCommandRequest(
		t,
		handler,
		"/assistant/runs/"+runID+"/cancel",
		"run-owner",
		"cancel-single-truth",
		nil,
	)
	assertRunStatus(t, cancelled, "cancelled")

	streamRequest := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/runs/"+runID+"/events?resumeToken="+
			url.QueryEscape(rtstreaming.NewResumeToken(runID, 1)),
		"run-owner",
		nil,
	)
	if streamRequest.Code != http.StatusOK {
		t.Fatalf("stream status=%d body=%s", streamRequest.Code, streamRequest.Body.String())
	}
	streamBody := streamRequest.Body.String()
	if strings.Contains(streamBody, `"turnId"`) ||
		!strings.Contains(streamBody, `"runId":"`+runID+`"`) {
		t.Fatalf("stream is not canonical AssistantRun wire: %s", streamBody)
	}
	if strings.Contains(streamBody, "\nid: "+runID+":1\n") {
		t.Fatalf("Last-Event-ID replay included acknowledged event: %s", streamBody)
	}

	foreign := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/runs/"+runID,
		"another-owner",
		nil,
	)
	if foreign.Code != http.StatusNotFound {
		t.Fatalf("cross-owner get status=%d body=%s", foreign.Code, foreign.Body.String())
	}
	runCount, err := integrationMongoDB.Collection("assistant_runs").CountDocuments(
		ctx,
		bson.M{"clientRequestId": "run-single-truth"},
	)
	if err != nil {
		t.Fatalf("count runs: %v", err)
	}
	if runCount != 1 {
		t.Fatalf("expected one writable AssistantRun, got %d", runCount)
	}
	events, err := integrationRunRepository.EventsAfter(ctx, runID, 0, 20)
	if err != nil {
		t.Fatalf("read persisted journal: %v", err)
	}
	for index, event := range events {
		want := int64(index + 1)
		if event.Sequence != want {
			t.Fatalf("journal gap at index %d: got=%d want=%d", index, event.Sequence, want)
		}
	}
	loaded, err := integrationRunRepository.Load(ctx, runID)
	if err != nil {
		t.Fatalf("load run: %v", err)
	}
	if err := integrationRunRepository.Commit(
		ctx,
		loaded.Revision-1,
		loaded,
		nil,
		nil,
	); !errorsIsRevisionConflict(err) {
		t.Fatalf("stale CAS must conflict, got %v", err)
	}
}

func assertRunStatus(t *testing.T, response interface {
	Result() *http.Response
}, want string) {
	t.Helper()
	httpResponse := response.Result()
	defer httpResponse.Body.Close()
	var envelope map[string]any
	if err := json.NewDecoder(httpResponse.Body).Decode(&envelope); err != nil {
		t.Fatalf("decode run envelope: %v", err)
	}
	if httpResponse.StatusCode != http.StatusOK || envelope["status"] != want {
		t.Fatalf(
			"run status=%d envelope=%#v want=%s",
			httpResponse.StatusCode,
			envelope,
			want,
		)
	}
}

func assistantRunCommandRequest(
	t *testing.T,
	handler http.Handler,
	path string,
	userID string,
	commandID string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal run command: %v", err)
		}
	}
	request := httptest.NewRequest(
		http.MethodPost,
		path,
		bytes.NewReader(payload),
	)
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	request.Header.Set("Idempotency-Key", commandID)
	request.Header.Set("X-Client-User-Id", userID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{
			Actor: operation.ActorContext{
				AccountID: userID,
				PersonaID: userID + ":persona",
			},
		},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func errorsIsRevisionConflict(err error) bool {
	return err == runruntime.ErrRevisionConflict
}
