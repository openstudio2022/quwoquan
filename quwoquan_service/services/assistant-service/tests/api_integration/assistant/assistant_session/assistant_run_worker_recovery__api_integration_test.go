// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-001
package api_integration

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

func TestAssistantRunExpiredMongoClaimIsRecoveredByAnotherWorker(
	t *testing.T,
) {
	ctx := context.Background()
	service := newIntegrationAssistantService()
	session, err := service.CreateSession(
		ctx,
		"worker-recovery-owner",
		assistant.CreateSessionInput{
			Summary:         "worker recovery",
			ClientRequestID: "worker-recovery-session",
		},
	)
	if err != nil {
		t.Fatalf("create recovery session: %v", err)
	}
	commands := runruntime.NewCommandService(
		integrationRunRepository,
		runruntime.SessionAuthorizerFunc(func(
			ctx context.Context,
			userID string,
			sessionID string,
		) error {
			_, authorizeErr := service.GetSession(ctx, userID, sessionID)
			return authorizeErr
		}),
		time.Now,
		nil,
	)
	run, err := commands.Start(ctx, runruntime.StartCommand{
		UserID:          "worker-recovery-owner",
		SessionID:       session.SessionID,
		ClientRequestID: "worker-recovery-run",
		InputText:       "恢复后给出可回查答案",
	})
	if err != nil {
		t.Fatalf("start recovery run: %v", err)
	}

	first, err := integrationRunRepository.ClaimNext(
		ctx,
		"worker-expired",
		50*time.Millisecond,
	)
	if err != nil {
		t.Fatalf("first claim: %v", err)
	}
	time.Sleep(75 * time.Millisecond)
	recovered, err := integrationRunRepository.ClaimNext(
		ctx,
		"worker-recovered",
		time.Second,
	)
	if err != nil {
		t.Fatalf("recover expired claim: %v", err)
	}
	if recovered.RunID != run.RunID ||
		recovered.FencingToken <= first.FencingToken {
		t.Fatalf("claim was not fenced and recovered: first=%#v next=%#v", first, recovered)
	}
	if err := integrationRunRepository.CompleteClaim(
		ctx,
		recovered,
		true,
		time.Now().UTC(),
	); err != nil {
		t.Fatalf("reschedule recovered claim: %v", err)
	}

	worker := runruntime.NewDurableWorker(
		integrationRunRepository,
		integrationRunRepository,
		recoveredRunExecutor{},
		"worker-recovered",
	)
	worked, err := worker.ProcessNext(ctx)
	if err != nil || !worked {
		t.Fatalf("process recovered run: worked=%t err=%v", worked, err)
	}
	stored, err := integrationRunRepository.Load(ctx, run.RunID)
	if err != nil {
		t.Fatalf("load recovered run: %v", err)
	}
	if stored.State != generated.AssistantRunStateCompleted ||
		stored.TerminalSnapshot["answerText"] != "恢复后的可回查答案" {
		t.Fatalf("unexpected recovered terminal run: %#v", stored)
	}
}

func TestAssistantRunSSEFollowsJournalUntilWorkerTerminalEvent(t *testing.T) {
	ctx := context.Background()
	const userID = "worker-stream-owner"
	service := newIntegrationAssistantService()
	session, err := service.CreateSession(
		ctx,
		userID,
		assistant.CreateSessionInput{
			Summary:         "worker stream",
			ClientRequestID: "worker-stream-session",
		},
	)
	if err != nil {
		t.Fatalf("create stream session: %v", err)
	}
	commands := runruntime.NewCommandService(
		integrationRunRepository,
		runruntime.SessionAuthorizerFunc(func(
			ctx context.Context,
			userID string,
			sessionID string,
		) error {
			_, authorizeErr := service.GetSession(ctx, userID, sessionID)
			return authorizeErr
		}),
		time.Now,
		nil,
	)
	run, err := commands.Start(ctx, runruntime.StartCommand{
		UserID:          userID,
		SessionID:       session.SessionID,
		ClientRequestID: "worker-stream-run",
		InputText:       "持续流式直到终态",
	})
	if err != nil {
		t.Fatalf("start streamed run: %v", err)
	}
	handler := assistanthttp.NewHandler(
		service,
		assistanthttp.WithRunCommandService(commands),
	).Routes()
	request := httptest.NewRequest(
		http.MethodGet,
		"/assistant/runs/"+run.RunID+"/events",
		nil,
	)
	request.Header.Set("X-Client-User-Id", userID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: userID,
			PersonaID: userID + ":persona",
		}},
	))
	recorder := httptest.NewRecorder()
	streamDone := make(chan struct{})
	go func() {
		handler.ServeHTTP(recorder, request)
		close(streamDone)
	}()

	worker := runruntime.NewDurableWorker(
		integrationRunRepository,
		integrationRunRepository,
		recoveredRunExecutor{},
		"worker-stream",
	)
	worked, err := worker.ProcessNext(ctx)
	if err != nil || !worked {
		t.Fatalf("process streamed run: worked=%t err=%v", worked, err)
	}
	select {
	case <-streamDone:
	case <-time.After(3 * time.Second):
		t.Fatal("SSE did not follow journal to terminal event")
	}
	body := recorder.Body.String()
	if !strings.Contains(body, `"eventType":"completed"`) ||
		!strings.Contains(body, `"eventType":"process_append"`) ||
		!strings.Contains(body, `"eventType":"presentation_snapshot"`) ||
		!strings.Contains(body, `"eventType":"presentation_commit"`) ||
		!strings.Contains(body, `"processId":"run:`+run.RunID) ||
		!strings.Contains(body, `"runId":"`+run.RunID+`"`) {
		t.Fatalf("SSE missed canonical terminal event: %s", body)
	}
}

func TestAssistantRunFailedSSECarriesStructuredRuntimeFailure(t *testing.T) {
	ctx := context.Background()
	const userID = "worker-failure-owner"
	service := newIntegrationAssistantService()
	session, err := service.CreateSession(
		ctx,
		userID,
		assistant.CreateSessionInput{
			Summary:         "worker failure",
			ClientRequestID: "worker-failure-session",
		},
	)
	if err != nil {
		t.Fatalf("create failure session: %v", err)
	}
	commands := runruntime.NewCommandService(
		integrationRunRepository,
		runruntime.SessionAuthorizerFunc(func(
			ctx context.Context,
			userID string,
			sessionID string,
		) error {
			_, authorizeErr := service.GetSession(ctx, userID, sessionID)
			return authorizeErr
		}),
		time.Now,
		nil,
	)
	run, err := commands.Start(ctx, runruntime.StartCommand{
		UserID:          userID,
		SessionID:       session.SessionID,
		ClientRequestID: "worker-failure-run",
		InputText:       "执行失败必须结构化",
	})
	if err != nil {
		t.Fatalf("start failure run: %v", err)
	}
	worker := runruntime.NewDurableWorker(
		integrationRunRepository,
		integrationRunRepository,
		failedRunExecutor{},
		"worker-failure",
	)
	if worked, processErr := worker.ProcessNext(ctx); processErr != nil || !worked {
		t.Fatalf("process failed run: worked=%t err=%v", worked, processErr)
	}

	handler := assistanthttp.NewHandler(
		service,
		assistanthttp.WithRunCommandService(commands),
	).Routes()
	response := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/runs/"+run.RunID+"/events",
		userID,
		nil,
	)
	body := response.Body.String()
	if !strings.Contains(body, `"eventType":"failed"`) ||
		!strings.Contains(
			body,
			`"code":"ASSISTANT.SYSTEM.run_execution_failed"`,
		) {
		t.Fatalf("failed SSE omitted structured RuntimeFailure: %s", body)
	}
}

type recoveredRunExecutor struct{}

type failedRunExecutor struct{}

func (failedRunExecutor) Execute(
	context.Context,
	runruntime.ExecutionRequest,
	func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	return runruntime.ExecutionResult{}, errors.New("provider disconnected")
}

func (recoveredRunExecutor) Execute(
	_ context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	itemID := request.IdempotencyPrefix + ":tool:recovered"
	if err := emit(runruntime.ExecutionItemUpdate{
		ItemID: itemID,
		Kind:   generated.AssistantRunItemKindToolUse,
		Status: generated.AssistantRunItemStatusStarted,
		TaskID: "task_root",
	}); err != nil {
		return runruntime.ExecutionResult{}, err
	}
	if err := emit(runruntime.ExecutionItemUpdate{
		ItemID: itemID,
		Kind:   generated.AssistantRunItemKindToolUse,
		Status: generated.AssistantRunItemStatusCompleted,
		TaskID: "task_root",
	}); err != nil {
		return runruntime.ExecutionResult{}, err
	}
	return runruntime.ExecutionResult{
		AnswerText: "恢复后的可回查答案",
		Presentation: map[string]any{
			"templateRef":       "assistant.answer.default@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"templateDigest":    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"revision":          int64(1),
			"rootNodeId":        "root",
			"nodes":             []map[string]any{{"nodeId": "root", "kind": "markdown", "body": "恢复后的可回查答案"}},
			"dataDigest":        "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
			"selectedVariant":   "standard",
			"fallbackMarkdown":  "恢复后的可回查答案",
			"fallbackPlainText": "恢复后的可回查答案",
			"committedAt":       "",
		},
		Verified:            true,
		VerificationSummary: "恢复后验证通过",
	}, nil
}
