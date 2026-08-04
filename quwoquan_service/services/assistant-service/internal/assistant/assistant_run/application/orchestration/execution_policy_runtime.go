package orchestration

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
)

type executionUsageBudget struct {
	policy  AgentExecutionPolicy
	enabled bool
	state   *executionBudgetConsumptionState
}

func newExecutionUsageBudget(
	ctx context.Context,
	policy AgentExecutionPolicy,
	enabled bool,
) *executionUsageBudget {
	state, _ := executionBudgetConsumptionStateFromContext(ctx)
	if state == nil {
		state = &executionBudgetConsumptionState{}
	}
	return &executionUsageBudget{
		policy:  policy,
		enabled: enabled,
		state:   state,
	}
}

func (b *executionUsageBudget) consume(response ModelResponse) error {
	if b == nil || !b.enabled {
		return nil
	}
	tokens, costUnits := modelResponseConsumption(response)
	return b.state.consumeModel(b.policy, tokens, costUnits)
}

func (b *executionUsageBudget) reserveToolCall() (
	*executionToolCallReservation,
	error,
) {
	if b == nil || !b.enabled {
		return &executionToolCallReservation{}, nil
	}
	return b.state.reserveToolCall(b.policy)
}

func consumeExecutionModelResponse(
	ctx context.Context,
	response ModelResponse,
) error {
	policy, enabled := executionPolicyFromContext(ctx)
	if !enabled {
		return nil
	}
	state, ok := executionBudgetConsumptionStateFromContext(ctx)
	if !ok {
		return nil
	}
	tokens, costUnits := modelResponseConsumption(response)
	return state.consumeModel(policy, tokens, costUnits)
}

func modelResponseConsumption(response ModelResponse) (int64, int64) {
	tokens := usageInt64(response.Usage, "totalTokens")
	if tokens <= 0 {
		tokens = usageInt64(response.Usage, "promptTokens") +
			usageInt64(response.Usage, "completionTokens")
	}
	costUnits := usageInt64(response.Usage, "costUnits")
	if costUnits <= 0 {
		// A provider-neutral cost unit defaults to one token when the adapter
		// cannot report a monetary unit. The profile catalog deliberately uses
		// the same scale for MaxTokens and MaxCostUnits.
		costUnits = tokens
	}
	return tokens, costUnits
}

func usageInt64(usage map[string]any, key string) int64 {
	if usage == nil {
		return 0
	}
	switch value := usage[key].(type) {
	case int:
		return int64(value)
	case int32:
		return int64(value)
	case int64:
		return value
	case float32:
		return int64(value)
	case float64:
		return int64(value)
	default:
		return 0
	}
}

type executionExplorationBudget struct {
	policy          AgentExecutionPolicy
	enabled         bool
	sourceIDs       map[string]struct{}
	navigationDepth int
}

func newExecutionExplorationBudget(
	ctx context.Context,
	policy AgentExecutionPolicy,
	enabled bool,
) *executionExplorationBudget {
	budget := &executionExplorationBudget{
		policy:    policy,
		enabled:   enabled,
		sourceIDs: map[string]struct{}{},
	}
	if state, _, ok := runruntime.RestoreContextExecution(ctx); ok {
		budget.navigationDepth = state.NavigationDepth
		for _, sourceID := range state.SourceIDs {
			budget.sourceIDs[sourceID] = struct{}{}
		}
	}
	return budget
}

func (b *executionExplorationBudget) snapshot() ([]string, int) {
	if b == nil {
		return nil, 0
	}
	sourceIDs := make([]string, 0, len(b.sourceIDs))
	for sourceID := range b.sourceIDs {
		sourceIDs = append(sourceIDs, sourceID)
	}
	sort.Strings(sourceIDs)
	return sourceIDs, b.navigationDepth
}

// prepareTool bounds model-provided parallel search queries and rejects only
// the concrete navigation that would exceed the frozen source/depth budget.
// It is deliberately side-effect free because PostPlan and PreToolUse hook
// transformations must each be revalidated. The budget advances only after the
// final transformed tool input is actually executed.
func (b *executionExplorationBudget) prepareTool(
	research toolpkg.ResearchPolicy,
	input map[string]any,
) (map[string]any, string) {
	if b == nil || !b.enabled {
		return input, ""
	}
	bounded := clonePolicyMap(input)
	switch research.ResolvedOperation() {
	case toolpkg.ResearchOperationDiscover:
		if len(b.sourceIDs) >= b.policy.MaxSources {
			return bounded, "source_budget_exhausted"
		}
		parallelInputField := strings.TrimSpace(research.ParallelInputField)
		if parallelInputField == "" {
			return bounded, ""
		}
		if queries, ok := bounded[parallelInputField].([]any); ok {
			limit := b.policy.SourceBreadth - 1 // query is the first branch.
			if limit < 0 {
				limit = 0
			}
			if len(queries) > limit {
				bounded[parallelInputField] = append([]any(nil), queries[:limit]...)
			}
		} else if queries, ok := bounded[parallelInputField].([]map[string]any); ok {
			limit := b.policy.SourceBreadth - 1
			if limit < 0 {
				limit = 0
			}
			if len(queries) > limit {
				cloned := make([]map[string]any, 0, limit)
				for _, query := range queries[:limit] {
					cloned = append(cloned, clonePolicyMap(query))
				}
				bounded[parallelInputField] = cloned
			}
		}
	case toolpkg.ResearchOperationNavigate:
		target, _ := bounded[strings.TrimSpace(research.TargetInputField)].(map[string]any)
		kind := strings.TrimSpace(fmt.Sprint(
			target[strings.TrimSpace(research.TargetKindField)],
		))
		value := strings.TrimSpace(fmt.Sprint(
			target[strings.TrimSpace(research.TargetValueField)],
		))
		if len(b.sourceIDs) >= b.policy.MaxSources {
			_, knownSource := b.sourceIDs[value]
			if !stringSliceContains(
				research.ReusableSourceTargetKinds,
				kind,
			) || !knownSource {
				return bounded, "source_budget_exhausted"
			}
		}
		if stringSliceContains(research.ChildTargetKinds, kind) {
			if b.navigationDepth+1 > b.policy.SourceDepth {
				return bounded, "source_depth_budget_exhausted"
			}
		}
	}
	return bounded, ""
}

func (b *executionExplorationBudget) commitTool(
	research toolpkg.ResearchPolicy,
	input map[string]any,
) {
	if b == nil || !b.enabled {
		return
	}
	switch research.ResolvedOperation() {
	case toolpkg.ResearchOperationDiscover:
		b.navigationDepth = 0
	case toolpkg.ResearchOperationNavigate:
		target, _ := input[strings.TrimSpace(research.TargetInputField)].(map[string]any)
		kind := strings.TrimSpace(fmt.Sprint(
			target[strings.TrimSpace(research.TargetKindField)],
		))
		if stringSliceContains(research.ChildTargetKinds, kind) {
			b.navigationDepth++
			return
		}
		b.navigationDepth = 1
	}
}

func (b *executionExplorationBudget) repairTools(
	values []string,
	metadataByName map[string]toolpkg.Metadata,
) []string {
	if b == nil || !b.enabled || len(b.sourceIDs) < b.policy.MaxSources {
		return append([]string(nil), values...)
	}
	allowed := make([]string, 0, len(values))
	for _, value := range values {
		metadata, found := metadataByName[strings.TrimSpace(value)]
		if !found {
			continue
		}
		switch metadata.Research.ResolvedOperation() {
		case toolpkg.ResearchOperationDiscover:
			continue
		case toolpkg.ResearchOperationNavigate:
			// A navigate tool can still reopen a source already accepted into the
			// ledger. Without a reusable target kind it can only exceed the budget.
			if len(metadata.Research.ReusableSourceTargetKinds) == 0 {
				continue
			}
		}
		allowed = append(allowed, value)
	}
	return allowed
}

// boundResult limits source material before it enters model context, public
// process projection, or a checkpoint. The source ledger may retain the full
// fetch result, but AgentLoop only observes the frozen profile allowance.
func (b *executionExplorationBudget) boundResult(
	research toolpkg.ResearchPolicy,
	result map[string]any,
) map[string]any {
	operation := research.ResolvedOperation()
	if b == nil || !b.enabled || result == nil ||
		operation == toolpkg.ResearchOperationNone {
		return result
	}
	allowNewSources := operation == toolpkg.ResearchOperationDiscover ||
		operation == toolpkg.ResearchOperationNavigate
	bounded := clonePolicyMap(result)
	if references, ok := referenceMaps(bounded["references"]); ok {
		limit := b.policy.SourceBreadth
		if limit < 0 {
			limit = 0
		}
		accepted := make([]map[string]any, 0, limit)
		for _, reference := range references {
			if len(accepted) == limit {
				break
			}
			if b.acceptReference(reference, allowNewSources) {
				accepted = append(accepted, clonePolicyMap(reference))
			}
		}
		bounded["references"] = accepted
	}
	if reference, ok := bounded["reference"].(map[string]any); ok {
		if !b.acceptReference(reference, allowNewSources) {
			delete(bounded, "reference")
		}
	}
	if sourceID := strings.TrimSpace(fmt.Sprint(bounded["sourceId"])); sourceID != "" && sourceID != "<nil>" {
		if !b.acceptSourceID(sourceID, allowNewSources) {
			delete(bounded, "sourceId")
		}
	}
	if assessment, ok := bounded["evidenceAssessment"].(map[string]any); ok {
		assessment["sourceIds"] = b.acceptedSourceIDs(
			assessment["sourceIds"],
			allowNewSources,
		)
	}
	return bounded
}

func (b *executionExplorationBudget) acceptReference(
	reference map[string]any,
	allowNew bool,
) bool {
	if reference == nil {
		return false
	}
	sourceID := strings.TrimSpace(fmt.Sprint(reference["sourceId"]))
	if sourceID == "" || sourceID == "<nil>" {
		return true
	}
	return b.acceptSourceID(sourceID, allowNew)
}

func (b *executionExplorationBudget) acceptSourceID(
	sourceID string,
	allowNew bool,
) bool {
	if _, exists := b.sourceIDs[sourceID]; exists {
		return true
	}
	if !allowNew || len(b.sourceIDs) >= b.policy.MaxSources {
		return false
	}
	b.sourceIDs[sourceID] = struct{}{}
	return true
}

func (b *executionExplorationBudget) acceptedSourceIDs(
	value any,
	allowNew bool,
) []string {
	values := stringValuesForPolicy(value)
	accepted := make([]string, 0, len(values))
	for _, sourceID := range values {
		if b.acceptSourceID(sourceID, allowNew) {
			accepted = append(accepted, sourceID)
		}
	}
	return accepted
}

func referenceMaps(value any) ([]map[string]any, bool) {
	switch values := value.(type) {
	case []map[string]any:
		return values, true
	case []any:
		result := make([]map[string]any, 0, len(values))
		for _, value := range values {
			entry, ok := value.(map[string]any)
			if ok {
				result = append(result, entry)
			}
		}
		return result, true
	default:
		return nil, false
	}
}

func stringValuesForPolicy(value any) []string {
	switch values := value.(type) {
	case []string:
		return append([]string(nil), values...)
	case []any:
		result := make([]string, 0, len(values))
		for _, value := range values {
			if text, ok := value.(string); ok && strings.TrimSpace(text) != "" {
				result = append(result, strings.TrimSpace(text))
			}
		}
		return result
	default:
		return nil
	}
}

func clonePolicyMap(value map[string]any) map[string]any {
	if value == nil {
		return nil
	}
	result := make(map[string]any, len(value))
	for key, item := range value {
		result[key] = clonePolicyValue(item)
	}
	return result
}

func clonePolicyValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return clonePolicyMap(typed)
	case []map[string]any:
		result := make([]map[string]any, 0, len(typed))
		for _, item := range typed {
			result = append(result, clonePolicyMap(item))
		}
		return result
	case []any:
		result := make([]any, len(typed))
		for index, item := range typed {
			result[index] = clonePolicyValue(item)
		}
		return result
	case []string:
		return append([]string(nil), typed...)
	default:
		return typed
	}
}
