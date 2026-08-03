package application

import (
	"context"
	"errors"

	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/domain"
)

type Repository interface {
	AppendIfAbsent(context.Context, domain.Fact) (bool, error)
	ListByRequest(context.Context, string) ([]domain.Fact, error)
}

type Appender struct{ store Repository }

func NewAppender(store Repository) *Appender { return &Appender{store: store} }

func (a *Appender) Append(ctx context.Context, deadLetter domain.Fact) (bool, error) {
	if a == nil || a.store == nil {
		return false, errors.New("external interaction dead-letter store is unavailable")
	}
	canonical, err := domain.NewFact(deadLetter)
	if err != nil {
		return false, err
	}
	return a.store.AppendIfAbsent(ctx, canonical)
}

func (a *Appender) ListByRequest(ctx context.Context, requestID string) ([]domain.Fact, error) {
	if a == nil || a.store == nil {
		return nil, errors.New("external interaction dead-letter store is unavailable")
	}
	return a.store.ListByRequest(ctx, requestID)
}
