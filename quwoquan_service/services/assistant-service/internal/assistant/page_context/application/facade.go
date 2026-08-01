package application

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/ports"
)

type Facade struct {
	store ports.Store
	now   func() time.Time
}

func NewFacade(store ports.Store, now func() time.Time) *Facade {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Facade{store: store, now: now}
}

func (f *Facade) Report(ctx context.Context, accountID, personaID string, snapshot model.Snapshot) (model.Receipt, error) {
	if f == nil || f.store == nil {
		return model.Receipt{}, errors.New("page context store is unavailable")
	}
	pageContext, err := model.New(accountID, personaID, snapshot, f.now())
	if err != nil {
		return model.Receipt{}, err
	}
	if err := f.store.Put(ctx, pageContext); err != nil {
		return model.Receipt{}, err
	}
	return model.Receipt{
		Accepted:   true,
		ContextKey: model.StorageKey(pageContext.AccountID),
		ExpiresAt:  pageContext.ExpiresAt,
	}, nil
}

func (f *Facade) Current(ctx context.Context, accountID string) (*model.PageContext, error) {
	if f == nil || f.store == nil {
		return nil, errors.New("page context store is unavailable")
	}
	pageContext, err := f.store.Get(ctx, accountID)
	if err != nil || pageContext == nil {
		return pageContext, err
	}
	if !pageContext.ExpiresAt.After(f.now()) {
		return nil, nil
	}
	return pageContext, nil
}
