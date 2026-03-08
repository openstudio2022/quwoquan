package repository

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/block/model"
)

type BlockRepository interface {
	Create(ctx context.Context, edge *model.BlockEdge) (created bool, err error)
	Delete(ctx context.Context, blockerID, blockedID string) (deleted bool, err error)
	Exists(ctx context.Context, blockerID, blockedID string) (bool, error)
	ListByBlocker(ctx context.Context, blockerID string, cursor string, limit int) ([]model.BlockEdge, string, error)
}
