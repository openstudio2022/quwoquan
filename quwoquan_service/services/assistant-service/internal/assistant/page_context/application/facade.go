package application

import (
	"context"
	"errors"
	"fmt"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/ports"
)

var ErrStoreUnavailable = errors.New("page context store is unavailable")

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
		return model.Receipt{}, ErrStoreUnavailable
	}
	pageContext, err := model.New(accountID, personaID, snapshot, f.now())
	if err != nil {
		return model.Receipt{}, err
	}
	if err := f.store.Put(ctx, pageContext); err != nil {
		return model.Receipt{}, fmt.Errorf("%w: %v", ErrStoreUnavailable, err)
	}
	return model.Receipt{
		Accepted:   true,
		ContextKey: model.StorageKey(pageContext.AccountID),
		ExpiresAt:  pageContext.ExpiresAt,
	}, nil
}

func (f *Facade) Current(ctx context.Context, accountID string) (*model.PageContext, error) {
	if f == nil || f.store == nil {
		return nil, ErrStoreUnavailable
	}
	pageContext, err := f.store.Get(ctx, accountID)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrStoreUnavailable, err)
	}
	if pageContext == nil {
		return nil, nil
	}
	if !pageContext.ExpiresAt.After(f.now()) {
		return nil, nil
	}
	return pageContext, nil
}
