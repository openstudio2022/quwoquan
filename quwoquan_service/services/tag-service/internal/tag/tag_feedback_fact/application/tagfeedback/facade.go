// Package tagfeedback 是 TagFeedbackFact append 命令门面。
package tagfeedback

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/domain/tagfeedback/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/domain/tagfeedback/ports"
)

// TagRefValidator 校验 tagRef 存在（复用 TagNodeView 只读投影）。
type TagRefValidator interface {
	TagRefExists(ctx context.Context, tagRef string) (bool, error)
}

var ErrTagRefNotFound = errors.New("tag feedback tagRef not found")

type Facade struct {
	sink      ports.Sink
	validator TagRefValidator
	now       func() time.Time
}

func NewFacade(sink ports.Sink, validator TagRefValidator) (*Facade, error) {
	if sink == nil {
		return nil, errors.New("tag feedback sink is required")
	}
	if validator == nil {
		return nil, errors.New("tag feedback validator is required")
	}
	return &Facade{sink: sink, validator: validator, now: time.Now}, nil
}

type AppendCommand struct {
	ActorID        string
	ActorKind      string
	TagRef         string
	Action         string
	Context        string
	IdempotencyKey string
}

type Result struct {
	Accepted bool
	Replayed bool
}

// Append 追加一条反馈事实；同 actor 同 Idempotency-Key 重放返回首次结果。
func (f *Facade) Append(ctx context.Context, command AppendCommand) (Result, error) {
	feedback, err := model.NewFeedback(
		deriveFeedbackID(command.ActorID, command.IdempotencyKey),
		command.ActorID, command.ActorKind, command.TagRef,
		command.Action, command.Context, command.IdempotencyKey, f.now())
	if err != nil {
		return Result{}, err
	}
	exists, err := f.validator.TagRefExists(ctx, feedback.TagRef)
	if err != nil {
		return Result{}, err
	}
	if !exists {
		return Result{}, ErrTagRefNotFound
	}
	_, replayed, err := f.sink.Append(ctx, feedback)
	if err != nil {
		return Result{}, err
	}
	return Result{Accepted: true, Replayed: replayed}, nil
}

func deriveFeedbackID(actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return "tagfb_" + hex.EncodeToString(sum[:12])
}
