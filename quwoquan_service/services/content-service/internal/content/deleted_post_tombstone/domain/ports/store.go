package ports

import (
	"context"

	tombstonemodel "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/model"
)

// Store accepts the caller transaction context. DeletePost therefore commits
// Post state, receipt, outbox and tombstone atomically without making Post own
// the tombstone collection.
type Store interface {
	EnsureIndexes(context.Context) error
	AppendIfAbsent(context.Context, tombstonemodel.Tombstone) (bool, error)
	Find(context.Context, string) (tombstonemodel.Tombstone, bool, error)
}
