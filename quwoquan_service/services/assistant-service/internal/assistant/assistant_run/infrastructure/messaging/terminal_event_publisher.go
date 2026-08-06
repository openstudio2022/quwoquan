package messaging

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

const (
	AssistantRunEventStream    = "assistant.assistant_run"
	AssistantRunEventRetention = 7 * 24 * time.Hour
)

type TerminalEventPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewTerminalEventPublisher(
	transport runtimemessaging.DurableRecordAppender,
) (*TerminalEventPublisher, error) {
	if transport == nil {
		return nil, errors.New("assistant run durable transport is required")
	}
	return &TerminalEventPublisher{transport: transport}, nil
}

func (publisher *TerminalEventPublisher) PublishTerminalEvent(
	ctx context.Context,
	event runruntime.TerminalEvent,
) error {
	// AssistantRunCompleted is the only transactional event declared by the
	// object contract. Failure/cancellation continue to drive the internal
	// learning and compaction handlers without inventing a parallel event.
	if strings.TrimSpace(event.Outcome) != "completed" {
		return nil
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.RunID) == "" ||
		strings.TrimSpace(event.UserID) == "" || strings.TrimSpace(event.PersonaID) == "" ||
		event.OccurredAt.IsZero() || event.AttemptCount <= 0 {
		return errors.New("assistant run completed event is incomplete")
	}
	if event.PersonaContextVersion != nil && *event.PersonaContextVersion < 0 {
		return errors.New("assistant run persona context version is invalid")
	}
	if event.ToolsCalled != nil {
		for _, toolName := range *event.ToolsCalled {
			if strings.TrimSpace(toolName) == "" {
				return errors.New("assistant run completed event has an invalid tool name")
			}
		}
	}
	if event.LLMModel != nil && strings.TrimSpace(*event.LLMModel) == "" {
		return errors.New("assistant run completed event has an invalid model identity")
	}
	if event.LLMTokensUsed != nil && *event.LLMTokensUsed < 0 {
		return errors.New("assistant run completed event has invalid token usage")
	}
	if event.LatencyMS != nil && *event.LatencyMS < 0 {
		return errors.New("assistant run completed event has invalid latency")
	}
	payload, err := json.Marshal(struct {
		ID                    string    `json:"_id"`
		UserID                string    `json:"userId"`
		PersonaID             string    `json:"personaId"`
		PersonaContextVersion *int64    `json:"personaContextVersion"`
		Status                string    `json:"status"`
		ToolsCalled           *[]string `json:"toolsCalled"`
		LLMModel              *string   `json:"llmModel"`
		LLMTokensUsed         *int64    `json:"llmTokensUsed"`
		LatencyMS             *int64    `json:"latencyMs"`
		SatisfactionScore     *float64  `json:"satisfactionScore"`
	}{
		ID: event.RunID, UserID: event.UserID, PersonaID: event.PersonaID,
		PersonaContextVersion: event.PersonaContextVersion,
		Status:                event.Outcome, ToolsCalled: event.ToolsCalled,
		LLMModel: event.LLMModel, LLMTokensUsed: event.LLMTokensUsed,
		LatencyMS: event.LatencyMS, SatisfactionScore: event.SatisfactionScore,
	})
	if err != nil {
		return fmt.Errorf("encode assistant run completed event: %w", err)
	}
	if err := runtimemessaging.AppendDurableRecord(ctx, publisher.transport,
		AssistantRunEventStream,
		map[string]string{
			"eventId": event.EventID, "eventName": "AssistantRunCompleted",
			"aggregateType": "AssistantRun", "aggregateId": event.RunID,
			"occurredAt": event.OccurredAt.UTC().Format(time.RFC3339Nano),
			"payload":    string(payload),
		}, AssistantRunEventRetention,
	); err != nil {
		return fmt.Errorf("append assistant run completed event: %w", err)
	}
	return nil
}

var _ runruntime.TerminalEventPublisher = (*TerminalEventPublisher)(nil)
