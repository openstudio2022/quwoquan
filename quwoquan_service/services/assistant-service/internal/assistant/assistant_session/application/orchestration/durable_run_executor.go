package orchestration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/streaming"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

// DurableRunExecutor adapts the production AgentLoop to the canonical
// AssistantRun worker. The execution-shaped AssistantTurn below is ephemeral:
// it is never written to SessionRunStore and its internal execution ID is not
// the public Run ID. All durable output is projected into typed RunItems by the
// worker callback.
type DurableRunExecutor struct {
	loop           *AgentLoop
	policyResolver DurableExecutionPolicyResolver
}

type DurableExecutionPolicyResolver func(
	context.Context,
	runruntime.ExecutionRequest,
) (assistant.AssistantFrozenPolicySelection, error)

func NewDurableRunExecutor(loop *AgentLoop) *DurableRunExecutor {
	if loop == nil {
		panic("assistant agent loop is required")
	}
	return &DurableRunExecutor{loop: loop}
}

func NewDurableRunExecutorWithPolicyResolver(
	loop *AgentLoop,
	resolver DurableExecutionPolicyResolver,
) *DurableRunExecutor {
	executor := NewDurableRunExecutor(loop)
	if resolver == nil {
		panic("assistant durable execution policy resolver is required")
	}
	executor.policyResolver = resolver
	return executor
}

func (e *DurableRunExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	if e == nil || e.loop == nil || strings.TrimSpace(request.RunID) == "" ||
		strings.TrimSpace(request.Goal) == "" || emit == nil {
		return runruntime.ExecutionResult{}, runruntime.ErrInvalidRun
	}
	if completedDeviceActionRef := executionCompletedDeviceActionRef(request.Checkpoint); completedDeviceActionRef != "" {
		answer := "设备上的系统日程已创建。"
		presentation, err := buildExecutionPresentation(request, answer, nil, nil)
		if err != nil {
			return runruntime.ExecutionResult{}, err
		}
		return runruntime.ExecutionResult{
			AnswerText:          answer,
			Presentation:        presentation,
			Verified:            true,
			VerificationSummary: "device action completed after explicit confirmation",
		}, nil
	}
	turn := executionTurn(request)
	if e.policyResolver != nil {
		selection, err := e.policyResolver(ctx, request)
		if err != nil {
			return runruntime.ExecutionResult{}, err
		}
		turn.FrozenPolicySelection = selection
	}
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
		return runruntime.ExecutionResult{}, fmt.Errorf(
			"agent loop failed: %s",
			failure.Code,
		)
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
	presentationDocument, presentationErr := buildExecutionPresentation(
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

func executionCompletedDeviceActionRef(
	checkpoint *runruntime.Checkpoint,
) string {
	if checkpoint == nil {
		return ""
	}
	const prefix = "device_action_completed:"
	for _, summary := range checkpoint.DecisionSummary {
		if strings.HasPrefix(summary, prefix) {
			return strings.TrimSpace(strings.TrimPrefix(summary, prefix))
		}
	}
	return ""
}

func buildExecutionPresentation(
	request runruntime.ExecutionRequest,
	answer string,
	processes []map[string]any,
	pendingApproval map[string]any,
) (map[string]any, error) {
	if len(request.SurfaceCapabilities) == 0 ||
		(strings.TrimSpace(answer) == "" && len(pendingApproval) == 0) {
		return nil, nil
	}
	skillID := strings.TrimSpace(request.RequestedSkillID)
	if skillID == "" {
		skillID = executionStringFromProcesses(processes, "skillId")
	}
	if skillID == "" {
		return nil, nil
	}
	manifest, found, err := assistantDomainSkillManifest(skillID)
	if err != nil {
		return nil, fmt.Errorf("load adaptive presentation skill: %w", err)
	}
	if !found || !stringSliceContains(
		manifest.Presentation.TemplateRefs,
		"assistant.answer.default",
	) {
		return nil, nil
	}
	templateDigest := sha256Digest(
		"assistant.answer.default:" + manifest.Presentation.AssetDigest,
	)
	dataDigest := sha256Digest(answer)
	nodes := []map[string]any{}
	if len(pendingApproval) > 0 &&
		supportsPresentationNode(request.SurfaceCapabilities, "confirmation_card") &&
		supportsPresentationNode(request.SurfaceCapabilities, "action_group") {
		approvalNodes, err := buildDeviceActionApprovalNodes(pendingApproval)
		if err != nil {
			return nil, err
		}
		nodes = append(nodes, approvalNodes...)
		answer = deviceActionFallbackMarkdown(pendingApproval)
		dataDigest = sha256Digest(answer)
	} else if supportsPresentationNode(request.SurfaceCapabilities, "markdown") {
		nodes = append(nodes, map[string]any{
			"nodeId":       "root",
			"parentNodeId": "",
			"order":        0,
			"kind":         "markdown",
			"title":        "",
			"body":         answer,
			"data":         map[string]any{},
			"binding":      map[string]any{},
			"style": map[string]any{
				"tone":           "neutral",
				"density":        "standard",
				"emphasis":       "normal",
				"variant":        "standard",
				"alignment":      "start",
				"spacingRole":    "related",
				"aspectRatio":    0,
				"responsiveSpan": 1,
			},
			"accessibility": map[string]any{
				"semanticLabel":        "",
				"semanticHint":         "",
				"excludeFromSemantics": false,
			},
		})
	}
	return map[string]any{
		"templateRef":       "assistant.answer.default@" + templateDigest,
		"templateDigest":    templateDigest,
		"revision":          int64(1),
		"rootNodeId":        "root",
		"nodes":             nodes,
		"dataDigest":        dataDigest,
		"selectedVariant":   presentationVariant(request.SurfaceCapabilities),
		"fallbackMarkdown":  answer,
		"fallbackPlainText": answer,
		"committedAt":       "",
	}, nil
}

func buildDeviceActionApprovalNodes(
	pendingApproval map[string]any,
) ([]map[string]any, error) {
	toolUseID := executionString(pendingApproval, "toolUseId")
	continuationToken := executionString(pendingApproval, "continuationToken")
	proposal := objectMap(pendingApproval["proposal"])
	input := objectMap(proposal["input"])
	toolName := executionString(proposal, "toolName")
	title := executionString(input, "title")
	startsAt := executionString(input, "startsAt")
	if toolUseID == "" || continuationToken == "" ||
		toolName != "calendar_create_reminder" ||
		title == "" || startsAt == "" {
		return nil, fmt.Errorf("invalid calendar device action proposal")
	}
	actionPayload := map[string]any{
		"decision":          "approved",
		"continuationToken": continuationToken,
		"deviceAction": map[string]any{
			"kind":           toolName,
			"idempotencyKey": toolUseID,
			"input":          cloneObject(input),
		},
	}
	approved := map[string]any{
		"intentId":             "approve_" + toolUseID,
		"operation":            "ContinueAssistantToolUse",
		"objectTypeRef":        "assistant_tool_use",
		"objectId":             toolUseID,
		"payload":              actionPayload,
		"requiresConfirmation": true,
	}
	rejected := map[string]any{
		"intentId":      "reject_" + toolUseID,
		"operation":     "ContinueAssistantToolUse",
		"objectTypeRef": "assistant_tool_use",
		"objectId":      toolUseID,
		"payload": map[string]any{
			"decision":          "rejected",
			"continuationToken": continuationToken,
		},
		"requiresConfirmation": true,
	}
	return []map[string]any{
		{
			"nodeId":       "root",
			"parentNodeId": "",
			"order":        0,
			"kind":         "confirmation_card",
			"title":        "确认创建系统日程",
			"body":         deviceActionFallbackMarkdown(pendingApproval),
			"action":       approved,
			"accessibility": map[string]any{
				"semanticLabel": "确认创建系统日程提醒",
			},
		},
		{
			"nodeId":       "reject_action",
			"parentNodeId": "root",
			"order":        0,
			"kind":         "action_group",
			"title":        "拒绝",
			"body":         "不创建",
			"action":       rejected,
			"accessibility": map[string]any{
				"semanticLabel": "拒绝创建系统日程提醒",
			},
		},
	}, nil
}

func deviceActionFallbackMarkdown(pendingApproval map[string]any) string {
	proposal := objectMap(pendingApproval["proposal"])
	input := objectMap(proposal["input"])
	title := executionString(input, "title")
	startsAt := executionString(input, "startsAt")
	if title == "" || startsAt == "" {
		return "需要确认后才能执行设备操作。"
	}
	return fmt.Sprintf("将在系统日历创建“%s”，开始时间：%s。", title, startsAt)
}

func supportsPresentationNode(capabilities map[string]any, kind string) bool {
	switch values := capabilities["supportedNodeKinds"].(type) {
	case []string:
		for _, value := range values {
			if strings.TrimSpace(value) == kind {
				return true
			}
		}
	case []any:
		for _, value := range values {
			if strings.TrimSpace(stringValue(value)) == kind {
				return true
			}
		}
	}
	return false
}

func presentationVariant(capabilities map[string]any) string {
	viewportClass := strings.TrimSpace(executionString(capabilities, "viewportClass"))
	density := strings.TrimSpace(executionString(capabilities, "density"))
	switch {
	case viewportClass != "" && density != "":
		return viewportClass + "_" + density
	case viewportClass != "":
		return viewportClass
	case density != "":
		return density
	default:
		return "standard"
	}
}

func stringSliceContains(values []string, target string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == target {
			return true
		}
	}
	return false
}

func sha256Digest(value string) string {
	digest := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(digest[:])
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
	surfaceID := executionString(request.SurfaceCapabilities, "surfaceId")
	trigger := decodeExecutionTrigger(request.Trigger)
	turnType := "user"
	if trigger.Type != "user_message" {
		turnType = "proactive"
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
		PageContext:     pageContext,
		Trigger:         trigger,
		ClientRequestID: request.IdempotencyPrefix,
		RequestContext: assistant.AssistantRunRequestContext{
			SurfaceID: surfaceID,
			PersonaID: request.UserID,
			TraceID:   request.RunID,
		},
		SessionPreferenceFacts: append(
			[]preferencemodel.Snapshot(nil),
			request.SessionPreferenceFacts...,
		),
		LongTermPreferenceFacts: append(
			[]preferencemodel.Snapshot(nil),
			request.LongTermPreferenceFacts...,
		),
		TraceID:   request.RunID,
		CreatedAt: executionStartTime(request.CreatedAt),
	}
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
