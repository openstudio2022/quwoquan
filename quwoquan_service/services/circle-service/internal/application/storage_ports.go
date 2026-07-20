package application

import (
	"context"
	"errors"
	"time"

	circlemodel "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

var ErrInvalidCircleFeedCursor = errors.New("invalid circle feed cursor")

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

// CircleRecordStore 是 Circle 聚合的具名读端口；写路径唯一入口是
// domain/circle/ports.AggregateStore（state/receipt/outbox 同事务）。
type CircleRecordStore interface {
	CircleReader
	CircleLister
}

type ListCirclePostsQuery struct {
	Identity string
	Type     string
	Sort     string
	Cursor   string
	Limit    int
}

type CircleFeedIntersectionReason struct {
	Kind          string  `json:"kind"`
	PrimaryText   string  `json:"primaryText"`
	SecondaryText string  `json:"secondaryText,omitempty"`
	Strength      float64 `json:"strength"`
}

// CircleFeedPost 是 circle 对 content Post 公开读投影的强类型防腐模型。
// Circle 不拥有 Post；该类型仅描述本地异步投影允许对 App 暴露的字段。
type CircleFeedPost struct {
	CircleID            string                         `json:"circleId"`
	PlacementID         string                         `json:"placementId"`
	PostID              string                         `json:"postId"`
	ContentType         string                         `json:"contentType"`
	ContentIdentity     string                         `json:"contentIdentity,omitempty"`
	AssistantUsePolicy  string                         `json:"assistantUsePolicy,omitempty"`
	AuthorID            string                         `json:"authorId,omitempty"`
	AuthorDisplayName   string                         `json:"authorDisplayName,omitempty"`
	AuthorAvatarURL     string                         `json:"authorAvatarUrl,omitempty"`
	AuthorBackgroundURL string                         `json:"authorBackgroundUrl,omitempty"`
	AuthorRoleLabel     string                         `json:"authorRoleLabel,omitempty"`
	AuthorIdentityTags  []string                       `json:"authorIdentityTags,omitempty"`
	AuthorVerified      bool                           `json:"authorVerified"`
	Title               string                         `json:"title,omitempty"`
	Body                string                         `json:"body,omitempty"`
	Summary             string                         `json:"summary,omitempty"`
	CoverURL            string                         `json:"coverUrl,omitempty"`
	ImageURLs           []string                       `json:"imageUrls,omitempty"`
	VideoURL            string                         `json:"videoUrl,omitempty"`
	ThumbnailURL        string                         `json:"thumbnailUrl,omitempty"`
	Width               int64                          `json:"width,omitempty"`
	Height              int64                          `json:"height,omitempty"`
	DurationMs          int64                          `json:"durationMs,omitempty"`
	LikeCount           int64                          `json:"likeCount"`
	CommentCount        int64                          `json:"commentCount"`
	ShareCount          int64                          `json:"shareCount"`
	CreatedAt           *time.Time                     `json:"createdAt,omitempty"`
	UpdatedAt           *time.Time                     `json:"updatedAt,omitempty"`
	PublishedAt         *time.Time                     `json:"publishedAt,omitempty"`
	ContentVertical     string                         `json:"contentVertical,omitempty"`
	RecallPath          string                         `json:"recallPath,omitempty"`
	SupplySource        string                         `json:"supplySource,omitempty"`
	IntersectionReasons []CircleFeedIntersectionReason `json:"intersectionReasons,omitempty"`
	Pinned              bool                           `json:"pinned"`
	Featured            bool                           `json:"featured"`
	PinnedAt            *time.Time                     `json:"pinnedAt,omitempty"`
	FeaturedAt          *time.Time                     `json:"featuredAt,omitempty"`
}

type CircleDiscoveryFeedScope string

const (
	CircleDiscoveryFeedScopeRecommended CircleDiscoveryFeedScope = "recommended"
	CircleDiscoveryFeedScopeMine        CircleDiscoveryFeedScope = "mine"
)

type CircleDiscoveryFeedQuery struct {
	Category    string
	SubCategory string
	Scope       CircleDiscoveryFeedScope
	PersonaID   string
	Sort        string
	Cursor      string
	Limit       int
}

type CircleDiscoveryFeedSlice struct {
	Circles []circlemodel.Circle `json:"circles"`
	Items   []CircleFeedPost     `json:"items"`
	Cursor  string               `json:"cursor,omitempty"`
}

type CircleFeedSlice struct {
	Items  []CircleFeedPost `json:"items"`
	Cursor string           `json:"cursor,omitempty"`
}

// CircleFeedStore 是 content Post 本地投影与 CirclePostPlacement 聚合读模型
// 联合形成的圈子动态流读端口。展示位事实始终从 placement 集合读取，
// 禁止回写到跨圈共享的 Post 文档。
type CircleFeedStore interface {
	ListCirclePosts(ctx context.Context, circleID string, query ListCirclePostsQuery) ([]CircleFeedPost, string, error)
}

// CircleDiscoveryFeedReader 在服务端聚合 Circle、Membership 与已发布 Post 投影，
// 消除 App 端 listCircles → 逐圈 getCircleFeed 的 N+1。
type CircleDiscoveryFeedReader interface {
	ListCircleDiscoveryFeed(ctx context.Context, query CircleDiscoveryFeedQuery) (CircleDiscoveryFeedSlice, error)
}

// CircleStoragePorts 聚合细粒度端口，不提供通用仓储转发方法。
type CircleStoragePorts struct {
	Records CircleRecordStore
}
