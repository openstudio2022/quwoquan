package persistence

import (
	"context"

	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

// CircleStore defines storage operations used by the application layer.
// Both in-memory and MongoDB implementations satisfy this interface.
type CircleStore interface {
	Create(ctx context.Context, circle *model.Circle) error
	Update(ctx context.Context, id string, circle *model.Circle) bool
	FindByID(ctx context.Context, id string) (*model.Circle, bool)
	List(ctx context.Context, opts ListCirclesOpts) ([]model.Circle, string)
	Archive(ctx context.Context, id string) bool
	IncrementMemberCount(ctx context.Context, id string, delta int64) error
	UpdateStorageUsed(ctx context.Context, id string, deltaBytes int64) error
	UpdateSections(ctx context.Context, id string, sections []model.CircleSectionConfig) error
}

// ListCirclesOpts controls circle listing queries.
type ListCirclesOpts struct {
	Category     string
	DomainID     string
	RecommendFor string
	Sort         string
	Cursor       string
	Limit        int
}

// MemberStore defines storage operations for circle members.
type MemberStore interface {
	Create(ctx context.Context, member *model.CircleMember) error
	FindByCircleAndUser(ctx context.Context, circleID, userID string) (*model.CircleMember, bool)
	Delete(ctx context.Context, circleID, userID string) bool
	UpdateRole(ctx context.Context, circleID, userID string, role model.CircleMemberRole) bool
	ListByCircle(ctx context.Context, circleID string, limit int, cursor string) ([]model.CircleMember, string)
	ListByUser(ctx context.Context, userID string, limit int, cursor string) ([]model.CircleMember, string)
}

// FileStore defines storage operations for circle files.
type FileStore interface {
	Create(ctx context.Context, file *model.CircleFile) error
	FindByID(ctx context.Context, circleID, fileID string) (*model.CircleFile, bool)
	Update(ctx context.Context, circleID, fileID string, file *model.CircleFile) bool
	Delete(ctx context.Context, circleID, fileID string) bool
	ListByCircle(ctx context.Context, circleID string, opts ListFilesOpts) ([]model.CircleFile, string)
}

// ListFilesOpts controls file listing queries.
type ListFilesOpts struct {
	ParentID string
	Sort     string
	Cursor   string
	Limit    int
}

// FeedStore defines read-only access to posts associated with circles.
type FeedStore interface {
	ListCirclePosts(ctx context.Context, circleID string, opts ListCirclePostsOpts) ([]map[string]any, string)
}

// ListCirclePostsOpts controls circle feed queries.
type ListCirclePostsOpts struct {
	Sort   string // latest, hot, featured
	Cursor string
	Limit  int
}
