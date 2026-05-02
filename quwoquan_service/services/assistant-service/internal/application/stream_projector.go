package application

import (
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type StreamProjector struct {
	Turn assistant.AssistantTurn
	Now  func() time.Time
	seq  uint64
}

func NewStreamProjector(turn assistant.AssistantTurn, now func() time.Time) *StreamProjector {
	return &StreamProjector{Turn: turn, Now: now}
}

func (p *StreamProjector) Event(eventType string, payload map[string]any) (streaming.Envelope, error) {
	return p.event(eventType, payload, nil)
}

func (p *StreamProjector) Failure(eventType string, payload map[string]any, failure rtfailures.Failure) (streaming.Envelope, error) {
	normalized := failure.Normalized()
	return p.event(eventType, payload, &normalized)
}

func (p *StreamProjector) event(eventType string, payload map[string]any, failure *rtfailures.Failure) (streaming.Envelope, error) {
	p.seq++
	if payload == nil {
		payload = map[string]any{}
	}
	canonicalType := canonicalStreamEventType(eventType)
	payload["schemaVersion"] = "assistant_stream_event.m5"
	payload["conversationId"] = p.Turn.ConversationID
	payload["turnId"] = p.Turn.TurnID
	payload["eventType"] = canonicalType
	payload["seq"] = p.seq
	payload["traceId"] = p.Turn.TraceID
	envelope, err := streaming.NewEnvelope(eventType, p.seq, payload)
	if err != nil {
		return streaming.Envelope{}, err
	}
	envelope.EventID = p.Turn.TurnID + ":" + eventType + ":" + time.Duration(p.seq).String()
	envelope.StreamID = p.Turn.TurnID
	envelope.Topic = "assistant.turn"
	envelope.TraceID = p.Turn.TraceID
	envelope.EventType = canonicalType
	envelope.Payload = payload
	envelope.RuntimeFailure = failure
	envelope.CreatedAt = p.now().Add(time.Duration(p.seq) * time.Millisecond)
	return envelope.Normalized(), nil
}

func (p *StreamProjector) now() time.Time {
	if p.Now != nil {
		return p.Now().UTC()
	}
	return time.Now().UTC()
}

func canonicalStreamEventType(eventType string) string {
	switch eventType {
	case "assistant.turn.started":
		return "turn_started"
	case "assistant.skill.selected":
		return "understanding_updated"
	case "assistant.reasoning.started", "assistant.model.delta":
		return "journey_step_updated"
	case "assistant.plan.updated":
		return "plan_updated"
	case "assistant.search_query.generated":
		return "search_query_generated"
	case "assistant.observation.assessed":
		return "observation_assessed"
	case "assistant.replan.requested":
		return "replan_requested"
	case "assistant.trace":
		return "understanding_updated"
	case "assistant.journey.updated":
		return "journey_step_updated"
	case "assistant.process_timeline.updated":
		return "journey_step_updated"
	case "assistant.tool.requested":
		return "tool_use_requested"
	case "assistant.tool.completed":
		return "tool_result_received"
	case "assistant.user_confirmation.requested":
		return "user_confirmation_requested"
	case "assistant.failure", "assistant.turn.failed":
		return "turn_failed"
	case "assistant.answer.delta":
		return "partial_answer"
	case "assistant.answer.final":
		return "final_answer"
	case "assistant.turn.completed":
		return "turn_completed"
	default:
		return eventType
	}
}
