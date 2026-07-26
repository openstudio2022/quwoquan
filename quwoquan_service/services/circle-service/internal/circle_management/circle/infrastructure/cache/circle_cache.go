package cache

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	rtredis "quwoquan_service/runtime/redis"

	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
)

const (
	circleCacheKeyPrefix = "cache:circle:"
	circleCacheTTL       = 600 * time.Second
)

// CachedCircleStore wraps the circle read ports with a Redis caching layer.
// 写路径经 AggregateStore 提交后由 CircleCommandFacade 调用 InvalidateCircle
// 失效缓存（storage.yaml invalidation rules）。
type CachedCircleStore struct {
	records application.CircleRecordStore
	rdb     rtredis.Client
	logger  *slog.Logger
}

var (
	_ application.CircleRecordStore = (*CachedCircleStore)(nil)
	_ circleports.CacheInvalidator  = (*CachedCircleStore)(nil)
)

func NewCachedCircleStore(
	records application.CircleRecordStore,
	rdb rtredis.Client,
) *CachedCircleStore {
	return &CachedCircleStore{records: records, rdb: rdb, logger: slog.Default()}
}

func (s *CachedCircleStore) cacheKey(id string) string {
	return fmt.Sprintf("%s%s", circleCacheKeyPrefix, id)
}

// InvalidateCircle 删除详情缓存；失败结构化告警（脏缓存最长存活一个 TTL）。
func (s *CachedCircleStore) InvalidateCircle(ctx context.Context, id string) error {
	if err := s.rdb.Del(ctx, s.cacheKey(id)); err != nil {
		s.logger.Warn("circle cache delete failed", "circleId", id, "error", err)
		return err
	}
	if err := InvalidateCircleDiscoveryFeed(ctx, s.rdb); err != nil {
		s.logger.Warn(
			"circle discovery cache invalidation failed",
			"circleId",
			id,
			"error",
			err,
		)
		return err
	}
	return nil
}

func (s *CachedCircleStore) FindByID(ctx context.Context, id string) (*model.Circle, bool) {
	key := s.cacheKey(id)
	data, err := s.rdb.GetBytes(ctx, key)
	if err == nil {
		var c model.Circle
		if json.Unmarshal(data, &c) == nil {
			return &c, true
		}
	}

	c, ok := s.records.FindByID(ctx, id)
	if !ok {
		return nil, false
	}

	if encoded, err := json.Marshal(c); err == nil {
		if setErr := s.rdb.SetBytes(ctx, key, encoded, circleCacheTTL); setErr != nil {
			s.logger.Warn("circle cache set failed", "circleId", id, "error", setErr)
		}
	}
	return c, true
}

func (s *CachedCircleStore) List(ctx context.Context, query application.ListCirclesQuery) ([]model.Circle, string) {
	return s.records.List(ctx, query)
}
