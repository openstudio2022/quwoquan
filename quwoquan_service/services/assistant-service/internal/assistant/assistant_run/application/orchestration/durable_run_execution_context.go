package orchestration

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

func executionTurn(request runruntime.ExecutionRequest) assistant.AssistantTurn {
	pageContext := decodeExecutionPageContext(request.ContextSnapshot)
	intersectionEvidence := decodeAuthorizedIntersectionEvidence(
		request.ContextSnapshot["authorizedIntersectionEvidence"],
	)
	trigger := decodeExecutionTrigger(request.Trigger)
	turnType := "user"
	if trigger.Type != "user_message" {
		turnType = "proactive"
	}
	sessionPreferences := append(
		[]preferencemodel.AssistantPreferenceSnapshot(nil),
		request.SessionPreferences...,
	)
	longTermPreferences := append(
		[]preferencemodel.AssistantPreferenceSnapshot(nil),
		request.LongTermPreferences...,
	)
	contextSummary := ProjectExecutionContextSummary(
		request.RunID,
		request.SessionContinuity,
		request.ConfirmedSlots,
	)
	if sharedAssistantSurface(request.RequestContext.SurfaceKind) {
		// 群聊/圈子只可使用 surface 内共享事实。个人偏好与长期记忆即使
		// 被旧 checkpoint 携带，也必须在构造执行 turn 时物理退出。
		sessionPreferences = nil
		longTermPreferences = nil
		contextSummary = ProjectExecutionContextSummary(
			request.RunID,
			nil,
			request.ConfirmedSlots,
		)
	}
	contextSummary = ProjectVerificationRepairContextSummary(
		request.RunID,
		contextSummary,
		request.TaskGraph,
	)
	return assistant.AssistantTurn{
		TurnID:         "execution:" + request.RunID,
		ExecutionRunID: request.RunID,
		SessionID:      request.SessionID,
		UserID:         request.UserID,
		TurnType:       turnType,
		Status:         "running",
		SkillID:        request.RequestedSkillID,
		DomainID:       request.RequestedDomainID,
		Input: assistant.AssistantTurnInput{
			Text: request.Goal,
		},
		PageContext:          pageContext,
		IntersectionEvidence: intersectionEvidence,
		Trigger:              trigger,
		ClientRequestID:      request.IdempotencyPrefix,
		RequestContext: assistant.AssistantRunRequestContext{
			ClientSessionID: request.RequestContext.ClientSessionID,
			PageID:          request.RequestContext.PageID,
			SurfaceKind:     request.RequestContext.SurfaceKind,
			SurfaceID:       request.RequestContext.SurfaceID,
			RouteID:         request.RequestContext.RouteID,
			OperationID:     request.RequestContext.OperationID,
			PersonaID:       request.RequestContext.PersonaID,
			TraceID:         request.RequestContext.TraceID,
		},
		SessionPreferences:      sessionPreferences,
		LongTermPreferences:     longTermPreferences,
		FeedbackContextSnapshot: request.FeedbackContextSnapshot.Clone(),
		ContextSummary:          contextSummary,
		TraceID:                 request.RunID,
		CreatedAt:               executionStartTime(request.CreatedAt),
		FrozenPolicySelection: assistant.AssistantFrozenPolicySelection{
			PolicyID:        request.FrozenPolicySelection.PolicyID,
			ReleaseDigest:   request.FrozenPolicySelection.ReleaseDigest,
			Cohort:          request.FrozenPolicySelection.Cohort,
			RolloutRevision: request.FrozenPolicySelection.RolloutRevision,
			RuleID:          request.FrozenPolicySelection.RuleID,
			Template: assistant.AssistantFrozenPolicyTemplate{
				TemplateID:   request.FrozenPolicySelection.Template.TemplateID,
				SkillID:      request.FrozenPolicySelection.Template.SkillID,
				DomainID:     request.FrozenPolicySelection.Template.DomainID,
				PromptPolicy: request.FrozenPolicySelection.Template.PromptPolicy,
				AllowedTools: append(
					[]string(nil),
					request.FrozenPolicySelection.Template.AllowedTools...,
				),
				SearchIntensity: request.FrozenPolicySelection.Template.SearchIntensity,
			},
			LearningContextPolicy: assistant.AssistantFrozenLearningContextPolicy{
				Enabled: request.FrozenPolicySelection.LearningContextPolicy.Enabled,
				AllowedSignals: append(
					[]string(nil),
					request.FrozenPolicySelection.LearningContextPolicy.AllowedSignals...,
				),
				AllowedMetricIDs: append(
					[]string(nil),
					request.FrozenPolicySelection.LearningContextPolicy.AllowedMetricIDs...,
				),
				AllowedReasonCodes: append(
					[]string(nil),
					request.FrozenPolicySelection.LearningContextPolicy.AllowedReasonCodes...,
				),
				MinimumFeedbackSamples: request.FrozenPolicySelection.LearningContextPolicy.MinimumFeedbackSamples,
				WindowDays:             request.FrozenPolicySelection.LearningContextPolicy.WindowDays,
				SnapshotTrainingEligible: request.FrozenPolicySelection.
					LearningContextPolicy.SnapshotTrainingEligible,
			},
		},
	}
}

// ProjectVerificationRepairContextSummary exposes only the bounded verifier
// repair constraint from the canonical root Task. It never rewrites the user
// input, Goal revision, Goal history or frozen Definition of Done.
func ProjectVerificationRepairContextSummary(
	runID string,
	value *assistant.AssistantRunContextSummary,
	graph runruntime.TaskGraph,
) *assistant.AssistantRunContextSummary {
	instruction := ""
	attempt := 0
	for _, task := range graph.Tasks {
		if task.TaskID != "task_root" || task.Attempt <= 1 ||
			task.Status != generated.AssistantTaskStatusRunning ||
			task.Verification.Passed ||
			!strings.HasPrefix(
				strings.TrimSpace(task.BlockReason),
				"verification_rejected:",
			) {
			continue
		}
		instruction = strings.TrimSpace(task.Verification.Summary)
		attempt = task.Attempt
		break
	}
	if instruction == "" {
		return value
	}
	var projected assistant.AssistantRunContextSummary
	if value != nil {
		projected = *value
		projected.ConfirmedFacts = append([]string(nil), value.ConfirmedFacts...)
		projected.PendingItems = append([]string(nil), value.PendingItems...)
		projected.ConfirmedSlots = cloneConfirmedSlotValues(value.ConfirmedSlots)
	} else {
		runID = strings.TrimSpace(runID)
		projected = assistant.AssistantRunContextSummary{
			SummaryID:  "assistant_run_verifier_repair:" + runID,
			FromTurnID: runID,
			ToTurnID:   runID,
			TurnCount:  1,
		}
	}
	line := fmt.Sprintf(
		"系统验证修复约束（第 %d 次执行；不改变用户目标或完成合同）：%s",
		attempt,
		instruction,
	)
	if text := strings.TrimSpace(projected.Text); text != "" {
		projected.Text = text + "\n" + line
	} else {
		projected.Text = line
	}
	return &projected
}

// ProjectExecutionContextSummary overlays only the current Run's confirmed
// slots onto the frozen AssistantSession summary. It gives resumed execution a
// session_summary recall source without mutating the frozen input or treating
// previous summary slots as newly confirmed by this Run.
func ProjectExecutionContextSummary(
	runID string,
	value *runruntime.SessionContinuity,
	current assistant.AssistantRunConfirmedSlots,
) *assistant.AssistantRunContextSummary {
	var projected *assistant.AssistantRunContextSummary
	if value != nil && strings.TrimSpace(value.SummaryID) != "" {
		projected = &assistant.AssistantRunContextSummary{
			SummaryID:      value.SummaryID,
			Text:           value.Text,
			FromTurnID:     value.FromTurnID,
			ToTurnID:       value.ToTurnID,
			TurnCount:      value.TurnCount,
			CurrentGoal:    value.CurrentGoal,
			ConfirmedFacts: append([]string(nil), value.ConfirmedFacts...),
			PendingItems:   append([]string(nil), value.PendingItems...),
			ConfirmedSlots: cloneConfirmedSlotValues(value.ConfirmedSlots),
		}
	}
	current = current.Clone()
	if len(current) == 0 {
		return projected
	}
	if projected == nil {
		runID = strings.TrimSpace(runID)
		projected = &assistant.AssistantRunContextSummary{
			SummaryID:      "assistant_run_confirmed_slots:" + runID,
			FromTurnID:     runID,
			ToTurnID:       runID,
			TurnCount:      1,
			ConfirmedSlots: map[string]string{},
		}
	}
	if projected.ConfirmedSlots == nil {
		projected.ConfirmedSlots = map[string]string{}
	}
	for key, item := range current {
		projected.ConfirmedSlots[key] = item
	}
	line := "本 Run 已确认槽位（覆盖旧摘要同名槽位）：" +
		formatConfirmedSlotValues(current)
	if text := strings.TrimSpace(projected.Text); text != "" {
		projected.Text = text + "\n" + line
	} else {
		projected.Text = line
	}
	return projected
}

func cloneConfirmedSlotValues(value map[string]string) map[string]string {
	if len(value) == 0 {
		return nil
	}
	cloned := make(map[string]string, len(value))
	for key, item := range value {
		cloned[key] = item
	}
	return cloned
}

func formatConfirmedSlotValues(
	value assistant.AssistantRunConfirmedSlots,
) string {
	keys := make([]string, 0, len(value))
	for key := range value {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		parts = append(parts, key+"="+value[key])
	}
	return strings.Join(parts, "；")
}

func sharedAssistantSurface(surfaceKind string) bool {
	switch strings.TrimSpace(surfaceKind) {
	case "conversation", "circle":
		return true
	default:
		return false
	}
}

func decodeAuthorizedIntersectionEvidence(
	value any,
) []assistant.AuthorizedIntersectionEvidence {
	if value == nil {
		return nil
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil
	}
	var evidence []assistant.AuthorizedIntersectionEvidence
	if err := json.Unmarshal(encoded, &evidence); err != nil {
		return nil
	}
	return evidence
}

func executionStartTime(createdAt time.Time) time.Time {
	if createdAt.IsZero() {
		return time.Now().UTC()
	}
	return createdAt.UTC()
}

func decodeExecutionTrigger(value map[string]any) assistant.AssistantTurnTrigger {
	if len(value) == 0 {
		return assistant.AssistantTurnTrigger{Type: "user_message"}
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return assistant.AssistantTurnTrigger{Type: "user_message"}
	}
	var trigger assistant.AssistantTurnTrigger
	if err := json.Unmarshal(encoded, &trigger); err != nil ||
		strings.TrimSpace(trigger.Type) == "" {
		return assistant.AssistantTurnTrigger{Type: "user_message"}
	}
	return trigger
}

func decodeExecutionPageContext(
	value map[string]any,
) *assistant.AssistantContextSnapshot {
	if len(value) == 0 {
		return nil
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil
	}
	var snapshot assistant.AssistantContextSnapshot
	if err := json.Unmarshal(encoded, &snapshot); err != nil {
		return nil
	}
	return &snapshot
}

func cloneObject(value map[string]any) map[string]any {
	result := make(map[string]any, len(value))
	for key, item := range value {
		result[key] = item
	}
	return result
}

func executionString(value map[string]any, key string) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(stringValue(value[key]))
}
