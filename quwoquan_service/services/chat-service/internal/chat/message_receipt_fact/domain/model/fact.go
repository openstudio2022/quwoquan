package model

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrIdentityIncomplete = errors.New("message receipt fact identity is incomplete")
	ErrReadAtRequired     = errors.New("message receipt fact readAt is required")
	ErrIdentityConflict   = errors.New("message receipt fact identity conflicts with the committed fact")
)

// Fact is the immutable proof that one persona read one Message. The stable
// business identity is (messageId, userId); ID is the persisted fact identity.
type Fact struct {
	ID             string    `json:"id" bson:"_id"`
	MessageID      string    `json:"messageId" bson:"messageId"`
	ConversationID string    `json:"conversationId" bson:"conversationId"`
	UserID         string    `json:"userId" bson:"userId"`
	ReadAt         time.Time `json:"readAt" bson:"readAt"`
}

func (fact Fact) Validate() error {
	if strings.TrimSpace(fact.ID) == "" ||
		strings.TrimSpace(fact.MessageID) == "" ||
		strings.TrimSpace(fact.ConversationID) == "" ||
		strings.TrimSpace(fact.UserID) == "" {
		return ErrIdentityIncomplete
	}
	if fact.ReadAt.IsZero() {
		return ErrReadAtRequired
	}
	return nil
}

func (fact Fact) SameImmutableValue(other Fact) bool {
	return fact.ID == other.ID &&
		fact.MessageID == other.MessageID &&
		fact.ConversationID == other.ConversationID &&
		fact.UserID == other.UserID &&
		fact.ReadAt.Equal(other.ReadAt)
}
