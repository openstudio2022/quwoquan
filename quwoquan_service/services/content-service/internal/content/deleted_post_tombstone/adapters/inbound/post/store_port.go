package post

import (
	"context"

	rtobs "quwoquan_service/runtime/observability"
	tombstonemodel "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/model"
	tombstoneports "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/ports"
)

// 契约 runtime_entrypoints[].telemetry.metric 同名计数器（outcome=ok|error）。
var tombstoneAppendOutcomes = rtobs.NewEntrypointOutcomeCounter("content_deleted_post_tombstone_append")

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
	created, err := port.store.AppendIfAbsent(ctx, tombstone)
	outcome := "ok"
	if err != nil {
		outcome = "error"
	}
	tombstoneAppendOutcomes.WithLabelValues(outcome).Inc()
	return created, err
}

func (port *StorePort) Find(
	ctx context.Context,
	postID string,
) (tombstonemodel.Tombstone, bool, error) {
	return port.store.Find(ctx, postID)
}

var _ tombstoneports.Store = (*StorePort)(nil)
