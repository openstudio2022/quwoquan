package application

import (
	"context"
	"errors"

	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/domain"
)

type Store interface {
	AppendIfAbsent(context.Context, domain.Fact) (bool, error)
}

type Appender struct{ store Store }

func NewAppender(store Store) *Appender { return &Appender{store: store} }

func (a *Appender) Append(ctx context.Context, attempt domain.Fact) (bool, error) {
	if a == nil || a.store == nil {
		return false, errors.New("external interaction attempt ledger is unavailable")
	}
	canonical, err := domain.NewFact(attempt)
	if err != nil {
		return false, err
	}
	return a.store.AppendIfAbsent(ctx, canonical)
}
