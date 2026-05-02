package streaming

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/runtime/failures"
)

type Envelope struct {
	ID             string            `json:"id,omitempty"`
	EventID        string            `json:"eventId,omitempty"`
	Topic          string            `json:"topic,omitempty"`
	StreamID       string            `json:"streamId,omitempty"`
	Event          string            `json:"event"`
	EventType      string            `json:"eventType,omitempty"`
	Seq            uint64            `json:"seq"`
	ResumeToken    string            `json:"resumeToken,omitempty"`
	TraceID        string            `json:"traceId,omitempty"`
	Data           json.RawMessage   `json:"data,omitempty"`
	Payload        map[string]any    `json:"payload,omitempty"`
	RuntimeFailure *failures.Failure `json:"runtimeFailure,omitempty"`
	CreatedAt      time.Time         `json:"createdAt,omitempty"`
}

func NewEnvelope(event string, seq uint64, data any) (Envelope, error) {
	if strings.TrimSpace(event) == "" {
		return Envelope{}, fmt.Errorf("runtime/streaming: event is required")
	}
	payload, err := json.Marshal(data)
	if err != nil {
		return Envelope{}, fmt.Errorf("runtime/streaming: marshal data: %w", err)
	}
	return Envelope{
		Event:     event,
		EventType: event,
		Seq:       seq,
		Data:      payload,
	}, nil
}

func (e Envelope) Normalized() Envelope {
	e.ID = strings.TrimSpace(e.ID)
	e.EventID = strings.TrimSpace(e.EventID)
	e.Topic = strings.TrimSpace(e.Topic)
	e.StreamID = strings.TrimSpace(e.StreamID)
	e.Event = strings.TrimSpace(e.Event)
	e.EventType = strings.TrimSpace(e.EventType)
	e.TraceID = strings.TrimSpace(e.TraceID)
	if e.Event == "" {
		e.Event = e.EventType
	}
	if e.EventType == "" {
		e.EventType = e.Event
	}
	if e.Payload == nil {
		e.Payload = map[string]any{}
	}
	if e.CreatedAt.IsZero() {
		e.CreatedAt = time.Now().UTC()
	} else {
		e.CreatedAt = e.CreatedAt.UTC()
	}
	if e.ResumeToken == "" && e.StreamID != "" {
		e.ResumeToken = NewResumeToken(e.StreamID, e.Seq)
	}
	if e.RuntimeFailure != nil {
		normalized := e.RuntimeFailure.Normalized()
		e.RuntimeFailure = &normalized
	}
	return e
}

func (e Envelope) DecodeData(target any) error {
	if len(e.Data) == 0 {
		return nil
	}
	if err := json.Unmarshal(e.Data, target); err != nil {
		return fmt.Errorf("runtime/streaming: decode data: %w", err)
	}
	return nil
}

func (e Envelope) SSEEvent() SSEEvent {
	normalized := e.Normalized()
	eventID := normalized.ResumeToken
	if eventID == "" {
		eventID = normalized.EventID
	}
	if eventID == "" {
		eventID = normalized.ID
	}
	return SSEEvent{
		ID:    eventID,
		Event: normalized.Event,
		Data:  normalized,
	}
}

func NewResumeToken(streamID string, seq uint64) string {
	raw := strings.TrimSpace(streamID) + ":" + strconv.FormatUint(seq, 10)
	return base64.RawURLEncoding.EncodeToString([]byte(raw))
}

func ParseResumeToken(token string) (string, uint64, error) {
	raw, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(token))
	if err != nil {
		return "", 0, fmt.Errorf("runtime/streaming: decode resume token: %w", err)
	}
	parts := strings.SplitN(string(raw), ":", 2)
	if len(parts) != 2 || parts[0] == "" {
		return "", 0, fmt.Errorf("runtime/streaming: invalid resume token")
	}
	seq, err := strconv.ParseUint(parts[1], 10, 64)
	if err != nil {
		return "", 0, fmt.Errorf("runtime/streaming: invalid resume token seq: %w", err)
	}
	return parts[0], seq, nil
}
