package orchestration

import (
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/streaming"
	"strings"

	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

func finalAnswerTextFromEvents(events []streaming.Envelope) string {
	for i := len(events) - 1; i >= 0; i-- {
		event := events[i]
		if event.EventType != string(assistantstreaming.AssistantStreamEventCompleted) {
			continue
		}
		if text := strings.TrimSpace(stringValue(event.Payload["finalAnswer"])); text != "" {
			return text
		}
		if text := strings.TrimSpace(stringValue(event.Payload["text"])); text != "" {
			return text
		}
	}
	return ""
}

func skillIDFromEvents(events []streaming.Envelope) string {
	for _, event := range events {
		if event.EventType != string(assistantstreaming.AssistantStreamEventProcessAppend) &&
			event.EventType != string(assistantstreaming.AssistantStreamEventProcessCommit) {
			continue
		}
		if skillID := streamProcessString(event.Payload, "skillId"); skillID != "" {
			return skillID
		}
	}
	return ""
}

func domainIDFromEvents(events []streaming.Envelope) string {
	for _, event := range events {
		if event.EventType != string(assistantstreaming.AssistantStreamEventProcessAppend) &&
			event.EventType != string(assistantstreaming.AssistantStreamEventProcessCommit) {
			continue
		}
		if domainID := streamProcessString(event.Payload, "domainId"); domainID != "" {
			return domainID
		}
	}
	return ""
}

func streamProcessString(payload map[string]any, field string) string {
	raw, ok := payload["process"]
	if !ok {
		return ""
	}
	switch process := raw.(type) {
	case assistant.AssistantRunVisibleProcess:
		switch field {
		case "skillId":
			return strings.TrimSpace(process.SkillID)
		case "domainId":
			return strings.TrimSpace(process.DomainID)
		}
	case *assistant.AssistantRunVisibleProcess:
		if process == nil {
			return ""
		}
		return streamProcessString(map[string]any{"process": *process}, field)
	case map[string]any:
		return strings.TrimSpace(stringValue(process[field]))
	}
	return ""
}
