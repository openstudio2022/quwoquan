// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package local_contract

import (
	"context"
	"sync"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

type compactionPolicyModel struct {
	mu             sync.Mutex
	reasoningCalls int
	compactions    int
}

func (*compactionPolicyModel) ModelExecutionCapabilities() orchestration.ModelExecutionCapabilities {
	return orchestration.ModelExecutionCapabilities{
		ToolCalling: true, ParallelTools: true, ReasoningEffort: true,
	}
}

func (m *compactionPolicyModel) Complete(
	_ context.Context,
	request orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	response := orchestration.ModelResponse{Usage: map[string]any{"totalTokens": int64(1)}}
	switch request.Stage {
	case "reasoning":
		m.mu.Lock()
		m.reasoningCalls++
		call := m.reasoningCalls
		m.mu.Unlock()
		if call == 2 {
			response.StructuredDelta = map[string]any{"nextAction": "answer"}
			return response, nil
		}
		response.StructuredDelta = map[string]any{
			"nextAction": "tool_call",
			"toolName":   "web_search",
			"toolInput":  map[string]any{"query": "官方恢复测试"},
		}
	case "evidence_processing":
		response.StructuredDelta = map[string]any{
			"evidenceSufficient": false,
			"retrievalProcessing": map[string]any{
				"processingSummary":  "仍需继续核验",
				"selectedKeyPoints":  []any{},
				"acceptedReferences": []any{},
			},
		}
	case "compaction":
		m.mu.Lock()
		m.compactions++
		m.mu.Unlock()
		response.Text = "当前目标是核验公开来源；已接受一个来源；仍需完成综合。"
		response.StructuredDelta = map[string]any{"summaryText": response.Text}
	case "final":
		response.Text = "你可以继续使用已恢复的来源账本。"
		response.StructuredDelta = map[string]any{"userMarkdown": response.Text}
	}
	return response, nil
}

type compactionHook struct {
	mu     sync.Mutex
	phases []runruntime.HookPhase
}

func (*compactionHook) Name() string { return "context-compaction-audit" }
func (*compactionHook) Phases() []runruntime.HookPhase {
	return []runruntime.HookPhase{
		runruntime.HookPreCompact,
		runruntime.HookPostCompact,
	}
}
func (h *compactionHook) Invoke(
	_ context.Context,
	input runruntime.HookInput,
) (runruntime.HookResult, error) {
	h.mu.Lock()
	h.phases = append(h.phases, input.Phase)
	h.mu.Unlock()
	return runruntime.HookResult{
		Decision: runruntime.HookAllow,
		Data:     input.Data,
	}, nil
}

func TestAgentLoopCompactsAtProfileBoundaryAndRestoresExplorationLedger(
	t *testing.T,
) {
	model := &compactionPolicyModel{}
	tools := &policyTools{result: func(orchestration.ToolRequest) map[string]any {
		return map[string]any{
			"references": []map[string]any{{
				"sourceId": "source:official:only",
				"title":    "官方来源",
			}},
			"evidenceAssessment": map[string]any{
				"status":             "insufficient",
				"evidenceSufficient": false,
				"replanRequired":     true,
				"reason":             "evidence_gap",
				"sourceIds":          []string{"source:official:only"},
			},
		}
	}}
	profile := reasoningProfile(t, generated.AssistantReasoningProfileDeep)
	profile.Budget.MaxSources = 1
	profile.Budget.MaxToolCalls = 2
	profile.CheckpointEvery = time.Minute
	now := time.Date(2026, 8, 4, 8, 0, 0, 0, time.UTC)
	var persistedState runruntime.ContextExecutionState
	var persistedCompaction *runruntime.ContextCompactionCheckpoint
	var persistedSequence int64
	sink := func(
		_ context.Context,
		receipt runruntime.ContextProgressReceipt,
	) error {
		persistedState = receipt.State
		persistedSequence = receipt.Sequence
		if receipt.Compaction != nil {
			copy := *receipt.Compaction
			persistedCompaction = &copy
		}
		return nil
	}
	ctx, err := runruntime.WithContextCompactionRuntime(
		t.Context(),
		runruntime.ContextCompactionRuntimeConfig{
			Scope:           "run:context-agentloop:goal:1",
			CheckpointEvery: profile.CheckpointEvery,
			StartedAt:       now.Add(-2 * time.Minute),
			Now:             func() time.Time { return now },
			Sink:            sink,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	ctx, err = orchestration.WithAgentExecutionPolicy(
		ctx,
		profile,
		model,
		orchestration.RuntimeExecutionCapabilities{
			Background: true,
			Compaction: true,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	hook := &compactionHook{}
	registry, err := runruntime.NewHookRegistry(
		runruntime.RegisteredHook{Hook: hook},
	)
	if err != nil {
		t.Fatal(err)
	}
	ctx = runruntime.WithExecutionHooks(ctx, registry, runruntime.Run{
		RunID: "context-agentloop",
		DefinitionOfDone: runruntime.DefinitionOfDone{
			Outcome:  "完成恢复测试",
			FrozenAt: now,
		},
	})
	ctx = runruntime.WithContextCompactionBoundary(ctx)
	runtime := orchestration.ReactRuntime{Model: model, Tools: tools}
	turn := policyTurn("context-agentloop-turn")
	result, err := runtime.Run(ctx, turn, policySkill(2))
	if err != nil {
		t.Fatal(err)
	}
	if result.FinalText == "" || persistedCompaction == nil ||
		persistedCompaction.ContextRevision != 1 ||
		persistedState.PlanCursor != 2 ||
		persistedState.ToolIteration != 1 ||
		len(persistedState.SourceIDs) != 1 {
		t.Fatalf(
			"first execution did not persist compacted state: result=%#v state=%#v checkpoint=%#v",
			result,
			persistedState,
			persistedCompaction,
		)
	}
	hook.mu.Lock()
	phases := append([]runruntime.HookPhase(nil), hook.phases...)
	hook.mu.Unlock()
	if len(phases) != 2 || phases[0] != runruntime.HookPreCompact ||
		phases[1] != runruntime.HookPostCompact {
		t.Fatalf("compaction hooks=%v", phases)
	}

	restoredCtx, err := runruntime.WithContextCompactionRuntime(
		t.Context(),
		runruntime.ContextCompactionRuntimeConfig{
			Scope:                  "run:context-agentloop:goal:1",
			CheckpointEvery:        profile.CheckpointEvery,
			StartedAt:              now.Add(-2 * time.Minute),
			InitialState:           persistedState,
			InitialCompaction:      persistedCompaction,
			InitialReceiptSequence: persistedSequence,
			Now:                    func() time.Time { return now },
			Sink:                   sink,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	restoredCtx, err = orchestration.WithAgentExecutionPolicy(
		restoredCtx,
		profile,
		model,
		orchestration.RuntimeExecutionCapabilities{
			Background: true,
			Compaction: true,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	restoredCtx = runruntime.WithContextCompactionBoundary(restoredCtx)
	if _, err := runtime.Run(restoredCtx, turn, policySkill(2)); err != nil {
		t.Fatal(err)
	}
	if tools.requestCount(turn.TurnID) != 1 {
		t.Fatalf(
			"restored source ledger allowed a second discovery call: %d",
			tools.requestCount(turn.TurnID),
		)
	}
	model.mu.Lock()
	compactions := model.compactions
	reasoningCalls := model.reasoningCalls
	model.mu.Unlock()
	if compactions != 1 || reasoningCalls != 3 {
		t.Fatalf(
			"model calls after recovery reasoning=%d compaction=%d",
			reasoningCalls,
			compactions,
		)
	}
}
