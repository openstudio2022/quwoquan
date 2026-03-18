package application

import (
	"context"

	followmodel "quwoquan_service/services/user-service/internal/domain/follow/model"
	followrepo "quwoquan_service/services/user-service/internal/domain/follow/repository"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
)

type FollowService struct {
	follows  followrepo.FollowRepository
	profiles userrepo.ProfileRepository
	pcache   *cache.ProfileCache
}

func NewFollowService(
	follows followrepo.FollowRepository,
	profiles userrepo.ProfileRepository,
	pcache *cache.ProfileCache,
) *FollowService {
	return &FollowService{follows: follows, profiles: profiles, pcache: pcache}
}

func (s *FollowService) Follow(ctx context.Context, followerID, followeeID string) error {
	if s.follows == nil {
		return nil
	}
	edge := &followmodel.FollowEdge{
		FollowerID: followerID,
		FolloweeID: followeeID,
		Source:     "profile",
	}
	created, err := s.follows.Create(ctx, edge)
	if err != nil {
		return err
	}
	if !created {
		return nil
	}

	_ = s.profiles.IncrementCounter(ctx, followeeID, "follower_count", 1)
	_ = s.profiles.IncrementCounter(ctx, followerID, "following_count", 1)
	_ = s.pcache.Del(ctx, followeeID)
	_ = s.pcache.Del(ctx, followerID)
	return nil
}

func (s *FollowService) Unfollow(ctx context.Context, followerID, followeeID string) error {
	if s.follows == nil {
		return nil
	}
	deleted, err := s.follows.Delete(ctx, followerID, followeeID)
	if err != nil {
		return err
	}
	if !deleted {
		return nil
	}

	_ = s.profiles.IncrementCounter(ctx, followeeID, "follower_count", -1)
	_ = s.profiles.IncrementCounter(ctx, followerID, "following_count", -1)
	_ = s.pcache.Del(ctx, followeeID)
	_ = s.pcache.Del(ctx, followerID)
	return nil
}

func (s *FollowService) ListFollowing(ctx context.Context, userID, cursor string, limit int) ([]followmodel.FollowEdge, string, error) {
	if s.follows == nil {
		return []followmodel.FollowEdge{}, "", nil
	}
	return s.follows.ListByFollower(ctx, userID, cursor, limit)
}

func (s *FollowService) ListFollowers(ctx context.Context, userID, cursor string, limit int) ([]followmodel.FollowEdge, string, error) {
	if s.follows == nil {
		return []followmodel.FollowEdge{}, "", nil
	}
	return s.follows.ListByFollowee(ctx, userID, cursor, limit)
}

func (s *FollowService) GetRelationship(ctx context.Context, userID, targetID string) (*followrepo.Relationship, error) {
	if s.follows == nil {
		return &followrepo.Relationship{}, nil
	}
	isFollowing, err := s.follows.Exists(ctx, userID, targetID)
	if err != nil {
		return nil, err
	}
	isFollowedBy, err := s.follows.Exists(ctx, targetID, userID)
	if err != nil {
		return nil, err
	}
	return &followrepo.Relationship{
		IsFollowing:  isFollowing,
		IsFollowedBy: isFollowedBy,
		IsMutual:     isFollowing && isFollowedBy,
	}, nil
}
