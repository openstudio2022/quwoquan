package streaming

import (
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

// AssistantTurnEnvelope is the sole public Run projection. The aggregate holds
// authorization facts, page context, preference snapshots and internal audit
// metadata; none of those fields may cross the HTTP boundary accidentally.
//
// Its field names intentionally mirror the metadata-owned
// AssistantTurnEnvelopeWire schema. Keep any response-shape expansion
// metadata-first, then update this explicit projector.
type AssistantTurnEnvelope struct {
	TurnID           string                                  `json:"turnId"`
	ConversationID   string                                  `json:"conversationId"`
	TurnType         string                                  `json:"turnType"`
	Status           string                                  `json:"status"`
	SkillID          string                                  `json:"skillId"`
	DomainID         string                                  `json:"domainId"`
	Input            assistant.AssistantTurnInput            `json:"input"`
	Trigger          assistant.AssistantTurnTrigger          `json:"trigger"`
	StreamState      assistant.AssistantTurnStreamState      `json:"streamState"`
	TerminalSnapshot *assistant.AssistantRunTerminalSnapshot `json:"terminalSnapshot,omitempty"`
	TraceID          string                                  `json:"traceId"`
	CreatedAt        time.Time                               `json:"createdAt"`
	CompletedAt      *time.Time                              `json:"completedAt,omitempty"`
}

func ProjectAssistantTurnEnvelope(turn assistant.AssistantTurn) AssistantTurnEnvelope {
	return AssistantTurnEnvelope{
		TurnID:           turn.TurnID,
		ConversationID:   turn.ConversationID,
		TurnType:         turn.TurnType,
		Status:           turn.Status,
		SkillID:          turn.SkillID,
		DomainID:         turn.DomainID,
		Input:            turn.Input,
		Trigger:          turn.Trigger,
		StreamState:      turn.StreamState,
		TerminalSnapshot: turn.TerminalSnapshot,
		TraceID:          turn.TraceID,
		CreatedAt:        turn.CreatedAt,
		CompletedAt:      turn.CompletedAt,
	}
}
