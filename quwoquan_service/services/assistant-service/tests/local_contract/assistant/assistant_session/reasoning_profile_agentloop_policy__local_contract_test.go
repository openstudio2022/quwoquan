// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
package local_contract

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

type policyCapableModel struct {
	mu            sync.Mutex
	reasoningCall map[string]int
	usageTokens   int64
	sequence      func(turnID string, call int) (string, map[string]any)
}

func (m *policyCapableModel) ModelExecutionCapabilities() orchestration.ModelExecutionCapabilities {
	return orchestration.ModelExecutionCapabilities{
		ToolCalling: true, ParallelTools: true, ReasoningEffort: true,
	}
}

func (m *policyCapableModel) Complete(
	_ context.Context,
	request orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	response := orchestration.ModelResponse{Usage: map[string]any{
		"totalTokens": m.usageTokens,
	}}
	switch request.Stage {
	case "reasoning":
		m.mu.Lock()
		if m.reasoningCall == nil {
			m.reasoningCall = map[string]int{}
		}
		m.reasoningCall[request.TurnID]++
		call := m.reasoningCall[request.TurnID]
		m.mu.Unlock()
		toolName := "web_search"
		input := map[string]any{"query": "bounded query"}
		if m.sequence != nil {
			toolName, input = m.sequence(request.TurnID, call)
		}
		response.StructuredDelta = map[string]any{
			"nextAction": "tool_call",
			"toolName":   toolName,
			"toolInput":  input,
		}
	case "evidence_processing":
		response.StructuredDelta = map[string]any{
			"evidenceSufficient": false,
			"retrievalProcessing": map[string]any{
				"processingSummary":  "仍需核验",
				"selectedKeyPoints":  []any{},
				"acceptedReferences": []any{},
			},
		}
	case "final":
		response.Text = "你可以根据当前已核验范围继续。"
		response.StructuredDelta = map[string]any{"userMarkdown": response.Text}
	}
	return response, nil
}

type policyTools struct {
	mu       sync.Mutex
	requests map[string][]orchestration.ToolRequest
	result   func(orchestration.ToolRequest) map[string]any
}

func (t *policyTools) ModelToolDeclarations(
	allowed []string,
) []ports.ModelToolDefinition {
	return canonicalTestModelToolDefinitions(allowed)
}

func (t *policyTools) Execute(
	_ context.Context,
	request orchestration.ToolRequest,
) (orchestration.ToolExecution, error) {
	t.mu.Lock()
	if t.requests == nil {
		t.requests = map[string][]orchestration.ToolRequest{}
	}
	t.requests[request.Turn.TurnID] = append(
		t.requests[request.Turn.TurnID],
		request,
	)
	t.mu.Unlock()
	result := map[string]any{
		"evidenceAssessment": map[string]any{
			"status":             "insufficient",
			"evidenceSufficient": false,
			"replanRequired":     true,
			"reason":             "evidence_gap",
			"sourceIds":          []string{},
		},
	}
	if t.result != nil {
		result = t.result(request)
	}
	return orchestration.ToolExecution{
		Requested: assistant.ToolUse{ToolName: request.ToolName, Input: request.Input},
		Completed: assistant.ToolUse{
			ToolName: request.ToolName,
			Input:    request.Input,
			Result:   result,
			Status:   "completed",
		},
	}, nil
}

func (t *policyTools) requestCount(turnID string) int {
	t.mu.Lock()
	defer t.mu.Unlock()
	return len(t.requests[turnID])
}

func reasoningProfile(
	t *testing.T,
	profile generated.AssistantReasoningProfile,
) runruntime.ReasoningProfileConfig {
	t.Helper()
	catalog, err := runruntime.DefaultReasoningProfileCatalog()
	if err != nil {
		t.Fatalf("default reasoning profiles: %v", err)
	}
	config, err := catalog.Resolve(profile)
	if err != nil {
		t.Fatalf("resolve reasoning profile %s: %v", profile, err)
	}
	return config
}

func policySkill(maxToolCalls int) orchestration.SkillSelection {
	return orchestration.SkillSelection{
		SkillID:         "knowledge_general",
		ProblemClass:    "complex_reasoning",
		SearchIntensity: "high",
		ToolPolicy:      []string{"web_search", "web_open", "web_find"},
		MaxToolCalls:    maxToolCalls,
	}
}

func policyTurn(turnID string) assistant.AssistantTurn {
	return assistant.AssistantTurn{
		TurnID: turnID,
		Input:  assistant.AssistantTurnInput{Text: "请完成有界研究"},
	}
}

func TestReasoningProfilesProduceImmutableProviderNeutralPolicies(t *testing.T) {
	model := &policyCapableModel{}
	profiles := []generated.AssistantReasoningProfile{
		generated.AssistantReasoningProfileFast,
		generated.AssistantReasoningProfileBalanced,
		generated.AssistantReasoningProfileDeep,
		generated.AssistantReasoningProfileBackgroundLong,
	}
	for _, profile := range profiles {
		profile := profile
		t.Run(profile.WireName(), func(t *testing.T) {
			config := reasoningProfile(t, profile)
			ctx, err := orchestration.WithAgentExecutionPolicy(
				t.Context(),
				config,
				model,
				orchestration.RuntimeExecutionCapabilities{
					Background: true,
					Compaction: true,
				},
			)
			if err != nil {
				t.Fatalf("negotiate %s: %v", profile, err)
			}
			policy, ok := orchestration.AgentExecutionPolicyFromContext(ctx)
			if !ok || policy.Profile != profile ||
				policy.MaxToolCalls != config.Budget.MaxToolCalls ||
				policy.MaxSubagents != config.Budget.MaxSubagents ||
				policy.ReflectionEverySteps != config.ReflectionEverySteps ||
				policy.SourceBreadth != config.SourceBreadth ||
				policy.SourceDepth != config.SourceDepth {
				t.Fatalf("policy=%+v config=%+v", policy, config)
			}
			policy.MaxToolCalls = 999
			again, _ := orchestration.AgentExecutionPolicyFromContext(ctx)
			if again.MaxToolCalls != config.Budget.MaxToolCalls {
				t.Fatalf("context policy was mutable: %+v", again)
			}
		})
	}
	if tier := orchestration.ResolveModelTier(orchestration.ModelRoutingInput{
		Stage:            ports.ModelStageReasoning,
		ProblemClass:     generated.ProblemClassComplexReasoning,
		SearchIntensity:  generated.SearchIntensityHigh,
		ReasoningProfile: generated.AssistantReasoningProfileFast,
	}); tier != ports.ModelTierFast {
		t.Fatalf("fast profile tier=%s", tier)
	}
	if tier := orchestration.ResolveModelTier(orchestration.ModelRoutingInput{
		Stage:            ports.ModelStageEvidenceProcessing,
		ProblemClass:     generated.ProblemClassSimpleQa,
		SearchIntensity:  generated.SearchIntensityLow,
		ReasoningProfile: generated.AssistantReasoningProfileDeep,
	}); tier != ports.ModelTierReasoning {
		t.Fatalf("deep profile tier=%s", tier)
	}
}

func TestReasoningProfileCapabilityNegotiationFailsClosed(t *testing.T) {
	background := reasoningProfile(t, generated.AssistantReasoningProfileBackgroundLong)
	_, err := orchestration.WithAgentExecutionPolicy(
		t.Context(),
		background,
		&policyCapableModel{},
		orchestration.RuntimeExecutionCapabilities{Background: true},
	)
	if !errors.Is(err, orchestration.ErrExecutionCapabilityUnavailable) {
		t.Fatalf("missing compaction must fail closed: %v", err)
	}
	_, err = orchestration.WithAgentExecutionPolicy(
		t.Context(),
		reasoningProfile(t, generated.AssistantReasoningProfileBalanced),
		uncapablePolicyModel{},
		orchestration.RuntimeExecutionCapabilities{},
	)
	if !errors.Is(err, orchestration.ErrExecutionCapabilityUnavailable) {
		t.Fatalf("unadvertised model capability must fail closed: %v", err)
	}
}

type policyCompletionBackend struct {
	mu    sync.Mutex
	tiers []ports.ModelTier
}

func (b *policyCompletionBackend) SupportsNativeToolCalling() bool { return false }

func (b *policyCompletionBackend) SupportsParallelModelRequests() bool { return true }

func (b *policyCompletionBackend) SupportsReasoningTier() bool { return true }

func (b *policyCompletionBackend) Complete(
	_ context.Context,
	request ports.ModelCompletionRequest,
) (ports.ModelCompletionResult, error) {
	b.mu.Lock()
	b.tiers = append(b.tiers, request.Tier)
	b.mu.Unlock()
	return ports.ModelCompletionResult{
		Content:      "你可以继续。",
		TierServed:   request.Tier,
		FinishReason: "stop",
	}, nil
}

func (b *policyCompletionBackend) Stream(
	ctx context.Context,
	request ports.ModelCompletionRequest,
	emit func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
	return b.Complete(ctx, request)
}

func TestProviderBridgeNegotiatesProfileWithoutProviderOrModelNames(t *testing.T) {
	backend := &policyCompletionBackend{}
	provider := orchestration.ProviderBackedModelProvider{Backend: backend}
	capabilities := provider.ModelExecutionCapabilities()
	if !capabilities.ToolCalling || !capabilities.ParallelTools ||
		!capabilities.ReasoningEffort {
		t.Fatalf("provider capabilities=%+v", capabilities)
	}
	for _, profile := range []generated.AssistantReasoningProfile{
		generated.AssistantReasoningProfileFast,
		generated.AssistantReasoningProfileDeep,
	} {
		ctx, err := orchestration.WithAgentExecutionPolicy(
			t.Context(),
			reasoningProfile(t, profile),
			provider,
			orchestration.RuntimeExecutionCapabilities{Compaction: true},
		)
		if err != nil {
			t.Fatalf("negotiate %s: %v", profile, err)
		}
		_, err = provider.Complete(ctx, orchestration.ModelRequest{
			TurnID:          "run-provider-" + profile.WireName(),
			Stage:           string(ports.ModelStageFinal),
			ProblemClass:    generated.ProblemClassSimpleQa.WireName(),
			SearchIntensity: generated.SearchIntensityLow.WireName(),
			UserQuestion:    "给我结论",
		})
		if err != nil {
			t.Fatalf("complete %s: %v", profile, err)
		}
	}
	backend.mu.Lock()
	defer backend.mu.Unlock()
	if len(backend.tiers) != 2 || backend.tiers[0] != ports.ModelTierFast ||
		backend.tiers[1] != ports.ModelTierReasoning {
		t.Fatalf("profile tiers=%v", backend.tiers)
	}
}

type uncapablePolicyModel struct{}

func (uncapablePolicyModel) Complete(
	context.Context,
	orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	return orchestration.ModelResponse{}, nil
}

func TestReasoningBudgetsAndReflectionAreIsolatedAcrossConcurrentRuns(t *testing.T) {
	model := &policyCapableModel{}
	tools := &policyTools{}
	runtime := orchestration.ReactRuntime{Model: model, Tools: tools}
	type runCase struct {
		turnID       string
		profile      generated.AssistantReasoningProfile
		wantTools    int
		reflectionAt int
	}
	cases := []runCase{
		{turnID: "run-fast", profile: generated.AssistantReasoningProfileFast, wantTools: 2, reflectionAt: 1},
		{turnID: "run-balanced", profile: generated.AssistantReasoningProfileBalanced, wantTools: 8, reflectionAt: 2},
	}
	results := make([]orchestration.ReactResult, len(cases))
	errs := make([]error, len(cases))
	var wait sync.WaitGroup
	for index, testCase := range cases {
		index, testCase := index, testCase
		wait.Add(1)
		go func() {
			defer wait.Done()
			ctx, err := orchestration.WithAgentExecutionPolicy(
				t.Context(),
				reasoningProfile(t, testCase.profile),
				model,
				orchestration.RuntimeExecutionCapabilities{
					Background: true, Compaction: true,
				},
			)
			if err != nil {
				errs[index] = err
				return
			}
			results[index], errs[index] = runtime.Run(
				ctx,
				policyTurn(testCase.turnID),
				policySkill(20),
			)
		}()
	}
	wait.Wait()
	for index, testCase := range cases {
		if errs[index] != nil {
			t.Fatalf("%s run: %v", testCase.profile, errs[index])
		}
		if got := tools.requestCount(testCase.turnID); got != testCase.wantTools {
			t.Fatalf("%s tool calls=%d want=%d", testCase.profile, got, testCase.wantTools)
		}
		if len(results[index].Steps) != testCase.wantTools {
			t.Fatalf("%s steps=%d", testCase.profile, len(results[index].Steps))
		}
		for stepIndex, step := range results[index].Steps {
			wantReflection := (stepIndex+1)%testCase.reflectionAt == 0
			if step.ReflectionApplied != wantReflection {
				t.Fatalf(
					"%s step=%d reflection=%t want=%t",
					testCase.profile,
					stepIndex+1,
					step.ReflectionApplied,
					wantReflection,
				)
			}
		}
	}
}

func TestReasoningProfileStopsWhenTokenBudgetIsExhausted(t *testing.T) {
	model := &policyCapableModel{usageTokens: 2}
	config := reasoningProfile(t, generated.AssistantReasoningProfileFast)
	config.Budget.MaxTokens = 1
	config.Budget.MaxCostUnits = 1
	ctx, err := orchestration.WithAgentExecutionPolicy(
		t.Context(),
		config,
		model,
		orchestration.RuntimeExecutionCapabilities{},
	)
	if err != nil {
		t.Fatalf("negotiate policy: %v", err)
	}
	_, err = (orchestration.ReactRuntime{
		Model: model,
		Tools: &policyTools{},
	}).Run(ctx, policyTurn("run-budget"), policySkill(20))
	if !errors.Is(err, orchestration.ErrExecutionBudgetExhausted) {
		t.Fatalf("token exhaustion must stop execution: %v", err)
	}
}

func TestReasoningProfileBoundsSourceBreadthAndNavigationDepth(t *testing.T) {
	model := &policyCapableModel{sequence: func(_ string, call int) (string, map[string]any) {
		if call == 1 {
			return "web_search", map[string]any{
				"query": "主查询",
				"searchQueries": []any{
					map[string]any{"dimension": "a", "query": "a"},
					map[string]any{"dimension": "b", "query": "b"},
					map[string]any{"dimension": "c", "query": "c"},
				},
			}
		}
		return "web_open", map[string]any{
			"target": map[string]any{"kind": "document_link", "value": "link-next"},
		}
	}}
	tools := &policyTools{result: func(request orchestration.ToolRequest) map[string]any {
		references := make([]map[string]any, 0, 5)
		for index := 1; index <= 5; index++ {
			references = append(references, map[string]any{
				"sourceId": fmt.Sprintf("source-%d", index),
			})
		}
		return map[string]any{
			"references": references,
			"evidenceAssessment": map[string]any{
				"status":             "insufficient",
				"evidenceSufficient": false,
				"replanRequired":     true,
				"reason":             "follow_document_link",
				"sourceIds":          []string{"source-1", "source-2", "source-3"},
			},
		}
	}}
	config := reasoningProfile(t, generated.AssistantReasoningProfileFast)
	config.SourceBreadth = 2
	config.SourceDepth = 1
	ctx, err := orchestration.WithAgentExecutionPolicy(
		t.Context(),
		config,
		model,
		orchestration.RuntimeExecutionCapabilities{},
	)
	if err != nil {
		t.Fatalf("negotiate policy: %v", err)
	}
	result, err := (orchestration.ReactRuntime{Model: model, Tools: tools}).Run(
		ctx,
		policyTurn("run-breadth"),
		policySkill(2),
	)
	if err != nil {
		t.Fatalf("breadth run: %v", err)
	}
	if len(result.Steps) == 0 {
		t.Fatal("breadth run has no steps")
	}
	queries, _ := result.Steps[0].Tool.Requested.Input["searchQueries"].([]any)
	if len(queries) != 1 {
		t.Fatalf("bounded searchQueries=%#v", queries)
	}
	references, _ := result.Steps[0].Tool.Completed.Result["references"].([]map[string]any)
	if len(references) != 2 {
		t.Fatalf("bounded references=%#v", references)
	}

	depthModel := &policyCapableModel{sequence: func(_ string, call int) (string, map[string]any) {
		if call == 1 {
			return "web_open", map[string]any{
				"target": map[string]any{"kind": "url", "value": "https://example.com/root"},
			}
		}
		return "web_open", map[string]any{
			"target": map[string]any{"kind": "document_link", "value": "link-child"},
		}
	}}
	depthTools := &policyTools{result: func(_ orchestration.ToolRequest) map[string]any {
		return map[string]any{
			"reference": map[string]any{"sourceId": "source-root"},
			"evidenceAssessment": map[string]any{
				"status":             "insufficient",
				"evidenceSufficient": false,
				"replanRequired":     true,
				"reason":             "follow_document_link",
				"sourceIds":          []string{"source-root"},
			},
		}
	}}
	depthCtx, err := orchestration.WithAgentExecutionPolicy(
		t.Context(),
		config,
		depthModel,
		orchestration.RuntimeExecutionCapabilities{},
	)
	if err != nil {
		t.Fatalf("negotiate depth policy: %v", err)
	}
	depthResult, err := (orchestration.ReactRuntime{
		Model: depthModel,
		Tools: depthTools,
	}).Run(depthCtx, policyTurn("run-depth"), policySkill(2))
	if err != nil {
		t.Fatalf("depth run: %v", err)
	}
	lastDepthStep := depthResult.Steps[len(depthResult.Steps)-1]
	if depthTools.requestCount("run-depth") != 1 || len(depthResult.Steps) < 2 ||
		lastDepthStep.DecisionRejection == nil ||
		lastDepthStep.DecisionRejection.ReasonCode != "source_depth_budget_exhausted" {
		t.Fatalf("depth boundary not enforced: requests=%d steps=%+v", depthTools.requestCount("run-depth"), depthResult.Steps)
	}
}

type capableSubagentModel struct{ *subagentStubModel }

func (m capableSubagentModel) ModelExecutionCapabilities() orchestration.ModelExecutionCapabilities {
	return orchestration.ModelExecutionCapabilities{
		ToolCalling: true, ParallelTools: true, ReasoningEffort: true,
	}
}

func TestReasoningProfileCapsSubagentFanout(t *testing.T) {
	model := capableSubagentModel{&subagentStubModel{}}
	loop := subagentLoop(t, model)
	fastCtx, err := loop.WithDurableReasoningProfile(
		t.Context(),
		reasoningProfile(t, generated.AssistantReasoningProfileFast),
	)
	if err != nil {
		t.Fatalf("fast policy: %v", err)
	}
	fastEvents, failure, err := loop.RunTurn(fastCtx, multiSkillTurn())
	if err != nil || failure != nil {
		t.Fatalf("fast run: failure=%+v err=%v", failure, err)
	}
	if plans, ok := completedPayload(t, fastEvents)["subagentPlan"].([]map[string]any); ok && len(plans) > 0 {
		t.Fatalf("fast profile must not fan out: %#v", plans)
	}

	balancedCtx, err := loop.WithDurableReasoningProfile(
		t.Context(),
		reasoningProfile(t, generated.AssistantReasoningProfileBalanced),
	)
	if err != nil {
		t.Fatalf("balanced policy: %v", err)
	}
	balancedEvents, failure, err := loop.RunTurn(balancedCtx, multiSkillTurn())
	if err != nil || failure != nil {
		t.Fatalf("balanced run: failure=%+v err=%v", failure, err)
	}
	plans, ok := completedPayload(t, balancedEvents)["subagentPlan"].([]map[string]any)
	if !ok || len(plans) != 2 {
		t.Fatalf("balanced profile plans=%#v", plans)
	}
	totalToolBudget := 0
	for _, plan := range plans {
		budget, _ := plan["toolBudget"].(int)
		totalToolBudget += budget
	}
	if totalToolBudget > reasoningProfile(t, generated.AssistantReasoningProfileBalanced).Budget.MaxToolCalls {
		t.Fatalf("subagents copied root budget: total=%d", totalToolBudget)
	}
}
