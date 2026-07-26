package circlegroup

import (
	"context"
	"fmt"
	"strings"

	groupports "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/ports"
)

// ConversationProvisionedFact is the trusted Chat outbox payload received from
// CircleGroupConversationProvisioned Redis Stream. It intentionally has no
// public HTTP representation.
type ConversationProvisionedFact struct {
	EventID        string
	CircleID       string
	CircleGroupID  string
	ConversationID string
}

type ConversationBindingProjector struct {
	writer groupports.ConversationBindingWriter
}

type ConversationBindingProjection interface {
	Apply(context.Context, ConversationProvisionedFact) error
}

func NewConversationBindingProjector(
	writer groupports.ConversationBindingWriter,
) *ConversationBindingProjector {
	return &ConversationBindingProjector{writer: writer}
}

func (p *ConversationBindingProjector) Apply(
	ctx context.Context,
	fact ConversationProvisionedFact,
) error {
	if p == nil || p.writer == nil {
		return fmt.Errorf("circle group conversation binding projector is not configured")
	}
	fact.EventID = strings.TrimSpace(fact.EventID)
	fact.CircleID = strings.TrimSpace(fact.CircleID)
	fact.CircleGroupID = strings.TrimSpace(fact.CircleGroupID)
	fact.ConversationID = strings.TrimSpace(fact.ConversationID)
	if fact.EventID == "" || fact.CircleID == "" || fact.CircleGroupID == "" ||
		fact.ConversationID == "" {
		return fmt.Errorf("CircleGroupConversationProvisioned payload is incomplete")
	}
	return p.writer.BindConversation(
		ctx,
		fact.EventID,
		fact.CircleID,
		fact.CircleGroupID,
		fact.ConversationID,
	)
}
