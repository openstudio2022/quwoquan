package application

import (
	"context"

	circlemodel "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

type ListCirclesQuery struct {
	Category     string
	DomainID     string
	RecommendFor string
	Sort         string
	Cursor       string
	Limit        int
}

type CircleReader interface {
	FindByID(ctx context.Context, id string) (*circlemodel.Circle, bool)
}

type CircleLister interface {
	List(ctx context.Context, query ListCirclesQuery) ([]circlemodel.Circle, string)
}

// CircleRecordStore 负责圈子主记录的读写，不包含派生计数。
type CircleRecordStore interface {
	CircleReader
	CircleLister
	Create(ctx context.Context, circle *circlemodel.Circle) error
	Update(ctx context.Context, id string, circle *circlemodel.Circle) bool
	Archive(ctx context.Context, id string) bool
}

// CircleMetricsStore 负责圈子派生计数与容量统计。
type CircleMetricsStore interface {
	UpdateStorageUsed(ctx context.Context, id string, deltaBytes int64) error
}

type CircleSectionStore interface {
	UpdateSections(ctx context.Context, id string, sections []circlemodel.CircleSectionConfig) error
}

type ListCirclePostsQuery struct {
	Sort   string
	Cursor string
	Limit  int
}

type CircleFeedStore interface {
	ListCirclePosts(ctx context.Context, circleID string, query ListCirclePostsQuery) ([]map[string]any, string)
	UpdateCirclePostPinned(ctx context.Context, circleID, postID string, pinned bool) (bool, error)
	UpdateCirclePostFeatured(ctx context.Context, circleID, postID string, featured bool) (bool, error)
}

type EntityIDGenerator interface {
	NewID() string
}

// CircleStoragePorts 聚合细粒度端口，不提供通用仓储转发方法。
type CircleStoragePorts struct {
	Records  CircleRecordStore
	Metrics  CircleMetricsStore
	Sections CircleSectionStore
	IDs      EntityIDGenerator
}
