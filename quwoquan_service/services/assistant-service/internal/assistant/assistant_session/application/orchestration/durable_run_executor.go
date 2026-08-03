package orchestration

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/streaming"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	presentationpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

// DurableRunExecutor adapts the production AgentLoop to the canonical
// AssistantRun worker. The execution-shaped AssistantTurn below is ephemeral:
// it is never written as an aggregate and its internal execution ID is not
// the public Run ID. All durable output is projected into typed RunItems by the
// worker callback.
type DurableRunExecutor struct {
	loop *AgentLoop
}

func NewDurableRunExecutor(loop *AgentLoop) *DurableRunExecutor {
	if loop == nil {
		panic("assistant agent loop is required")
	}
	return &DurableRunExecutor{loop: loop}
}

func (e *DurableRunExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	if e == nil || e.loop == nil || strings.TrimSpace(request.RunID) == "" ||
		strings.TrimSpace(request.Goal) == "" ||
		strings.TrimSpace(request.SkillPackageID) == "" ||
		strings.TrimSpace(request.SkillPackageReleaseDigest) == "" ||
		emit == nil {
		return runruntime.ExecutionResult{}, runruntime.ErrInvalidRun
	}
	ctx = skillpkg.WithPackageRelease(ctx, skillpkg.PackageReleaseIdentity{
		PackageID:     request.SkillPackageID,
		ReleaseDigest: request.SkillPackageReleaseDigest,
	})
	if receipt, completed := executionCompletedDeviceAction(request.Checkpoint); completed {
		answer := "设备操作已完成。"
		if provider, ok := e.loop.React.Tools.(ToolMetadataProvider); ok {
			if metadata, found := provider.ToolMetadata(receipt.ActionKind); found &&
				strings.TrimSpace(metadata.Confirmation.CompletionSummary) != "" {
				answer = strings.TrimSpace(metadata.Confirmation.CompletionSummary)
			}
		}
		presentation, err := e.buildExecutionPresentation(ctx, request, answer, nil, nil)
		if err != nil {
			return runruntime.ExecutionResult{}, err
		}
		return runruntime.ExecutionResult{
			AnswerText:          answer,
			Presentation:        presentation,
			Verified:            true,
			VerificationSummary: "device action completed after explicit confirmation and native receipt",
		}, nil
	}
	turn := executionTurn(request)
	answer := strings.Builder{}
	processes := make(map[string]map[string]any)
	processOrder := make([]string, 0)
	startedItems := make(map[string]bool)
	waitingState := generated.AssistantRunState("")
	waitReason := ""
	pendingApproval := map[string]any(nil)
	pendingApprovalRef := ""
	completed := false
	firstAnswerObserved := false
	_, failure, err := e.loop.RunTurnWithSink(
		ctx,
		turn,
		func(envelope streaming.Envelope) error {
			switch envelope.EventType {
			case string(assistantstreaming.AssistantStreamEventAnswerDelta):
				if !firstAnswerObserved && !request.CreatedAt.IsZero() {
					firstAnswerObserved = true
					recordAssistantFirstVisibleResponse(
						time.Since(request.CreatedAt),
					)
				}
				if text, ok := envelope.Payload["text"].(string); ok {
					answer.WriteString(text)
				}
			case string(assistantstreaming.AssistantStreamEventCompleted):
				completed = true
				if !firstAnswerObserved && !request.CreatedAt.IsZero() {
					firstAnswerObserved = true
					recordAssistantFirstVisibleResponse(
						time.Since(request.CreatedAt),
					)
				}
				if finalAnswer, ok := envelope.Payload["finalAnswer"].(string); ok && strings.TrimSpace(finalAnswer) != "" {
					answer.Reset()
					answer.WriteString(finalAnswer)
				}
			case string(generated.AssistantStreamEventTypeWaitingInput):
				waitingState = generated.AssistantRunStateWaitingUser
				waitReason = executionString(envelope.Payload, "reason")
				if waitReason == "" {
					waitReason = "waiting_user_input"
				}
			case string(generated.AssistantStreamEventTypeWaitingApproval):
				waitingState = generated.AssistantRunStateWaitingApproval
				waitReason = executionString(envelope.Payload, "reason")
				pendingApproval = cloneObject(envelope.Payload)
				pendingApprovalRef = executionString(envelope.Payload, "toolUseId")
				if waitReason == "" {
					waitReason = "waiting_tool_approval"
				}
			}
			return projectExecutionProcesses(
				envelope,
				request,
				emit,
				processes,
				&processOrder,
				startedItems,
			)
		},
	)
	if err != nil {
		return runruntime.ExecutionResult{}, err
	}
	if failure != nil {
		return runruntime.ExecutionResult{}, &runruntime.ExecutionFailure{
			Code:   failure.Code,
			Origin: string(failure.Origin),
			Kind:   string(failure.Kind),
			Nature: string(failure.Nature),
		}
	}
	if waitingState == "" && !completed {
		waitingState = generated.AssistantRunStateWaitingUser
		waitReason = "waiting_user_input"
	}
	visibleProcesses := make([]map[string]any, 0, len(processOrder))
	for _, processID := range processOrder {
		visibleProcesses = append(visibleProcesses, processes[processID])
	}
	finalAnswer := strings.TrimSpace(answer.String())
	evidenceRefs := collectExecutionEvidenceRefs(visibleProcesses)
	verified, verificationSummary := verifyExecutionResult(
		request.DefinitionOfDone,
		finalAnswer,
		visibleProcesses,
		evidenceRefs,
	)
	presentationDocument, presentationErr := e.buildExecutionPresentation(
		ctx,
		request,
		finalAnswer,
		visibleProcesses,
		pendingApproval,
	)
	if presentationErr != nil {
		return runruntime.ExecutionResult{}, presentationErr
	}
	return runruntime.ExecutionResult{
		AnswerText:          finalAnswer,
		Processes:           visibleProcesses,
		EvidenceRefs:        evidenceRefs,
		Presentation:        presentationDocument,
		Verified:            completed && verified,
		VerificationSummary: verificationSummary,
		WaitingState:        waitingState,
		WaitReason:          waitReason,
		PendingApprovalRef:  pendingApprovalRef,
	}, nil
}

func executionCompletedDeviceAction(
	checkpoint *runruntime.Checkpoint,
) (runruntime.DeviceActionExecutionReceipt, bool) {
	if checkpoint == nil {
		return runruntime.DeviceActionExecutionReceipt{}, false
	}
	const prefix = "device_action_completed:"
	completedRefs := map[string]struct{}{}
	for _, summary := range checkpoint.DecisionSummary {
		if strings.HasPrefix(summary, prefix) {
			completedRefs[strings.TrimSpace(strings.TrimPrefix(summary, prefix))] = struct{}{}
		}
	}
	for index := len(checkpoint.DeviceActionReceipts) - 1; index >= 0; index-- {
		receipt := checkpoint.DeviceActionReceipts[index]
		if _, completed := completedRefs[strings.TrimSpace(receipt.IdempotencyKey)]; completed && strings.TrimSpace(receipt.Outcome) == "completed" &&
			strings.TrimSpace(receipt.ActionKind) != "" {
			return receipt, true
		}
	}
	return runruntime.DeviceActionExecutionReceipt{}, false
}

func selectTemplateInput(
	schema map[string]any,
	sources []map[string]any,
) (map[string]any, bool) {
	properties, ok := schema["properties"].(map[string]any)
	if !ok {
		return nil, false
	}
	selected := make(map[string]any, len(properties))
	for name := range properties {
		for _, source := range sources {
			if value, found := source[name]; found {
				selected[name] = value
				break
			}
		}
	}
	for _, name := range stringList(schema["required"]) {
		if _, found := selected[name]; !found {
			return nil, false
		}
	}
	return selected, true
}

func toolConfirmationPresentation(
	pending map[string]any,
) (map[string]any, string, string, presentationpkg.ActionPolicy, error) {
	toolUseID := executionString(pending, "toolUseId")
	continuationToken := executionString(pending, "continuationToken")
	proposal := objectMap(pending["proposal"])
	input := objectMap(proposal["input"])
	confirmation := objectMap(proposal["confirmation"])
	toolName := executionString(proposal, "toolName")
	templateRef := executionString(confirmation, "templateRef")
	title := executionString(confirmation, "title")
	body := executionString(confirmation, "description")
	if toolUseID == "" || continuationToken == "" || toolName == "" ||
		templateRef == "" || title == "" || body == "" || len(input) == 0 {
		return nil, "", "", nil, fmt.Errorf("invalid typed tool confirmation proposal")
	}
	rows := make([]any, 0)
	fallbackLines := []string{title, "", body}
	for _, raw := range anyList(confirmation["displayFields"]) {
		field := objectMap(raw)
		key := executionString(field, "inputKey")
		label := executionString(field, "label")
		value, found := input[key]
		if key == "" || label == "" || !found || emptyPresentationValue(value) {
			continue
		}
		text := presentationValueText(value)
		if text == "" {
			return nil, "", "", nil, fmt.Errorf("invalid confirmation display value")
		}
		rows = append(rows, map[string]any{"项目": label, "内容": text})
		fallbackLines = append(fallbackLines, "- "+label+"："+text)
	}
	if len(rows) == 0 {
		return nil, "", "", nil, fmt.Errorf("typed tool confirmation has no displayable fields")
	}
	approved := map[string]any{
		"intentId":      "approve_" + toolUseID,
		"operation":     "ContinueAssistantToolUse",
		"objectTypeRef": "assistant_tool_use",
		"objectId":      toolUseID,
		"payload": map[string]any{
			"decision":          "approved",
			"continuationToken": continuationToken,
			"deviceAction": map[string]any{
				"kind": toolName, "idempotencyKey": toolUseID,
				"input": cloneObject(input),
			},
		},
		"requiresConfirmation": true,
	}
	rejected := map[string]any{
		"intentId":      "reject_" + toolUseID,
		"operation":     "ContinueAssistantToolUse",
		"objectTypeRef": "assistant_tool_use",
		"objectId":      toolUseID,
		"payload": map[string]any{
			"decision": "rejected", "continuationToken": continuationToken,
		},
		"requiresConfirmation": true,
	}
	return map[string]any{
			"title": title,
			"body":  body,
			"details": map[string]any{
				"columns": []any{"项目", "内容"},
				"rows":    rows,
			},
			"approveAction": approved,
			"rejectAction":  rejected,
		}, strings.Join(fallbackLines, "\n"), templateRef, continuationActionPolicy{
			ToolUseID: toolUseID, ContinuationToken: continuationToken,
		}, nil
}

type continuationActionPolicy struct {
	ToolUseID         string
	ContinuationToken string
}

func (policy continuationActionPolicy) ValidateAction(
	_ context.Context,
	_ string,
	action presentationpkg.ActionIntent,
) error {
	if action.Operation != "ContinueAssistantToolUse" ||
		action.ObjectTypeRef != "assistant_tool_use" ||
		action.ObjectID != policy.ToolUseID || !action.RequiresConfirmation {
		return presentationpkg.ErrActionRejected
	}
	decision := executionString(action.Payload, "decision")
	token := executionString(action.Payload, "continuationToken")
	if token != policy.ContinuationToken ||
		(decision != "approved" && decision != "rejected") {
		return presentationpkg.ErrActionRejected
	}
	return nil
}

func presentationDocumentMap(document presentationpkg.Document) (map[string]any, error) {
	raw, err := json.Marshal(document)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func stringList(value any) []string {
	switch values := value.(type) {
	case []string:
		return append([]string(nil), values...)
	case []any:
		result := make([]string, 0, len(values))
		for _, value := range values {
			if text, ok := value.(string); ok {
				result = append(result, text)
			}
		}
		return result
	default:
		return nil
	}
}

func anyList(value any) []any {
	switch values := value.(type) {
	case []any:
		return values
	case []map[string]any:
		result := make([]any, 0, len(values))
		for _, item := range values {
			result = append(result, item)
		}
		return result
	default:
		return nil
	}
}

func emptyPresentationValue(value any) bool {
	if value == nil {
		return true
	}
	if text, ok := value.(string); ok {
		return strings.TrimSpace(text) == ""
	}
	return false
}

func presentationValueText(value any) string {
	var text string
	switch typed := value.(type) {
	case string:
		text = strings.TrimSpace(typed)
	case json.Number:
		text = typed.String()
	case int:
		text = fmt.Sprintf("%d", typed)
	case int32:
		text = fmt.Sprintf("%d", typed)
	case int64:
		text = fmt.Sprintf("%d", typed)
	case float64:
		text = fmt.Sprintf("%v", typed)
	case bool:
		text = fmt.Sprintf("%t", typed)
	default:
		return ""
	}
	if len([]rune(text)) > 2000 || strings.ContainsAny(text, "<>\x00") {
		return ""
	}
	return text
}

func presentationSurfaceCapabilities(values map[string]any) presentationpkg.SurfaceCapabilities {
	supported := make(map[generated.AssistantPresentationNodeKind]bool)
	appendKind := func(raw any) {
		kind, err := generated.ParseAssistantPresentationNodeKind(
			strings.TrimSpace(stringValue(raw)),
		)
		if err == nil && kind != generated.AssistantPresentationNodeKindUnknown {
			supported[kind] = true
		}
	}
	switch raw := values["supportedNodeKinds"].(type) {
	case []any:
		for _, value := range raw {
			appendKind(value)
		}
	case []string:
		for _, value := range raw {
			appendKind(value)
		}
	}
	density := generated.AssistantPresentationDensityStandard
	if raw := strings.TrimSpace(executionString(values, "density")); raw != "" {
		if parsed, err := generated.ParseAssistantPresentationDensity(raw); err == nil {
			density = parsed
		}
	}
	viewport := strings.TrimSpace(executionString(values, "viewportClass"))
	if viewport == "" {
		viewport = "standard"
	}
	return presentationpkg.SurfaceCapabilities{
		SupportedNodeKinds: supported, ViewportClass: viewport, Density: density,
	}
}

func collectExecutionEvidenceRefs(processes []map[string]any) []string {
	unique := map[string]struct{}{}
	for _, process := range processes {
		appendReference := func(reference map[string]any) {
			if sourceID := strings.TrimSpace(stringValue(reference["sourceId"])); sourceID != "" {
				unique[sourceID] = struct{}{}
			}
		}
		switch references := process["acceptedReferences"].(type) {
		case []map[string]any:
			for _, reference := range references {
				appendReference(reference)
			}
		case []any:
			for _, raw := range references {
				if reference := objectMap(raw); reference != nil {
					appendReference(reference)
				}
			}
		}
	}
	result := make([]string, 0, len(unique))
	for reference := range unique {
		result = append(result, reference)
	}
	sort.Strings(result)
	return result
}

func verifyExecutionResult(
	definition runruntime.DefinitionOfDone,
	answer string,
	processes []map[string]any,
	evidenceRefs []string,
) (bool, string) {
	if len(definition.VerificationRequirements) == 0 {
		return false, "Definition of Done 缺少验证要求"
	}
	for _, requirement := range definition.VerificationRequirements {
		switch strings.TrimSpace(requirement) {
		case "answer_present":
			if strings.TrimSpace(answer) == "" {
				return false, "最终答案为空"
			}
		case "evidence_present":
			if len(evidenceRefs) == 0 {
				return false, "缺少 authoritative evidence ledger 引用"
			}
		case "citations_present":
			if !executionHasAcceptedEvidence(processes) {
				return false, "缺少已接受且可回查的证据"
			}
		default:
			return false, "存在未实现的验证要求: " + requirement
		}
	}
	return true, "Definition of Done 已通过可执行验证"
}

func executionHasAcceptedEvidence(processes []map[string]any) bool {
	for _, process := range processes {
		switch value := process["acceptedReferences"].(type) {
		case []any:
			if len(value) > 0 {
				return true
			}
		case []string:
			if len(value) > 0 {
				return true
			}
		}
		if count, ok := process["acceptedDocumentCount"].(float64); ok && count > 0 {
			return true
		}
		if count, ok := process["acceptedDocumentCount"].(int); ok && count > 0 {
			return true
		}
	}
	return false
}

func executionStringFromProcesses(
	processes []map[string]any,
	key string,
) string {
	for index := len(processes) - 1; index >= 0; index-- {
		if value := strings.TrimSpace(stringValue(processes[index][key])); value != "" {
			return value
		}
	}
	return ""
}

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
	sessionPreferenceFacts := append(
		[]preferencemodel.Snapshot(nil),
		request.SessionPreferenceFacts...,
	)
	longTermPreferenceFacts := append(
		[]preferencemodel.Snapshot(nil),
		request.LongTermPreferenceFacts...,
	)
	if sharedAssistantSurface(request.RequestContext.SurfaceKind) {
		// 群聊/圈子只可使用 surface 内共享事实。个人偏好与长期记忆即使
		// 被旧 checkpoint 携带，也必须在构造执行 turn 时物理退出。
		sessionPreferenceFacts = nil
		longTermPreferenceFacts = nil
	}
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
		SessionPreferenceFacts:  sessionPreferenceFacts,
		LongTermPreferenceFacts: longTermPreferenceFacts,
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

func projectExecutionProcesses(
	envelope streaming.Envelope,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
	processes map[string]map[string]any,
	processOrder *[]string,
	startedItems map[string]bool,
) error {
	rawProcesses := make([]map[string]any, 0)
	if process := objectMap(envelope.Payload["process"]); process != nil {
		rawProcesses = append(rawProcesses, process)
	}
	if list, ok := envelope.Payload["processes"].([]any); ok {
		for _, raw := range list {
			if process := objectMap(raw); process != nil {
				rawProcesses = append(rawProcesses, process)
			}
		}
	} else if list, ok := envelope.Payload["processes"].([]map[string]any); ok {
		rawProcesses = append(rawProcesses, list...)
	}
	for _, process := range rawProcesses {
		processID := strings.TrimSpace(stringValue(process["processId"]))
		if processID == "" {
			continue
		}
		if _, exists := processes[processID]; !exists {
			*processOrder = append(*processOrder, processID)
		}
		processes[processID] = cloneObject(process)
		itemID := request.IdempotencyPrefix + ":process:" + processID
		status := strings.TrimSpace(stringValue(process["status"]))
		if !startedItems[itemID] {
			if err := emit(runruntime.ExecutionItemUpdate{
				ItemID:  itemID,
				Kind:    processItemKind(process),
				Status:  generated.AssistantRunItemStatusStarted,
				TaskID:  "task_root",
				Summary: boundedProcessSummary(process),
				Payload: safeProcessPayload(process),
			}); err != nil {
				return err
			}
			startedItems[itemID] = true
		}
		if status == "completed" || status == "failed" ||
			envelope.EventType == string(assistantstreaming.AssistantStreamEventProcessCommit) {
			closure := generated.AssistantRunItemStatusCompleted
			if status == "failed" {
				closure = generated.AssistantRunItemStatusFailed
			}
			if err := emit(runruntime.ExecutionItemUpdate{
				ItemID:  itemID,
				Kind:    processItemKind(process),
				Status:  closure,
				TaskID:  "task_root",
				Summary: boundedProcessSummary(process),
			}); err != nil && !errors.Is(err, runruntime.ErrItemStateConflict) {
				return err
			}
		}
	}
	return nil
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

func processItemKind(
	process map[string]any,
) generated.AssistantRunItemKind {
	scope := strings.ToLower(stringValue(process["scope"]))
	stage := strings.ToLower(stringValue(process["stage"]))
	switch {
	case strings.Contains(scope, "subagent") || strings.Contains(stage, "subagent"):
		return generated.AssistantRunItemKindSubagent
	case strings.Contains(scope, "tool") || strings.Contains(stage, "tool") ||
		strings.Contains(stage, "retriev"):
		return generated.AssistantRunItemKindToolUse
	case strings.Contains(stage, "evidence") || strings.Contains(stage, "observ"):
		return generated.AssistantRunItemKindEvidence
	default:
		return generated.AssistantRunItemKindTask
	}
}

func safeProcessPayload(process map[string]any) map[string]any {
	allowed := []string{
		"processId",
		"scope",
		"stage",
		"actionCode",
		"toolUseId",
		"status",
		"order",
		"summary",
		"skillId",
		"domainId",
		"searchedDocumentCount",
		"processedDocumentCount",
		"acceptedDocumentCount",
		"acceptedReferences",
	}
	result := make(map[string]any, len(allowed))
	for _, key := range allowed {
		if value, ok := process[key]; ok {
			result[key] = value
		}
	}
	return result
}

func boundedProcessSummary(process map[string]any) string {
	if summary := strings.TrimSpace(stringValue(process["summary"])); summary != "" {
		runes := []rune(summary)
		if len(runes) > 256 {
			runes = runes[:256]
		}
		return string(runes)
	}
	return strings.TrimSpace(stringValue(process["stage"]))
}

func objectMap(value any) map[string]any {
	switch typed := value.(type) {
	case map[string]any:
		return typed
	default:
		return nil
	}
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

var _ runruntime.RunExecutor = (*DurableRunExecutor)(nil)
