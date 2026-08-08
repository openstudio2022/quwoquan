package orchestration

import (
	"fmt"
	"strings"

	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/reasoning"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func replanReason(observation react.Observation, budget react.Budget) string {
	if !observation.Empty {
		return "observation_sufficient"
	}
	if budget.MaxIterations <= 0 || budget.MaxToolCalls <= 0 {
		return "budget_exhausted"
	}
	return "observation_empty"
}

func stringSliceContains(values []string, target string) bool {
	target = strings.TrimSpace(target)
	for _, value := range values {
		if strings.TrimSpace(value) == target {
			return true
		}
	}
	return false
}

func guardAllowedTools(
	runtimeToolPolicy []string,
	guard react.ToolExecutionGuard,
) []string {
	allowed := make([]string, 0, len(runtimeToolPolicy))
	for _, toolName := range runtimeToolPolicy {
		toolName = strings.TrimSpace(toolName)
		if toolName == "" || guard.Allow(toolName) != nil {
			continue
		}
		allowed = append(allowed, toolName)
	}
	return allowed
}

func toolDecisionRejectionObservation(
	rejection *react.ToolDecisionRejection,
) map[string]any {
	if rejection == nil {
		return nil
	}
	return map[string]any{
		"kind":          "decision_rejected",
		"status":        "rejected",
		"reasonCode":    strings.TrimSpace(rejection.ReasonCode),
		"requestedTool": strings.TrimSpace(rejection.RequestedTool),
		"allowedTools":  append([]string(nil), rejection.AllowedTools...),
		"retryable":     rejection.Retryable,
	}
}

func rejectNonAllowHookDecision(
	phase runruntime.HookPhase,
	result runruntime.HookResult,
) error {
	switch result.Decision {
	case runruntime.HookAllow:
		return nil
	case runruntime.HookBlock, runruntime.HookRequireConfirmation:
		return hookDecisionError(phase, result)
	default:
		return fmt.Errorf("%s hook returned an invalid decision", phase)
	}
}

func hookDecisionError(
	phase runruntime.HookPhase,
	result runruntime.HookResult,
) error {
	reason := strings.TrimSpace(result.Reason)
	if reason == "" {
		reason = "lifecycle policy rejected execution"
	}
	return fmt.Errorf("%s hook %s: %s", phase, result.Decision, reason)
}

func hookString(data map[string]any, key string) string {
	if data == nil {
		return ""
	}
	value, _ := data[key].(string)
	return strings.TrimSpace(value)
}

func hookObjectMap(data map[string]any, key string) map[string]any {
	if data == nil {
		return nil
	}
	return cloneObjectMap(objectMap(data[key]))
}

func cloneObjectMap(value map[string]any) map[string]any {
	if value == nil {
		return nil
	}
	cloned := make(map[string]any, len(value))
	for key, item := range value {
		cloned[key] = item
	}
	return cloned
}
