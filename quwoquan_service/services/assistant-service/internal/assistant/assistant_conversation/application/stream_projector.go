package application

import (
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

type StreamProjector struct {
	Turn assistant.AssistantTurn
	Now  func() time.Time
	seq  uint64
}

func NewStreamProjector(turn assistant.AssistantTurn, now func() time.Time) *StreamProjector {
	return NewStreamProjectorAt(turn, now, 0)
}

func NewStreamProjectorAt(
	turn assistant.AssistantTurn,
	now func() time.Time,
	afterSeq uint64,
) *StreamProjector {
	return &StreamProjector{Turn: turn, Now: now, seq: afterSeq}
}

func (p *StreamProjector) Event(eventType AssistantStreamEventType, payload map[string]any) (streaming.Envelope, error) {
	return p.event(eventType, payload, nil)
}

func (p *StreamProjector) Failure(eventType AssistantStreamEventType, payload map[string]any, failure rtfailures.Failure) (streaming.Envelope, error) {
	normalized := failure.Normalized()
	return p.event(eventType, payload, &normalized)
}

func (p *StreamProjector) event(eventType AssistantStreamEventType, payload map[string]any, failure *rtfailures.Failure) (streaming.Envelope, error) {
	if err := requireAssistantStreamEventType(eventType); err != nil {
		return streaming.Envelope{}, err
	}
	p.seq++
	if payload == nil {
		payload = map[string]any{}
	}
	payload["schema"] = "assistant_stream_event"
	payload["conversationId"] = p.Turn.ConversationID
	payload["turnId"] = p.Turn.TurnID
	payload["eventType"] = string(eventType)
	payload["seq"] = p.seq
	payload["traceId"] = p.Turn.TraceID
	envelope, err := streaming.NewEnvelope(string(eventType), p.seq, payload)
	if err != nil {
		return streaming.Envelope{}, err
	}
	envelope.EventID = p.Turn.TurnID + ":" + string(eventType) + ":" + time.Duration(p.seq).String()
	envelope.StreamID = p.Turn.TurnID
	envelope.Topic = "assistant.run"
	envelope.TraceID = p.Turn.TraceID
	envelope.EventType = string(eventType)
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
