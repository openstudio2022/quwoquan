package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

type DeadLetter struct {
	DeadLetterID string
	AttemptID    string
	FailureCode  string
	PayloadHash  string
	FailedAt     time.Time
}

type Store interface {
	AppendIfAbsent(context.Context, DeadLetter) (bool, error)
}

type Appender struct{ store Store }

func NewAppender(store Store) *Appender { return &Appender{store: store} }

func (a *Appender) Append(ctx context.Context, deadLetter DeadLetter) (bool, error) {
	if a == nil || a.store == nil {
		return false, errors.New("external interaction dead-letter store is unavailable")
	}
	if strings.TrimSpace(deadLetter.DeadLetterID) == "" || strings.TrimSpace(deadLetter.AttemptID) == "" || strings.TrimSpace(deadLetter.FailureCode) == "" || strings.TrimSpace(deadLetter.PayloadHash) == "" || deadLetter.FailedAt.IsZero() {
		return false, errors.New("external interaction dead-letter fact is incomplete")
	}
	return a.store.AppendIfAbsent(ctx, deadLetter)
}
