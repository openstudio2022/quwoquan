package orchestration

import (
	"errors"
	"strings"

	"quwoquan_service/runtime/streaming"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

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
