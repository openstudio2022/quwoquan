// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

type hookStub struct {
	name   string
	phases []runruntime.HookPhase
	invoke func(runruntime.HookInput) runruntime.HookResult
}

func (h hookStub) Name() string                   { return h.name }
func (h hookStub) Phases() []runruntime.HookPhase { return h.phases }
func (h hookStub) Invoke(_ context.Context, input runruntime.HookInput) (runruntime.HookResult, error) {
	return h.invoke(input), nil
}

func TestRunHooksCanTransformAndBlockButCannotRewriteProtectedFacts(t *testing.T) {
	registry, err := runruntime.NewHookRegistry(
		runruntime.RegisteredHook{Priority: 20, Hook: hookStub{
			name:   "approval",
			phases: []runruntime.HookPhase{runruntime.HookPreToolUse},
			invoke: func(input runruntime.HookInput) runruntime.HookResult {
				return runruntime.HookResult{
					Decision:        runruntime.HookRequireConfirmation,
					Reason:          "device write requires confirmation",
					ConfirmationRef: "confirmation:calendar_write",
					Data:            input.Data,
				}
			},
		}},
		runruntime.RegisteredHook{Priority: 10, Hook: hookStub{
			name:   "normalize",
			phases: []runruntime.HookPhase{runruntime.HookPreToolUse},
			invoke: func(input runruntime.HookInput) runruntime.HookResult {
				input.Data["normalized"] = true
				return runruntime.HookResult{Decision: runruntime.HookAllow, Data: input.Data}
			},
		}},
	)
	if err != nil {
		t.Fatal(err)
	}
	result, err := registry.Run(context.Background(), runruntime.HookInput{
		Phase: runruntime.HookPreToolUse,
		Data:  map[string]any{"tool": "calendar_write"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.Decision != runruntime.HookRequireConfirmation || result.Data["normalized"] != true {
		t.Fatalf("hook result = %#v", result)
	}

	compactionRegistry, err := runruntime.NewHookRegistry(runruntime.RegisteredHook{Hook: hookStub{
		name:   "bad_compactor",
		phases: []runruntime.HookPhase{runruntime.HookPostCompact},
		invoke: func(input runruntime.HookInput) runruntime.HookResult {
			return runruntime.HookResult{
				Decision:             runruntime.HookAllow,
				ProtectedFactsDigest: "rewritten",
			}
		},
	}})
	if err != nil {
		t.Fatal(err)
	}
	_, err = compactionRegistry.Run(context.Background(), runruntime.HookInput{
		Phase:                runruntime.HookPostCompact,
		ProtectedFactsDigest: "canonical",
	})
	if err == nil {
		t.Fatal("post-compact hook rewrote protected facts")
	}
}

func TestReactRuntimeInvokesPlanningAndToolHooksWithoutReasoningTrace(t *testing.T) {
	phases := make([]runruntime.HookPhase, 0, 4)
	registry, err := runruntime.NewHookRegistry(runruntime.RegisteredHook{Hook: hookStub{
		name: "react-lifecycle",
		phases: []runruntime.HookPhase{
			runruntime.HookPrePlan,
			runruntime.HookPostPlan,
			runruntime.HookPreToolUse,
			runruntime.HookPostToolUse,
		},
		invoke: func(input runruntime.HookInput) runruntime.HookResult {
			phases = append(phases, input.Phase)
			for _, forbidden := range []string{"chainOfThought", "modelDelta", "reasoningText"} {
				if _, found := input.Data[forbidden]; found {
					t.Fatalf("%s hook received forbidden reasoning field %q", input.Phase, forbidden)
				}
			}
			return runruntime.HookResult{
				Decision: runruntime.HookAllow,
				Data:     input.Data,
			}
		},
	}})
	if err != nil {
		t.Fatalf("new hook registry: %v", err)
	}
	run := runruntime.Run{
		RunID:                     "run-react-hooks",
		UserID:                    "user-react-hooks",
		SkillPackageReleaseDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		DefinitionOfDone: runruntime.DefinitionOfDone{
			Outcome: "answer_present",
		},
	}
	ctx := runruntime.WithExecutionHooks(t.Context(), registry, run)
	result, err := (orchestration.ReactRuntime{
		Model: reactHookModel{},
		Tools: reactHookTools{},
	}).Run(ctx, assistant.AssistantTurn{
		TurnID: "turn-react-hooks",
		Input:  assistant.AssistantTurnInput{Text: "核验公开事实"},
	}, orchestration.SkillSelection{
		SkillID:      "knowledge_general",
		DomainID:     "knowledge_general",
		ToolPolicy:   []string{"web_search"},
		MaxToolCalls: 1,
	})
	if err != nil {
		t.Fatalf("run React lifecycle: %v", err)
	}
	want := []runruntime.HookPhase{
		runruntime.HookPrePlan,
		runruntime.HookPostPlan,
		runruntime.HookPreToolUse,
		runruntime.HookPostToolUse,
	}
	if len(phases) != len(want) {
		t.Fatalf("hook phases=%v want=%v", phases, want)
	}
	for index := range want {
		if phases[index] != want[index] {
			t.Fatalf("hook phases=%v want=%v", phases, want)
		}
	}
	if result.StopReason != "observation_sufficient" || result.FinalText == "" {
		t.Fatalf("React result=%+v", result)
	}
}

type reactHookModel struct{}

func (reactHookModel) Complete(
	_ context.Context,
	request orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	switch request.Stage {
	case "reasoning":
		return orchestration.ModelResponse{StructuredDelta: map[string]any{
			"nextAction": "tool_call",
			"toolName":   "web_search",
			"toolInput":  map[string]any{"query": "canonical fact"},
		}}, nil
	case "evidence_processing":
		return orchestration.ModelResponse{StructuredDelta: map[string]any{
			"evidenceSufficient": true,
			"retrievalProcessing": map[string]any{
				"processingSummary": "已核验公开事实",
			},
		}}, nil
	case "final":
		return orchestration.ModelResponse{
			Text: "你已获得核验结果。",
			StructuredDelta: map[string]any{
				"userMarkdown": "你已获得核验结果。",
			},
		}, nil
	default:
		return orchestration.ModelResponse{}, nil
	}
}

type reactHookTools struct{}

func (reactHookTools) ToolMetadata(toolName string) (toolpkg.Metadata, bool) {
	if toolName != "web_search" {
		return toolpkg.Metadata{}, false
	}
	return toolpkg.WebSearchMetadata(), true
}

func (reactHookTools) ModelToolDeclarations(
	allowed []string,
) []ports.ModelToolDefinition {
	for _, toolName := range allowed {
		if toolName == "web_search" {
			return []ports.ModelToolDefinition{{
				Name: "web_search",
				Parameters: map[string]any{
					"type":                 "object",
					"additionalProperties": true,
				},
			}}
		}
	}
	return nil
}

func (reactHookTools) Execute(
	_ context.Context,
	request orchestration.ToolRequest,
) (orchestration.ToolExecution, error) {
	result := map[string]any{
		"summary": "canonical fact",
		"evidenceAssessment": map[string]any{
			"status":             "accepted",
			"evidenceSufficient": true,
			"replanRequired":     false,
		},
	}
	return orchestration.ToolExecution{
		Requested: assistant.ToolUse{
			ToolName: request.ToolName,
			Input:    request.Input,
		},
		Completed: assistant.ToolUse{
			ToolName: request.ToolName,
			Input:    request.Input,
			Result:   result,
			Status:   "completed",
		},
	}, nil
}

func TestReasoningProfilesAreCapabilityNegotiatedAndNotProviderNamed(t *testing.T) {
	configs := make([]runruntime.ReasoningProfileConfig, 0, 4)
	for _, profile := range []generated.AssistantReasoningProfile{
		generated.AssistantReasoningProfileFast,
		generated.AssistantReasoningProfileBalanced,
		generated.AssistantReasoningProfileDeep,
		generated.AssistantReasoningProfileBackgroundLong,
	} {
		config := runruntime.ReasoningProfileConfig{
			Profile: profile,
			Capability: runruntime.CapabilityRequirements{
				ToolCalling:     true,
				ReasoningEffort: true,
			},
			Budget: runruntime.ReasoningBudget{
				MaxDuration:  5 * time.Minute,
				MaxTokens:    10_000,
				MaxCostUnits: 10_000,
				MaxToolCalls: 10,
				MaxSubagents: 2,
				MaxSources:   10,
			},
			ReflectionEverySteps: 3,
			SourceBreadth:        4,
			SourceDepth:          2,
			CheckpointEvery:      time.Minute,
			StopRules: runruntime.ReasoningStopRules{
				RequireDefinitionOfDone: true,
				RequireEvidence:         true,
				RequireVerifier:         true,
				StopOnBudgetExhaustion:  true,
			},
		}
		if profile == generated.AssistantReasoningProfileBackgroundLong {
			config.Capability.Background = true
			config.Capability.Compaction = true
		}
		configs = append(configs, config)
	}
	catalog, err := runruntime.NewReasoningProfileCatalog(configs)
	if err != nil {
		t.Fatal(err)
	}
	background, err := catalog.Resolve(generated.AssistantReasoningProfileBackgroundLong)
	if err != nil || !background.Capability.Background || !background.StopRules.RequireVerifier {
		t.Fatalf("background profile = %#v, error = %v", background, err)
	}

	configs[3].Capability.Compaction = false
	if _, err := runruntime.NewReasoningProfileCatalog(configs); err == nil {
		t.Fatal("background_long without compaction was accepted")
	}
	if _, err := catalog.Resolve(generated.AssistantReasoningProfile("provider-model-name")); err == nil || errors.Is(err, context.Canceled) {
		t.Fatalf("unknown provider-specific profile error = %v", err)
	}
}

func TestDurableWorkerResolvesProfileBudgetIntoExecutionRequestAndTaskGraph(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		context.Background(),
		runruntime.StartCommand{
			UserID:          "user-profile-budget",
			SessionID:       "session-profile-budget",
			ClientRequestID: "request-profile-budget",
			InputText:       "完成一个有界任务",
		},
	)
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	executor := &goalCapturingRunExecutor{}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"worker-profile-budget",
	)
	if worked, processErr := worker.ProcessNext(context.Background()); processErr != nil || !worked {
		t.Fatalf("process run: worked=%t err=%v", worked, processErr)
	}
	policy := executor.request.ReasoningPolicy
	if policy.Profile != generated.AssistantReasoningProfileBalanced ||
		policy.Budget.MaxDuration <= 0 || policy.Budget.MaxTokens <= 0 ||
		!policy.StopRules.RequireDefinitionOfDone ||
		!policy.StopRules.RequireVerifier {
		t.Fatalf("resolved reasoning policy = %#v", policy)
	}
	stored, err := repository.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load run: %v", err)
	}
	rootBudget := stored.TaskGraph.Tasks[0].Budget
	if stored.ReasoningPolicy != policy ||
		rootBudget.MaxToolCalls != policy.Budget.MaxToolCalls ||
		rootBudget.MaxTokens != policy.Budget.MaxTokens ||
		rootBudget.MaxCostUnits != policy.Budget.MaxCostUnits ||
		rootBudget.Deadline.IsZero() {
		t.Fatalf("durable policy=%#v task budget=%#v request policy=%#v", stored.ReasoningPolicy, rootBudget, policy)
	}
}

func TestDeepAndBackgroundProfilesFailClosedWithoutEvidenceRequirement(t *testing.T) {
	for _, profile := range []generated.AssistantReasoningProfile{
		generated.AssistantReasoningProfileDeep,
		generated.AssistantReasoningProfileBackgroundLong,
	} {
		t.Run(profile.WireName(), func(t *testing.T) {
			repository := newMemoryRunRepository()
			queue := newMemoryWorkQueue()
			run, err := workerCommandService(repository).Start(
				context.Background(),
				runruntime.StartCommand{
					UserID:           "user-profile-fail-closed",
					SessionID:        "session-profile-fail-closed",
					ClientRequestID:  "request-profile-" + profile.WireName(),
					InputText:        "深度核验",
					ReasoningProfile: profile,
					DefinitionOfDone: runruntime.DefinitionOfDone{
						Outcome:                  "回答存在",
						VerificationRequirements: []string{"answer_present"},
					},
				},
			)
			if err != nil {
				t.Fatalf("start run: %v", err)
			}
			executor := &neverRunExecutor{}
			queue.enqueue(run.RunID)
			worker := runruntime.NewDurableWorker(
				repository,
				queue,
				executor,
				"worker-profile-fail-closed-"+profile.WireName(),
			)
			if worked, processErr := worker.ProcessNext(context.Background()); processErr != nil || !worked {
				t.Fatalf("process run: worked=%t err=%v", worked, processErr)
			}
			stored, err := repository.Load(context.Background(), run.RunID)
			if err != nil {
				t.Fatalf("load run: %v", err)
			}
			if executor.called || stored.State != generated.AssistantRunStateFailed ||
				stored.TerminalReason != "reasoning_profile_rejected" {
				t.Fatalf("profile did not fail closed: called=%t run=%#v", executor.called, stored)
			}
		})
	}
}

func TestDurableWorkerPersistsPerRequirementMissingAndFailedVerdict(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		context.Background(),
		runruntime.StartCommand{
			UserID:          "user-verifier",
			SessionID:       "session-verifier",
			ClientRequestID: "request-verifier",
			InputText:       "逐条验收",
			DefinitionOfDone: runruntime.DefinitionOfDone{
				Outcome: "回答、证据和引用均通过",
				VerificationRequirements: []string{
					"answer_present",
					"evidence_present",
					"citations_present",
				},
			},
		},
	)
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	executor := &staticVerificationExecutor{
		build: func(request runruntime.ExecutionRequest) runruntime.ExecutionResult {
			answerRef := "assistant_run_item:answer:" + request.RunID
			return runruntime.ExecutionResult{
				AnswerText:   "只有答案，没有充分证据",
				ArtifactRefs: []string{answerRef, "artifact:evidence:1"},
				VerificationEvidence: []runruntime.VerificationEvidence{
					{
						Requirement:  "answer_present",
						Passed:       true,
						ArtifactRefs: []string{answerRef},
					},
					{
						Requirement:  "evidence_present",
						Passed:       false,
						ArtifactRefs: []string{"artifact:evidence:1"},
					},
				},
			}
		},
	}
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		executor,
		"worker-verifier",
	)
	if worked, processErr := worker.ProcessNext(context.Background()); processErr != nil || !worked {
		t.Fatalf("process run: worked=%t err=%v", worked, processErr)
	}
	stored, err := repository.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load run: %v", err)
	}
	if stored.State != generated.AssistantRunStateFailed {
		t.Fatalf("unmet Definition of Done completed: %#v", stored)
	}
	var verdict map[string]any
	for _, item := range stored.Items {
		if item.Kind == generated.AssistantRunItemKindEvidence {
			verdict = item.Payload
		}
	}
	// Platform-owned verifiers now emit failed (with fixSuggestion) for unmet
	// requirements instead of leaving them in missing.
	if verdict == nil ||
		!stringSliceContainsAny(verdict["failed"], "citations_present") ||
		!stringSliceContainsAny(verdict["failed"], "evidence_present") {
		t.Fatalf("per-requirement verdict=%#v", verdict)
	}
}

func TestDurableWorkerRunsCompletionBlockAndStopHooks(t *testing.T) {
	counts := map[runruntime.HookPhase]int{}
	registry, err := runruntime.NewHookRegistry(
		runruntime.RegisteredHook{Hook: hookStub{
			name: "completion-lifecycle",
			phases: []runruntime.HookPhase{
				runruntime.HookBeforeComplete,
				runruntime.HookOnBlocked,
				runruntime.HookOnStop,
			},
			invoke: func(input runruntime.HookInput) runruntime.HookResult {
				counts[input.Phase]++
				if input.Phase == runruntime.HookBeforeComplete {
					return runruntime.HookResult{
						Decision: runruntime.HookBlock,
						Reason:   "release policy rejected completion",
					}
				}
				return runruntime.HookResult{Decision: runruntime.HookAllow}
			},
		}},
	)
	if err != nil {
		t.Fatalf("new hook registry: %v", err)
	}
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		context.Background(),
		runruntime.StartCommand{
			UserID:          "user-hook-block",
			SessionID:       "session-hook-block",
			ClientRequestID: "request-hook-block",
			InputText:       "完成前受门禁检查",
		},
	)
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	profiles, err := runruntime.DefaultReasoningProfileCatalog()
	if err != nil {
		t.Fatalf("default profiles: %v", err)
	}
	queue.enqueue(run.RunID)
	worker := runruntime.NewConfiguredDurableWorker(
		repository,
		queue,
		&successfulRunExecutor{},
		"worker-hook-block",
		profiles,
		registry,
	)
	if worked, processErr := worker.ProcessNext(context.Background()); processErr != nil || !worked {
		t.Fatalf("process run: worked=%t err=%v", worked, processErr)
	}
	stored, err := repository.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load run: %v", err)
	}
	if stored.State != generated.AssistantRunStateFailed ||
		counts[runruntime.HookBeforeComplete] != 1 ||
		counts[runruntime.HookOnBlocked] != 1 ||
		counts[runruntime.HookOnStop] != 1 {
		t.Fatalf("hook lifecycle counts=%#v run=%#v", counts, stored)
	}
}

func TestDurableWorkerCompletionConfirmationCannotBecomeCompleted(t *testing.T) {
	registry, err := runruntime.NewHookRegistry(
		runruntime.RegisteredHook{Hook: hookStub{
			name:   "completion-confirmation",
			phases: []runruntime.HookPhase{runruntime.HookBeforeComplete},
			invoke: func(runruntime.HookInput) runruntime.HookResult {
				return runruntime.HookResult{
					Decision:        runruntime.HookRequireConfirmation,
					Reason:          "operator confirmation is required",
					ConfirmationRef: "confirmation:before-complete",
				}
			},
		}},
	)
	if err != nil {
		t.Fatalf("new hook registry: %v", err)
	}
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		context.Background(),
		runruntime.StartCommand{
			UserID:          "user-hook-confirm",
			SessionID:       "session-hook-confirm",
			ClientRequestID: "request-hook-confirm",
			InputText:       "完成前需要确认",
		},
	)
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	profiles, err := runruntime.DefaultReasoningProfileCatalog()
	if err != nil {
		t.Fatalf("default profiles: %v", err)
	}
	queue.enqueue(run.RunID)
	worker := runruntime.NewConfiguredDurableWorker(
		repository,
		queue,
		&hookConfirmationExecutor{
			confirmationRef: "confirmation:before-complete",
		},
		"worker-hook-confirm",
		profiles,
		registry,
	)
	if worked, processErr := worker.ProcessNext(context.Background()); processErr != nil || !worked {
		t.Fatalf("process run: worked=%t err=%v", worked, processErr)
	}
	stored, err := repository.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load run: %v", err)
	}
	if stored.State != generated.AssistantRunStateWaitingApproval ||
		stored.CompletedAt != nil || stored.Checkpoint == nil ||
		stored.Checkpoint.PendingApprovalRef != "confirmation:before-complete" ||
		stored.TaskGraph.AllCompleted() {
		t.Fatalf("completion confirmation did not wait safely: %#v", stored)
	}
}

type neverRunExecutor struct{ called bool }

func (e *neverRunExecutor) Execute(
	context.Context,
	runruntime.ExecutionRequest,
	func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	e.called = true
	return runruntime.ExecutionResult{}, errors.New("executor must not run")
}

type staticVerificationExecutor struct {
	build func(runruntime.ExecutionRequest) runruntime.ExecutionResult
}

type hookConfirmationExecutor struct {
	confirmationRef string
}

func (e *hookConfirmationExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	result, err := (&successfulRunExecutor{}).Execute(ctx, request, emit)
	if err != nil {
		return runruntime.ExecutionResult{}, err
	}
	continuationToken := testAssistantRunContinuationToken(
		request.RunID,
		e.confirmationRef,
	)
	result.Presentation["nodes"] = []map[string]any{{
		"nodeId": "root",
		"kind":   "confirmation_card",
		"action": map[string]any{
			"operation":     "ContinueAssistantToolUse",
			"objectTypeRef": "assistant_tool_use",
			"objectId":      e.confirmationRef,
			"payload": map[string]any{
				"decision":          "approved",
				"continuationToken": continuationToken,
				"deviceAction": map[string]any{
					"kind":           "assistant_completion_confirmation",
					"idempotencyKey": e.confirmationRef,
				},
			},
		},
	}}
	return result, nil
}

func testAssistantRunContinuationToken(runID string, toolUseID string) string {
	digest := sha256.Sum256([]byte(
		strings.TrimSpace(runID) + "\x00" + strings.TrimSpace(toolUseID),
	))
	return "ct_" + hex.EncodeToString(digest[:16])
}

func (e *staticVerificationExecutor) Execute(
	_ context.Context,
	request runruntime.ExecutionRequest,
	_ func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	return e.build(request), nil
}

func stringSliceContainsAny(value any, target string) bool {
	switch values := value.(type) {
	case []string:
		for _, value := range values {
			if value == target {
				return true
			}
		}
	case []any:
		for _, value := range values {
			if value == target {
				return true
			}
		}
	}
	return false
}
