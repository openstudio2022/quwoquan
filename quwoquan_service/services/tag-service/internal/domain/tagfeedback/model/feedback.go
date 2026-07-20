// Package model 定义 TagFeedback 不可变反馈事实。
// typed append + (actorId, idempotencyKey) 唯一约束去重；不修改 TagNodeView
// 或 TagTaxonomyRelease。
package model

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidArgument     = errors.New("tag feedback invalid argument")
	ErrInvalidAction       = errors.New("tag feedback invalid action")
	ErrIdempotencyConflict = errors.New("tag feedback idempotency key reused with a different command")
)

var validActions = map[string]struct{}{
	"click":   {},
	"ignore":  {},
	"correct": {},
}

// Feedback 是一条事实记录。
type Feedback struct {
	ID             string    `bson:"_id"`
	ActorID        string    `bson:"actorId"`
	ActorKind      string    `bson:"actorKind"`
	TagRef         string    `bson:"tagRef"`
	Action         string    `bson:"action"`
	Context        string    `bson:"context,omitempty"`
	IdempotencyKey string    `bson:"idempotencyKey"`
	RecordedAt     time.Time `bson:"recordedAt"`
}

// NewFeedback 校验并构造事实。
func NewFeedback(id, actorID, actorKind, tagRef, action, contextText, idempotencyKey string, now time.Time) (Feedback, error) {
	actorID = strings.TrimSpace(actorID)
	tagRef = strings.TrimSpace(tagRef)
	action = strings.TrimSpace(strings.ToLower(action))
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if id == "" || actorID == "" || tagRef == "" || idempotencyKey == "" {
		return Feedback{}, ErrInvalidArgument
	}
	if _, ok := validActions[action]; !ok {
		return Feedback{}, ErrInvalidAction
	}
	return Feedback{
		ID:             id,
		ActorID:        actorID,
		ActorKind:      strings.TrimSpace(actorKind),
		TagRef:         tagRef,
		Action:         action,
		Context:        strings.TrimSpace(contextText),
		IdempotencyKey: idempotencyKey,
		RecordedAt:     now.UTC(),
	}, nil
}
