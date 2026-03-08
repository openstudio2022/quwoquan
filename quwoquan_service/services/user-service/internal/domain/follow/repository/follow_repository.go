package repository

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/follow/model"
)

type Relationship struct {
	IsFollowing  bool `json:"isFollowing"`
	IsFollowedBy bool `json:"isFollowedBy"`
	IsMutual     bool `json:"isMutual"`
}

type FollowRepository interface {
	Create(ctx context.Context, edge *model.FollowEdge) (created bool, err error)
	Delete(ctx context.Context, followerID, followeeID string) (deleted bool, err error)
	Exists(ctx context.Context, followerID, followeeID string) (bool, error)
	ListByFollower(ctx context.Context, followerID string, cursor string, limit int) ([]model.FollowEdge, string, error)
	ListByFollowee(ctx context.Context, followeeID string, cursor string, limit int) ([]model.FollowEdge, string, error)
	CountByFollower(ctx context.Context, followerID string) (int64, error)
	CountByFollowee(ctx context.Context, followeeID string) (int64, error)
}
