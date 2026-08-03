package post

import (
	"context"

	tombstonemodel "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/model"
	tombstoneports "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/ports"
)

type StorePort struct {
	store tombstoneports.Store
}

func NewStorePort(store tombstoneports.Store) *StorePort {
	if store == nil {
		panic("DeletedPostTombstone Post port requires object store")
	}
	return &StorePort{store: store}
}

func (port *StorePort) EnsureIndexes(ctx context.Context) error {
	return port.store.EnsureIndexes(ctx)
}

func (port *StorePort) AppendIfAbsent(
	ctx context.Context,
	tombstone tombstonemodel.Tombstone,
) (bool, error) {
	return port.store.AppendIfAbsent(ctx, tombstone)
}

func (port *StorePort) Find(
	ctx context.Context,
	postID string,
) (tombstonemodel.Tombstone, bool, error) {
	return port.store.Find(ctx, postID)
}

var _ tombstoneports.Store = (*StorePort)(nil)
