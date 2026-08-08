package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	runorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func buildProductionRunHooks(
	agentLoop *runorchestration.AgentLoop,
) (*runruntime.HookRegistry, error) {
	if agentLoop == nil || agentLoop.React.Model == nil {
		return nil, errors.New("assistant verification model is unavailable")
	}
	model := runruntime.ConstrainedVerificationModelFunc(func(
		ctx context.Context,
		request runruntime.ConstrainedVerificationRequest,
	) (runruntime.ConstrainedVerificationResponse, error) {
		response, err := agentLoop.React.Model.Complete(ctx, runorchestration.ModelRequest{
			Stage:            "verification",
			ProblemClass:     string(assistantgenerated.ProblemClassComplexReasoning),
			SearchIntensity:  string(assistantgenerated.SearchIntensityLow),
			ReasoningProfile: assistantgenerated.AssistantReasoningProfileBalanced,
			Prompt: "只根据冻结目标、公开答案、过程摘要和 artifact refs 验证单个完成要求。" +
				"只返回 passed、artifactRefs、summary、fixSuggestion 四个结构化字段，不执行工具，也不改写要求。",
			Observation: map[string]any{
				"requirement":  request.Requirement,
				"goal":         request.Goal,
				"constraints":  append([]string{}, request.Constraints...),
				"answerText":   request.AnswerText,
				"processNotes": append([]string{}, request.ProcessNotes...),
				"artifactRefs": append([]string{}, request.ArtifactRefs...),
			},
		})
		if err != nil {
			return runruntime.ConstrainedVerificationResponse{}, err
		}
		if err := runorchestration.ConsumeExecutionModelResponse(
			ctx,
			response,
		); err != nil {
			return runruntime.ConstrainedVerificationResponse{}, err
		}
		return decodeConstrainedVerification(response.StructuredDelta)
	})
	return runruntime.NewProductionHookRegistry(
		model,
		runruntime.SlogHookAuditSink{Logger: slog.Default()},
	)
}

func decodeConstrainedVerification(
	value map[string]any,
) (runruntime.ConstrainedVerificationResponse, error) {
	if len(value) == 0 {
		return runruntime.ConstrainedVerificationResponse{}, errors.New("verification response is empty")
	}
	allowed := map[string]struct{}{
		"passed": {}, "artifactRefs": {}, "summary": {}, "fixSuggestion": {},
	}
	for key := range value {
		if _, ok := allowed[key]; !ok {
			return runruntime.ConstrainedVerificationResponse{}, fmt.Errorf(
				"verification response has unknown field %q",
				key,
			)
		}
	}
	passed, ok := value["passed"].(bool)
	if !ok {
		return runruntime.ConstrainedVerificationResponse{}, errors.New("verification response passed must be bool")
	}
	summary, ok := value["summary"].(string)
	if !ok || strings.TrimSpace(summary) == "" {
		return runruntime.ConstrainedVerificationResponse{}, errors.New("verification response summary is required")
	}
	artifactRefs, err := verificationStringSlice(value["artifactRefs"])
	if err != nil {
		return runruntime.ConstrainedVerificationResponse{}, err
	}
	fixSuggestion := ""
	if raw, exists := value["fixSuggestion"]; exists {
		var valid bool
		fixSuggestion, valid = raw.(string)
		if !valid {
			return runruntime.ConstrainedVerificationResponse{}, errors.New("verification response fixSuggestion must be string")
		}
	}
	if !passed && strings.TrimSpace(fixSuggestion) == "" {
		return runruntime.ConstrainedVerificationResponse{}, errors.New("rejected verification requires a fix suggestion")
	}
	return runruntime.ConstrainedVerificationResponse{
		Passed:        passed,
		ArtifactRefs:  artifactRefs,
		Summary:       strings.TrimSpace(summary),
		FixSuggestion: strings.TrimSpace(fixSuggestion),
	}, nil
}

func verificationStringSlice(value any) ([]string, error) {
	if value == nil {
		return nil, nil
	}
	result := []string{}
	switch typed := value.(type) {
	case []string:
		result = append(result, typed...)
	case []any:
		for _, item := range typed {
			text, ok := item.(string)
			if !ok {
				return nil, errors.New("verification response artifactRefs must contain strings")
			}
			result = append(result, text)
		}
	default:
		return nil, errors.New("verification response artifactRefs must be a list")
	}
	seen := map[string]struct{}{}
	normalized := make([]string, 0, len(result))
	for _, item := range result {
		item = strings.TrimSpace(item)
		if item == "" {
			return nil, errors.New("verification response artifactRefs contains an empty value")
		}
		if _, duplicate := seen[item]; duplicate {
			continue
		}
		seen[item] = struct{}{}
		normalized = append(normalized, item)
	}
	return normalized, nil
}
