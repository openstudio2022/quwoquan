package skillcontext

import (
	"context"
	"fmt"
	"math"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

// resolveFeedbackContext is the final model-facing privacy boundary for the
// feedback snapshot already frozen on AssistantRun. It deliberately rebuilds
// the value from a closed allowlist instead of serializing the persisted
// snapshot: consent identity, definition digest, source watermark and
// training eligibility therefore cannot enter ContextSnapshot or a prompt.
func resolveFeedbackContext(
	_ context.Context,
	run runruntime.Run,
) (application.ResolvedContext, error) {
	snapshot := run.FeedbackContextSnapshot
	decision := strings.TrimSpace(snapshot.Decision)
	if !validFeedbackContextDecision(decision) ||
		run.CreatedAt.IsZero() || strings.TrimSpace(run.RunID) == "" ||
		snapshot.WindowDays < 0 || snapshot.WindowDays > 90 ||
		snapshot.FeedbackSampleCount < 0 || snapshot.PositiveFeedbackCount < 0 ||
		snapshot.NegativeFeedbackCount < 0 || snapshot.TextFeedbackCount < 0 {
		return application.ResolvedContext{}, fmt.Errorf(
			"assistant feedback context snapshot is unavailable",
		)
	}
	if decision == "injected" && snapshot.WindowDays == 0 {
		return application.ResolvedContext{}, fmt.Errorf(
			"assistant feedback context snapshot is unavailable",
		)
	}

	value := map[string]any{
		"decision":            decision,
		"windowDays":          snapshot.WindowDays,
		"feedbackSampleCount": snapshot.FeedbackSampleCount,
	}
	policy := run.FrozenPolicySelection.LearningContextPolicy
	allowedSignals := feedbackStringSet(policy.AllowedSignals)
	if _, allowed := allowedSignals["feedback_counts"]; allowed {
		value["positiveFeedbackCount"] = snapshot.PositiveFeedbackCount
		value["negativeFeedbackCount"] = snapshot.NegativeFeedbackCount
		value["textFeedbackCount"] = snapshot.TextFeedbackCount
	}
	if _, allowed := allowedSignals["metric_summaries"]; allowed {
		metrics, err := modelFeedbackMetrics(
			snapshot.Metrics,
			feedbackStringSet(policy.AllowedMetricIDs),
		)
		if err != nil {
			return application.ResolvedContext{}, err
		}
		if len(metrics) > 0 {
			value["metrics"] = metrics
		}
	}
	if _, allowed := allowedSignals["top_reason_codes"]; allowed {
		reasons, err := modelFeedbackReasons(
			snapshot.Reasons,
			feedbackStringSet(policy.AllowedReasonCodes),
		)
		if err != nil {
			return application.ResolvedContext{}, err
		}
		if len(reasons) > 0 {
			value["reasons"] = reasons
		}
	}
	tokenCost := 32
	if metrics, ok := value["metrics"].([]map[string]any); ok {
		tokenCost += len(metrics) * 16
	}
	if reasons, ok := value["reasons"].([]map[string]any); ok {
		tokenCost += len(reasons) * 8
	}

	return application.ResolvedContext{
		Kind:        "memory",
		SourceRef:   "run:" + strings.TrimSpace(run.RunID) + ":feedback-context",
		Authority:   generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity: generated.AssistantContextSensitivityPrivate,
		CapturedAt:  run.CreatedAt.UTC(),
		TokenCost:   tokenCost,
		Value:       value,
	}, nil
}

func validFeedbackContextDecision(value string) bool {
	return assistantmodel.IsKnownAssistantFeedbackContextDecision(value)
}

func modelFeedbackMetrics(
	values []assistantmodel.AssistantFeedbackMetricSummary,
	allowlist map[string]struct{},
) ([]map[string]any, error) {
	result := make([]map[string]any, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, metric := range values {
		metricID := strings.TrimSpace(metric.MetricID)
		if _, allowed := allowlist[metricID]; !allowed {
			continue
		}
		if _, duplicate := seen[metricID]; duplicate || metric.SampleCount < 0 ||
			math.IsNaN(metric.Average) || math.IsInf(metric.Average, 0) ||
			math.IsNaN(metric.Latest) || math.IsInf(metric.Latest, 0) {
			return nil, fmt.Errorf("assistant feedback metric summary is invalid")
		}
		seen[metricID] = struct{}{}
		result = append(result, map[string]any{
			"metricId":    metricID,
			"sampleCount": metric.SampleCount,
			"average":     metric.Average,
			"latest":      metric.Latest,
		})
	}
	return result, nil
}

func modelFeedbackReasons(
	values []assistantmodel.AssistantFeedbackReasonSummary,
	allowlist map[string]struct{},
) ([]map[string]any, error) {
	result := make([]map[string]any, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, reason := range values {
		reasonCode := strings.TrimSpace(reason.ReasonCode)
		if _, allowed := allowlist[reasonCode]; !allowed {
			continue
		}
		if _, duplicate := seen[reasonCode]; duplicate || reason.Count < 0 {
			return nil, fmt.Errorf("assistant feedback reason summary is invalid")
		}
		seen[reasonCode] = struct{}{}
		result = append(result, map[string]any{
			"reasonCode": reasonCode,
			"count":      reason.Count,
		})
	}
	return result, nil
}

func feedbackStringSet(values []string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			result[value] = struct{}{}
		}
	}
	return result
}
