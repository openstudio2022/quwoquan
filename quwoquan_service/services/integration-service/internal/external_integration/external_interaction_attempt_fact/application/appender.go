package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

type Attempt struct {
	AttemptID     string
	Provider      string
	Operation     string
	SubjectID     string
	Outcome       string
	SourceEventID string
	OccurredAt    time.Time
}

type Store interface {
	AppendIfAbsent(context.Context, Attempt) (bool, error)
}

type Appender struct{ store Store }

func NewAppender(store Store) *Appender { return &Appender{store: store} }

func (a *Appender) Append(ctx context.Context, attempt Attempt) (bool, error) {
	if a == nil || a.store == nil {
		return false, errors.New("external interaction attempt ledger is unavailable")
	}
	if strings.TrimSpace(attempt.AttemptID) == "" || strings.TrimSpace(attempt.Provider) == "" || strings.TrimSpace(attempt.Operation) == "" || strings.TrimSpace(attempt.SourceEventID) == "" || attempt.OccurredAt.IsZero() {
		return false, errors.New("external interaction attempt fact is incomplete")
	}
	return a.store.AppendIfAbsent(ctx, attempt)
}
