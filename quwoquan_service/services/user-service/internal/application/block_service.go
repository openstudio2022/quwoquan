package application

import (
	"context"

	"github.com/google/uuid"

	blockmodel "quwoquan_service/services/user-service/internal/domain/block/model"
	blockrepo "quwoquan_service/services/user-service/internal/domain/block/repository"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
)

type BlockService struct {
	blocks blockrepo.BlockRepository
	bcache *cache.BlockCache
}

func NewBlockService(blocks blockrepo.BlockRepository, bcache *cache.BlockCache) *BlockService {
	return &BlockService{blocks: blocks, bcache: bcache}
}

func (s *BlockService) Block(ctx context.Context, blockerID, blockedID string) error {
	edge := &blockmodel.BlockEdge{
		ID:        uuid.New().String(),
		BlockerID: blockerID,
		BlockedID: blockedID,
	}
	created, err := s.blocks.Create(ctx, edge)
	if err != nil {
		return err
	}
	if created {
		_ = s.bcache.Add(ctx, blockerID, blockedID)
	}
	return nil
}

func (s *BlockService) Unblock(ctx context.Context, blockerID, blockedID string) error {
	deleted, err := s.blocks.Delete(ctx, blockerID, blockedID)
	if err != nil {
		return err
	}
	if deleted {
		_ = s.bcache.Remove(ctx, blockerID, blockedID)
	}
	return nil
}

func (s *BlockService) CheckBlocked(ctx context.Context, blockerID, blockedID string) (bool, error) {
	exists, err := s.bcache.Exists(ctx, blockerID)
	if err == nil && exists {
		return s.bcache.IsMember(ctx, blockerID, blockedID)
	}

	blocked, err := s.blocks.Exists(ctx, blockerID, blockedID)
	if err != nil {
		return false, err
	}

	go s.backfillBlockCache(blockerID) //nolint:errcheck
	return blocked, nil
}

func (s *BlockService) backfillBlockCache(blockerID string) {
	ctx := context.Background()
	edges, _, err := s.blocks.ListByBlocker(ctx, blockerID, "", 1000)
	if err != nil {
		return
	}
	ids := make([]string, len(edges))
	for i, e := range edges {
		ids[i] = e.BlockedID
	}
	_ = s.bcache.LoadFromDB(ctx, blockerID, ids)
}

func (s *BlockService) ListBlocked(ctx context.Context, blockerID, cursor string, limit int) ([]blockmodel.BlockEdge, string, error) {
	return s.blocks.ListByBlocker(ctx, blockerID, cursor, limit)
}
