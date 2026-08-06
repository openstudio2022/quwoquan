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
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
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
	var err error
	ctx, err = e.loop.WithDurableReasoningProfile(ctx, request.ReasoningPolicy)
	if err != nil {
		return runruntime.ExecutionResult{}, err
	}
	ctx = withExecutionBudgetConsumption(
		ctx,
		ExecutionBudgetConsumption{
			ToolCalls: request.BudgetConsumption.ToolCalls,
			Tokens:    request.BudgetConsumption.Tokens,
			CostUnits: request.BudgetConsumption.CostUnits,
		},
		request.BudgetReceiptSequence,
		func(snapshot executionBudgetConsumptionSnapshot) error {
			return emit(runruntime.ExecutionItemUpdate{
				Budget: &runruntime.BudgetConsumptionReceipt{
					Scope:    request.IdempotencyPrefix,
					Sequence: snapshot.Sequence,
					Consumption: runruntime.BudgetConsumption{
						ToolCalls: snapshot.Consumption.ToolCalls,
						Tokens:    snapshot.Consumption.Tokens,
						CostUnits: snapshot.Consumption.CostUnits,
					},
				},
			})
		},
	)
	ctx = skillpkg.WithPackageRelease(ctx, skillpkg.PackageReleaseIdentity{
		PackageID:     request.SkillPackageID,
		ReleaseDigest: request.SkillPackageReleaseDigest,
	})
	if receipt, completed := executionCompletedDeviceAction(request.Checkpoint); completed {
		answer := "设备操作已完成。"
		if provider, ok := e.loop.React.Tools.(ToolMetadataProvider); ok {
			if metadata, found := provider.ToolMetadata(receipt.Capability); found &&
				strings.TrimSpace(metadata.Confirmation.CompletionSummary) != "" {
				answer = strings.TrimSpace(metadata.Confirmation.CompletionSummary)
			}
		}
		prepared, err := e.prepareDeviceCompletionPresentation(ctx, request)
		if err != nil {
			return runruntime.ExecutionResult{}, err
		}
		var presentation map[string]any
		if prepared.SkillID != "" {
			presentation, err = e.buildExecutionPresentation(
				ctx, request, prepared, answer, nil,
			)
			if err != nil {
				return runruntime.ExecutionResult{}, err
			}
		}
		artifactRefs := []string{
			executionAnswerArtifactRef(request.RunID),
			"device_action_receipt:" + strings.TrimSpace(receipt.IdempotencyKey),
		}
		return runruntime.ExecutionResult{
			AnswerText:   answer,
			ArtifactRefs: artifactRefs,
			VerificationEvidence: verificationEvidenceForExecution(
				request.DefinitionOfDone,
				true,
				answer,
				nil,
				nil,
				artifactRefs,
			),
			Presentation: presentation,
		}, nil
	}
	turn := executionTurn(request)
	answer := strings.Builder{}
	processes := make(map[string]assistant.AssistantRunVisibleProcess)
	processOrder := make([]string, 0)
	startedItems := make(map[string]bool)
	taskTracker := newExecutionTaskTracker(request)
	waitingState := generated.AssistantRunState("")
	waitReason := ""
	pendingApproval := map[string]any(nil)
	pendingApprovalRef := ""
	completed := false
	firstAnswerObserved := false
	var prepared *PreparedExecution
	_, failure, err := e.loop.RunTurnWithPreparedExecution(
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
				taskTracker,
			)
		},
		func(value PreparedExecution) error {
			if prepared != nil {
				return fmt.Errorf("assistant execution prepared more than once")
			}
			prepared = &value
			return nil
		},
	)
	if err != nil {
		result := runruntime.ExecutionResult{}
		if prepared != nil {
			result.ConfirmedSlots = prepared.ConfirmedSlots.Clone()
		}
		return result, err
	}
	if failure != nil {
		return runruntime.ExecutionResult{}, &runruntime.ExecutionFailure{
			Code:   failure.Code,
			Origin: string(failure.Origin),
			Kind:   string(failure.Kind),
			Nature: string(failure.Nature),
		}
	}
	if prepared == nil {
		return runruntime.ExecutionResult{}, fmt.Errorf(
			"assistant execution completed without a frozen Skill/Context preparation",
		)
	}
	if waitingState == "" && !completed {
		waitingState = generated.AssistantRunStateWaitingUser
		waitReason = "waiting_user_input"
	}
	visibleProcesses := make([]assistant.AssistantRunVisibleProcess, 0, len(processOrder))
	for _, processID := range processOrder {
		visibleProcesses = append(visibleProcesses, processes[processID])
	}
	finalAnswer := strings.TrimSpace(answer.String())
	evidenceRefs := collectExecutionEvidenceRefs(visibleProcesses)
	artifactRefs := append([]string{}, evidenceRefs...)
	if completed && finalAnswer != "" {
		artifactRefs = append(
			artifactRefs,
			executionAnswerArtifactRef(request.RunID),
		)
	}
	verificationEvidence := verificationEvidenceForExecution(
		request.DefinitionOfDone,
		completed,
		finalAnswer,
		visibleProcesses,
		evidenceRefs,
		artifactRefs,
	)
	presentationDocument, presentationErr := e.buildExecutionPresentation(
		ctx,
		request,
		*prepared,
		finalAnswer,
		pendingApproval,
	)
	if presentationErr != nil {
		return runruntime.ExecutionResult{}, presentationErr
	}
	return runruntime.ExecutionResult{
		AnswerText:           finalAnswer,
		Processes:            visibleProcesses,
		ArtifactRefs:         artifactRefs,
		EvidenceRefs:         evidenceRefs,
		VerificationEvidence: verificationEvidence,
		Presentation:         presentationDocument,
		WaitingState:         waitingState,
		WaitReason:           waitReason,
		PendingApprovalRef:   pendingApprovalRef,
		ConfirmedSlots:       prepared.ConfirmedSlots.Clone(),
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
			strings.TrimSpace(receipt.Capability) != "" {
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
) (map[string]any, string, presentationpkg.ActionPolicy, error) {
	runID := executionString(pending, "runId")
	toolUseID := executionString(pending, "toolUseId")
	continuationToken := executionString(pending, "continuationToken")
	issuedAt, issuedErr := time.Parse(
		time.RFC3339Nano,
		executionString(pending, "issuedAt"),
	)
	expiresAt, expiresErr := time.Parse(
		time.RFC3339Nano,
		executionString(pending, "expiresAt"),
	)
	proposal := objectMap(pending["proposal"])
	input := objectMap(proposal["input"])
	confirmation := objectMap(proposal["confirmation"])
	toolName := executionString(proposal, "toolName")
	templateRef := executionString(confirmation, "templateRef")
	title := executionString(confirmation, "title")
	body := executionString(confirmation, "description")
	if runID == "" || toolUseID == "" || continuationToken == "" ||
		issuedErr != nil || expiresErr != nil ||
		!expiresAt.After(issuedAt) ||
		toolName == "" || templateRef == "" || title == "" ||
		body == "" || len(input) == 0 {
		return nil, "", nil, fmt.Errorf("invalid typed tool confirmation proposal")
	}
	rows := make([]any, 0)
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
			return nil, "", nil, fmt.Errorf("invalid confirmation display value")
		}
		rows = append(rows, map[string]any{"项目": label, "内容": text})
	}
	if len(rows) == 0 {
		return nil, "", nil, fmt.Errorf("typed tool confirmation has no displayable fields")
	}
	inputDigest, ok := presentationGroundingDigest(input)
	if !ok {
		return nil, "", nil, fmt.Errorf("tool confirmation input digest unavailable")
	}
	approvedContract := map[string]any{
		"runId":            runID,
		"toolInvocationId": toolUseID,
		"decision":         "approved",
		"capability":       toolName,
		"inputDigest":      inputDigest,
		"approvalPermit":   continuationToken,
	}
	approvedDigest, ok := presentationGroundingDigest(approvedContract)
	if !ok {
		return nil, "", nil, fmt.Errorf("approve tool intent digest unavailable")
	}
	rejectedContract := map[string]any{
		"runId":            runID,
		"toolInvocationId": toolUseID,
		"decision":         "rejected",
		"capability":       toolName,
		"inputDigest":      inputDigest,
		"approvalPermit":   continuationToken,
	}
	rejectedDigest, ok := presentationGroundingDigest(rejectedContract)
	if !ok {
		return nil, "", nil, fmt.Errorf("reject tool intent digest unavailable")
	}
	approved := map[string]any{
		"intentId":      "approve_" + toolUseID,
		"kind":          string(presentationpkg.ActionIntentApproveTool),
		"requestDigest": approvedDigest,
		"jti":           "approve_" + toolUseID,
		"issuedAt":      issuedAt.UTC().Format(time.RFC3339Nano),
		"expiresAt":     expiresAt.UTC().Format(time.RFC3339Nano),
		"approveTool":   approvedContract,
	}
	rejected := map[string]any{
		"intentId":      "reject_" + toolUseID,
		"kind":          string(presentationpkg.ActionIntentApproveTool),
		"requestDigest": rejectedDigest,
		"jti":           "reject_" + toolUseID,
		"issuedAt":      issuedAt.UTC().Format(time.RFC3339Nano),
		"expiresAt":     expiresAt.UTC().Format(time.RFC3339Nano),
		"approveTool":   rejectedContract,
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
		}, templateRef, continuationActionPolicy{
			RunID: runID, ToolUseID: toolUseID,
			ContinuationToken: continuationToken,
			Capability:        toolName, InputDigest: inputDigest,
		}, nil
}

type continuationActionPolicy struct {
	RunID             string
	ToolUseID         string
	ContinuationToken string
	Capability        string
	InputDigest       string
}

func (policy continuationActionPolicy) ValidateAction(
	_ context.Context,
	_ string,
	action presentationpkg.ActionIntent,
) error {
	if action.Kind != presentationpkg.ActionIntentApproveTool ||
		action.ApproveTool == nil ||
		action.ApproveTool.RunID != policy.RunID ||
		action.ApproveTool.ToolInvocationID != policy.ToolUseID ||
		action.ApproveTool.Capability != policy.Capability ||
		action.ApproveTool.InputDigest != policy.InputDigest ||
		action.ApproveTool.ApprovalPermit != policy.ContinuationToken {
		return presentationpkg.ErrActionRejected
	}
	if action.ApproveTool.Decision != "approved" &&
		action.ApproveTool.Decision != "rejected" {
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
	supportedActions := make(map[string]bool)
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
	appendAction := func(raw any) {
		operation := strings.TrimSpace(stringValue(raw))
		if operation != "" {
			supportedActions[operation] = true
		}
	}
	switch raw := values["supportedActionIntents"].(type) {
	case []any:
		for _, value := range raw {
			appendAction(value)
		}
	case []string:
		for _, value := range raw {
			appendAction(value)
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
		SupportedNodeKinds:     supported,
		SupportedActionIntents: supportedActions,
		ViewportClass:          viewport,
		Density:                density,
	}
}

func collectExecutionEvidenceRefs(
	processes []assistant.AssistantRunVisibleProcess,
) []string {
	unique := map[string]struct{}{}
	for _, process := range processes {
		for _, reference := range process.AcceptedReferences {
			if sourceID := strings.TrimSpace(reference.SourceID); sourceID != "" {
				unique[sourceID] = struct{}{}
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

func verificationEvidenceForExecution(
	definition runruntime.DefinitionOfDone,
	completed bool,
	answer string,
	processes []assistant.AssistantRunVisibleProcess,
	evidenceRefs []string,
	availableArtifactRefs []string,
) []runruntime.VerificationEvidence {
	available := map[string]bool{}
	for _, artifactRef := range availableArtifactRefs {
		artifactRef = strings.TrimSpace(artifactRef)
		if artifactRef != "" {
			available[artifactRef] = true
		}
	}
	answerArtifactRef := ""
	for artifactRef := range available {
		if strings.HasPrefix(artifactRef, "assistant_run_item:answer:") {
			answerArtifactRef = artifactRef
			break
		}
	}
	rows := make([]runruntime.VerificationEvidence, 0, len(definition.VerificationRequirements))
	for _, requirement := range definition.VerificationRequirements {
		requirement = strings.TrimSpace(requirement)
		row := runruntime.VerificationEvidence{Requirement: requirement}
		switch requirement {
		case "answer_present":
			row.Passed = completed && strings.TrimSpace(answer) != "" && answerArtifactRef != ""
			if row.Passed {
				row.ArtifactRefs = []string{answerArtifactRef}
				row.Summary = "final answer is persisted as a durable RunItem"
			} else {
				row.Summary = "final answer is absent or execution did not complete"
			}
		case "evidence_present":
			row.ArtifactRefs = append([]string{}, evidenceRefs...)
			row.Passed = completed && len(row.ArtifactRefs) > 0
			row.Summary = "authoritative evidence ledger references are present"
		case "citations_present":
			row.ArtifactRefs = append([]string{}, evidenceRefs...)
			row.Passed = completed && len(row.ArtifactRefs) > 0 &&
				executionHasAcceptedEvidence(processes)
			row.Summary = "accepted citations are linked to durable evidence"
		default:
			row.Summary = "no deterministic verifier is registered for this requirement"
		}
		rows = append(rows, row)
	}
	return rows
}

func executionAnswerArtifactRef(runID string) string {
	return "assistant_run_item:answer:" + strings.TrimSpace(runID)
}

func executionHasAcceptedEvidence(
	processes []assistant.AssistantRunVisibleProcess,
) bool {
	for _, process := range processes {
		if len(process.AcceptedReferences) > 0 || process.AcceptedDocumentCount > 0 {
			return true
		}
	}
	return false
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

func projectExecutionProcesses(
	envelope streaming.Envelope,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
	processes map[string]assistant.AssistantRunVisibleProcess,
	processOrder *[]string,
	startedItems map[string]bool,
	taskTracker *executionTaskTracker,
) error {
	rawProcesses := make([]assistant.AssistantRunVisibleProcess, 0)
	switch process := envelope.Payload["process"].(type) {
	case assistant.AssistantRunVisibleProcess:
		rawProcesses = append(rawProcesses, process)
	case *assistant.AssistantRunVisibleProcess:
		if process != nil {
			rawProcesses = append(rawProcesses, *process)
		}
	}
	if list, ok := envelope.Payload["processes"].([]assistant.AssistantRunVisibleProcess); ok {
		rawProcesses = append(rawProcesses, list...)
	}
	for _, typedProcess := range rawProcesses {
		processID := strings.TrimSpace(typedProcess.ProcessID)
		if processID == "" {
			continue
		}
		process := visibleProcessMap(typedProcess)
		if _, exists := processes[processID]; !exists {
			*processOrder = append(*processOrder, processID)
		}
		processes[processID] = *typedProcess.Clone()
		itemID := request.IdempotencyPrefix + ":process:" + processID
		taskID, taskUpdate := taskTracker.taskForProcess(process)
		status := strings.TrimSpace(typedProcess.Status)
		if !startedItems[itemID] {
			if err := emit(runruntime.ExecutionItemUpdate{
				ItemID:  itemID,
				Kind:    processItemKind(process),
				Status:  generated.AssistantRunItemStatusStarted,
				TaskID:  taskID,
				Summary: boundedProcessSummary(process),
				Payload: safeProcessPayload(process),
				Task:    taskUpdate,
			}); err != nil {
				return err
			}
			startedItems[itemID] = true
			taskTracker.mark(taskID, generated.AssistantTaskStatusRunning)
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
				TaskID:  taskID,
				Summary: boundedProcessSummary(process),
				Task:    taskUpdate,
			}); err != nil && !errors.Is(err, runruntime.ErrItemStateConflict) {
				return err
			}
			if closure == generated.AssistantRunItemStatusFailed {
				taskTracker.mark(taskID, generated.AssistantTaskStatusFailed)
			} else {
				taskTracker.mark(taskID, generated.AssistantTaskStatusCompleted)
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
	actionCode := strings.TrimSpace(stringValue(process["actionCode"]))
	switch {
	case strings.Contains(scope, "subagent") || strings.Contains(stage, "subagent"):
		return generated.AssistantRunItemKindSubagent
	case actionCode == generated.PlannerActionCodeParallelProbe.WireName():
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

// visibleProcessMap is the explicit boundary from the public process domain
// type into the persisted RunItem projection. AgentLoop intentionally emits a
// typed value; accepting only map[string]any silently discarded every process
// and therefore the real TaskGraph. Keep this conversion exhaustive instead
// of JSON round-tripping or adding a second wire decoder.
func visibleProcessMap(value any) map[string]any {
	switch typed := value.(type) {
	case map[string]any:
		return typed
	case assistant.AssistantRunVisibleProcess:
		references := make([]map[string]any, 0, len(typed.AcceptedReferences))
		for _, reference := range typed.AcceptedReferences {
			references = append(references, visibleReferenceMap(reference))
		}
		return map[string]any{
			"processId":              typed.ProcessID,
			"scope":                  typed.Scope,
			"stage":                  typed.Stage,
			"actionCode":             typed.ActionCode,
			"status":                 typed.Status,
			"order":                  typed.Order,
			"summary":                typed.Summary,
			"skillId":                typed.SkillID,
			"domainId":               typed.DomainID,
			"searchedDocumentCount":  typed.SearchedDocumentCount,
			"processedDocumentCount": typed.ProcessedDocumentCount,
			"acceptedDocumentCount":  typed.AcceptedDocumentCount,
			"acceptedReferences":     references,
		}
	default:
		return nil
	}
}

func visibleReferenceMap(
	reference assistant.AssistantRunVisibleReference,
) map[string]any {
	result := map[string]any{
		"title":       reference.Title,
		"destination": citationDestinationMap(reference.Destination),
		"source":      reference.Source,
		"snippet":     reference.Snippet,
	}
	if sourceID := strings.TrimSpace(reference.SourceID); sourceID != "" {
		result["sourceId"] = sourceID
	}
	return result
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
