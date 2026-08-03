package application

import (
	"context"
	"errors"

	tombstonemodel "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/model"
	tombstoneports "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/ports"
)

type Appender struct{ store tombstoneports.Store }

func NewAppender(store tombstoneports.Store) *Appender { return &Appender{store: store} }

func (a *Appender) Append(ctx context.Context, tombstone tombstonemodel.Tombstone) (bool, error) {
	if a == nil || a.store == nil {
		return false, errors.New("deleted post tombstone store is unavailable")
	}
	if err := tombstone.Validate(); err != nil {
		return false, err
	}
	return a.store.AppendIfAbsent(ctx, tombstone)
}
