// Package model 定义 TagFeedbackFact 不可变反馈事实。
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

// validActions 与 tag_feedback_fact/fields.yaml 的 TagFeedbackAction 同集。
// dislike 是唯一的负向取值：ignore 只清除既有偏好，correct 只标记推荐错误，
// 两者都无法表达「不要再给我这个标签」。
var validActions = map[string]struct{}{
	"click":   {},
	"ignore":  {},
	"correct": {},
	"dislike": {},
}

// Feedback 是一条事实记录。
type Feedback struct {
	ID               string     `bson:"_id"`
	ActorID          string     `bson:"actorId"`
	ActorKind        string     `bson:"actorKind"`
	TagRef           string     `bson:"tagRef"`
	Action           string     `bson:"action"`
	Context          string     `bson:"context,omitempty"`
	IdempotencyKey   string     `bson:"idempotencyKey"`
	RecordedAt       time.Time  `bson:"recordedAt"`
	EventPublishedAt *time.Time `bson:"eventPublishedAt,omitempty"`
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
