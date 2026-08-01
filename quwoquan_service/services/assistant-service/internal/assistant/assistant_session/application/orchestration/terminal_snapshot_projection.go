package orchestration

import (
	"encoding/json"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/streaming"
	"sort"
	"strings"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

const (
	maxTerminalSnapshotProcesses  = 32
	maxTerminalSnapshotReferences = 5
)

// ProjectAssistantRunTerminalSnapshot deterministically reduces persisted run
// events to the public terminal snapshot without exposing internal material.
func ProjectAssistantRunTerminalSnapshot(
	events []streaming.Envelope,
	selectedPolicyRef *assistant.AssistantSelectedPolicyRef,
) assistant.AssistantRunTerminalSnapshot {
	snapshot := assistant.AssistantRunTerminalSnapshot{
		Processes: []assistant.AssistantRunVisibleProcess{},
	}
	if selectedPolicyRef != nil &&
		strings.TrimSpace(selectedPolicyRef.PolicyID) != "" &&
		strings.TrimSpace(selectedPolicyRef.ReleaseDigest) != "" &&
		strings.TrimSpace(selectedPolicyRef.Cohort) != "" {
		value := assistant.AssistantSelectedPolicyRef{
			PolicyID:      strings.TrimSpace(selectedPolicyRef.PolicyID),
			ReleaseDigest: strings.TrimSpace(selectedPolicyRef.ReleaseDigest),
			Cohort:        strings.TrimSpace(selectedPolicyRef.Cohort),
		}
		snapshot.SelectedPolicyRef = &value
	}

	ordered := append([]streaming.Envelope(nil), events...)
	sort.SliceStable(ordered, func(i, j int) bool {
		return ordered[i].Seq < ordered[j].Seq
	})
	seenSeq := make(map[uint64]struct{}, len(ordered))
	for _, event := range ordered {
		if _, duplicate := seenSeq[event.Seq]; duplicate {
			continue
		}
		seenSeq[event.Seq] = struct{}{}

		switch assistantstreaming.AssistantStreamEventType(event.EventType) {
		case assistantstreaming.AssistantStreamEventProcessReplace:
			snapshot.Processes = visibleProcessesFromPayload(event.Payload["processes"])
		case assistantstreaming.AssistantStreamEventProcessAppend, assistantstreaming.AssistantStreamEventProcessCommit:
			process, ok := visibleProcessFromPayload(event.Payload["process"])
			if ok {
				snapshot.Processes = upsertVisibleProcess(snapshot.Processes, process)
			}
		case assistantstreaming.AssistantStreamEventAnswerDelta:
			snapshot.AnswerText += stringValue(event.Payload["text"])
		case assistantstreaming.AssistantStreamEventCompleted:
			if finalAnswer := strings.TrimSpace(stringValue(event.Payload["finalAnswer"])); finalAnswer != "" {
				snapshot.AnswerText = finalAnswer
			} else if finalAnswer := strings.TrimSpace(stringValue(event.Payload["text"])); finalAnswer != "" {
				snapshot.AnswerText = finalAnswer
			}
		case assistantstreaming.AssistantStreamEventFailed:
			if event.RuntimeFailure != nil {
				failure := publicTerminalFailure(*event.RuntimeFailure)
				snapshot.Failure = &failure
			}
		}
	}
	snapshot.AnswerText = strings.TrimSpace(snapshot.AnswerText)
	sort.SliceStable(snapshot.Processes, func(i, j int) bool {
		if snapshot.Processes[i].Order == snapshot.Processes[j].Order {
			return snapshot.Processes[i].ProcessID < snapshot.Processes[j].ProcessID
		}
		return snapshot.Processes[i].Order < snapshot.Processes[j].Order
	})
	return snapshot
}

func publicTerminalFailure(failure rtfailures.Failure) assistant.AssistantRunTerminalFailure {
	normalized := failure.Normalized()
	return assistant.AssistantRunTerminalFailure{
		Code:   strings.TrimSpace(normalized.Code),
		Origin: string(normalized.Origin),
		Kind:   string(normalized.Kind),
		Nature: string(normalized.Nature),
	}
}

func runtimeFailureFromTerminal(
	failure assistant.AssistantRunTerminalFailure,
) *rtfailures.Failure {
	normalized := rtfailures.Failure{
		Code:   strings.TrimSpace(failure.Code),
		Origin: rtfailures.Origin(strings.TrimSpace(failure.Origin)),
		Kind:   rtfailures.Kind(strings.TrimSpace(failure.Kind)),
		Nature: rtfailures.Nature(strings.TrimSpace(failure.Nature)),
	}.Normalized()
	return &normalized
}

func visibleProcessesFromPayload(raw any) []assistant.AssistantRunVisibleProcess {
	if raw == nil {
		return []assistant.AssistantRunVisibleProcess{}
	}
	payload, err := json.Marshal(raw)
	if err != nil {
		return []assistant.AssistantRunVisibleProcess{}
	}
	var decoded []assistant.AssistantRunVisibleProcess
	if err := json.Unmarshal(payload, &decoded); err != nil {
		return []assistant.AssistantRunVisibleProcess{}
	}
	result := make([]assistant.AssistantRunVisibleProcess, 0, len(decoded))
	for _, process := range decoded {
		if len(result) >= maxTerminalSnapshotProcesses {
			break
		}
		normalized, ok := normalizeVisibleProcess(process)
		if !ok {
			continue
		}
		result = upsertVisibleProcess(result, normalized)
	}
	return result
}

func visibleProcessFromPayload(raw any) (assistant.AssistantRunVisibleProcess, bool) {
	switch process := raw.(type) {
	case assistant.AssistantRunVisibleProcess:
		return normalizeVisibleProcess(process)
	case *assistant.AssistantRunVisibleProcess:
		if process == nil {
			return assistant.AssistantRunVisibleProcess{}, false
		}
		return normalizeVisibleProcess(*process)
	}
	payload, err := json.Marshal(raw)
	if err != nil {
		return assistant.AssistantRunVisibleProcess{}, false
	}
	var process assistant.AssistantRunVisibleProcess
	if err := json.Unmarshal(payload, &process); err != nil {
		return assistant.AssistantRunVisibleProcess{}, false
	}
	return normalizeVisibleProcess(process)
}

func normalizeVisibleProcess(
	process assistant.AssistantRunVisibleProcess,
) (assistant.AssistantRunVisibleProcess, bool) {
	process.ProcessID = trimSnapshotText(process.ProcessID, 160)
	process.Scope = trimSnapshotText(process.Scope, 80)
	process.Stage = trimSnapshotText(process.Stage, 80)
	process.Status = trimSnapshotText(process.Status, 80)
	if process.ProcessID == "" || process.Scope == "" || process.Stage == "" || process.Status == "" {
		return assistant.AssistantRunVisibleProcess{}, false
	}
	process.Summary = userProcessSummary(process.Summary)
	process.SkillID = trimSnapshotText(process.SkillID, 160)
	process.DomainID = trimSnapshotText(process.DomainID, 160)
	process.SearchedDocumentCount = nonNegative(process.SearchedDocumentCount)
	process.ProcessedDocumentCount = nonNegative(process.ProcessedDocumentCount)
	process.AcceptedDocumentCount = nonNegative(process.AcceptedDocumentCount)

	references := make([]assistant.AssistantRunVisibleReference, 0, len(process.AcceptedReferences))
	for _, reference := range process.AcceptedReferences {
		if len(references) >= maxTerminalSnapshotReferences {
			break
		}
		destination, ok := citationDestinationFromMap(
			citationDestinationMap(reference.Destination),
		)
		if !ok {
			continue
		}
		references = append(references, assistant.AssistantRunVisibleReference{
			Title:       trimSnapshotText(reference.Title, 240),
			Destination: destination,
			Source:      trimSnapshotText(reference.Source, 160),
			Snippet:     trimSnapshotText(reference.Snippet, 600),
		})
	}
	process.AcceptedReferences = references
	return process, true
}

func upsertVisibleProcess(
	processes []assistant.AssistantRunVisibleProcess,
	process assistant.AssistantRunVisibleProcess,
) []assistant.AssistantRunVisibleProcess {
	for index := range processes {
		if processes[index].ProcessID == process.ProcessID {
			processes[index] = process
			return processes
		}
	}
	if len(processes) >= maxTerminalSnapshotProcesses {
		return processes
	}
	return append(processes, process)
}

func trimSnapshotText(value string, maxRunes int) string {
	value = strings.TrimSpace(value)
	runes := []rune(value)
	if maxRunes > 0 && len(runes) > maxRunes {
		return string(runes[:maxRunes])
	}
	return value
}

func nonNegative(value int) int {
	if value < 0 {
		return 0
	}
	return value
}
