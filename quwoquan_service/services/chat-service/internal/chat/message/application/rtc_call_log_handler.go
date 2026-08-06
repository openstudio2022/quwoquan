package application

import (
	"context"
	"fmt"
	"strings"
	"time"
)

type RtcCallEndedFact struct {
	EventID        string
	CallID         string
	CallType       string
	InitiatorID    string
	ConversationID string
	EndReason      string
	DurationMs     int64
	StartedAt      time.Time
	EndedAt        time.Time
}

type RtcCallLogProjection interface {
	ProjectRtcCallLog(context.Context, RtcCallEndedFact) error
}

// RtcCallLogHandler is the chat.message lifecycle boundary for rtc CallEnded.
// It owns fail-closed source validation; the injected projection port owns the
// atomic Message/outbox commit.
type RtcCallLogHandler struct{ projection RtcCallLogProjection }

func NewRtcCallLogHandler(projection RtcCallLogProjection) *RtcCallLogHandler {
	return &RtcCallLogHandler{projection: projection}
}

func (handler *RtcCallLogHandler) AppendRtcCallLog(
	ctx context.Context,
	fact RtcCallEndedFact,
) error {
	if handler == nil || handler.projection == nil {
		return fmt.Errorf("RTC call log handler is not configured")
	}
	fact.EventID = strings.TrimSpace(fact.EventID)
	fact.CallID = strings.TrimSpace(fact.CallID)
	fact.CallType = strings.TrimSpace(fact.CallType)
	fact.InitiatorID = strings.TrimSpace(fact.InitiatorID)
	fact.ConversationID = strings.TrimSpace(fact.ConversationID)
	fact.EndReason = strings.TrimSpace(fact.EndReason)
	if fact.EventID == "" || fact.CallID == "" {
		return fmt.Errorf("RTC CallEnded eventId and callId are required")
	}
	if fact.DurationMs < 0 {
		return fmt.Errorf("RTC CallEnded durationMs must not be negative")
	}
	return handler.projection.ProjectRtcCallLog(ctx, fact)
}
