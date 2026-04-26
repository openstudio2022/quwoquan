package application

import (
	"context"
	"reflect"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	runtimegovernance "quwoquan_service/runtime/governance"
	blockrepo "quwoquan_service/services/user-service/internal/domain/block/repository"
	userevent "quwoquan_service/services/user-service/internal/domain/follow/event"
	followmodel "quwoquan_service/services/user-service/internal/domain/follow/model"
	followrepo "quwoquan_service/services/user-service/internal/domain/follow/repository"
	followtelemetry "quwoquan_service/services/user-service/internal/domain/follow/telemetry"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
)

type FollowService struct {
	follows  followrepo.FollowRepository
	profiles userrepo.ProfileRepository
	personas userrepo.PersonaRepository
	blocks   blockrepo.BlockRepository
	pcache   *cache.ProfileCache
	events   UserEventPublisher
}

func NewFollowService(
	follows followrepo.FollowRepository,
	profiles userrepo.ProfileRepository,
	personas userrepo.PersonaRepository,
	pcache *cache.ProfileCache,
	blocks blockrepo.BlockRepository,
	events UserEventPublisher,
) *FollowService {
	if events == nil {
		events = NoopUserEventPublisher()
	}
	return &FollowService{
		follows:  follows,
		profiles: profiles,
		personas: personas,
		blocks:   blocks,
		pcache:   pcache,
		events:   events,
	}
}

func (s *FollowService) Follow(ctx context.Context, followerID, followeeID, source string) (bool, error) {
	startedAt := time.Now()
	defer func() {
		followtelemetry.Collector().RecordFollowCommandLatency(time.Since(startedAt))
	}()
	if !hasFollowRepository(s.follows) {
		return false, nil
	}
	if strings.TrimSpace(followerID) == "" || strings.TrimSpace(followeeID) == "" {
		return false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleUser, rterr.KindUser, "invalid_argument"),
			"关注主体不能为空",
			"followerId/followeeId required",
		)
	}
	if followerID == followeeID {
		return false, nil
	}
	blocked, err := s.hasBlockGate(ctx, followerID, followeeID)
	if err != nil {
		return false, err
	}
	if blocked {
		followtelemetry.Collector().RecordBlockRejection()
		return false, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleUser, rterr.KindUser, "forbidden"),
			"当前关系不可关注",
			"follow blocked by block edge",
		)
	}
	edge := &followmodel.FollowEdge{
		FollowerID: followerID,
		FolloweeID: followeeID,
		Source:     defaultFollowSource(source),
	}
	created, err := s.follows.Create(ctx, edge)
	if err != nil {
		return false, err
	}
	if !created {
		followtelemetry.Collector().RecordDuplicateFollow()
		return false, nil
	}

	s.incrementCounters(ctx, followeeID, followerID, 1)
	_ = s.pcache.Del(ctx, followeeID)
	_ = s.pcache.Del(ctx, followerID)
	_ = s.events.PublishUserEvent(
		ctx,
		userevent.UserFollowed,
		followeeID,
		followerID,
		map[string]any{
			"followerId": followerID,
			"followeeId": followeeID,
			"source":     edge.Source,
		},
	)
	return true, nil
}

func (s *FollowService) Unfollow(ctx context.Context, followerID, followeeID string) (bool, error) {
	startedAt := time.Now()
	defer func() {
		followtelemetry.Collector().RecordFollowCommandLatency(time.Since(startedAt))
	}()
	if !hasFollowRepository(s.follows) {
		return false, nil
	}
	deleted, err := s.follows.Delete(ctx, followerID, followeeID)
	if err != nil {
		return false, err
	}
	if !deleted {
		return false, nil
	}

	s.incrementCounters(ctx, followeeID, followerID, -1)
	_ = s.pcache.Del(ctx, followeeID)
	_ = s.pcache.Del(ctx, followerID)
	_ = s.events.PublishUserEvent(
		ctx,
		userevent.UserUnfollowed,
		followeeID,
		followerID,
		map[string]any{
			"followerId": followerID,
			"followeeId": followeeID,
		},
	)
	return true, nil
}

func (s *FollowService) ListFollowing(ctx context.Context, userID, cursor string, limit int) ([]followmodel.FollowEdge, string, error) {
	if !hasFollowRepository(s.follows) {
		return []followmodel.FollowEdge{}, "", nil
	}
	return s.follows.ListByFollower(ctx, userID, cursor, limit)
}

func (s *FollowService) ListFollowers(ctx context.Context, userID, cursor string, limit int) ([]followmodel.FollowEdge, string, error) {
	if !hasFollowRepository(s.follows) {
		return []followmodel.FollowEdge{}, "", nil
	}
	return s.follows.ListByFollowee(ctx, userID, cursor, limit)
}

func (s *FollowService) GetRelationship(ctx context.Context, userID, targetID string) (*followrepo.Relationship, error) {
	if !hasFollowRepository(s.follows) {
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

func (s *FollowService) hasBlockGate(ctx context.Context, followerID, followeeID string) (bool, error) {
	if s.blocks == nil {
		return false, nil
	}
	blocked, err := s.blocks.Exists(ctx, followerID, followeeID)
	if err != nil {
		return false, err
	}
	if blocked {
		return true, nil
	}
	return s.blocks.Exists(ctx, followeeID, followerID)
}

func (s *FollowService) incrementCounters(ctx context.Context, followeeID, followerID string, delta int64) {
	if s.profiles == nil {
		return
	}
	followeeOwnerID := s.counterOwnerID(ctx, followeeID)
	followerOwnerID := s.counterOwnerID(ctx, followerID)
	if err := s.profiles.IncrementCounter(ctx, followeeOwnerID, "follower_count", delta); err != nil {
		followtelemetry.Collector().RecordCounterMismatch()
	}
	if err := s.profiles.IncrementCounter(ctx, followerOwnerID, "following_count", delta); err != nil {
		followtelemetry.Collector().RecordCounterMismatch()
	}
	s.reconcileCounter(ctx, followeeOwnerID, "follower_count")
	s.reconcileCounter(ctx, followerOwnerID, "following_count")
}

func (s *FollowService) counterOwnerID(ctx context.Context, subjectID string) string {
	subjectID = strings.TrimSpace(subjectID)
	if subjectID == "" || s.personas == nil {
		return subjectID
	}
	if !runtimegovernance.PersonaGraphEnabled() {
		return subjectID
	}
	persona, err := s.personas.FindBySubAccountID(ctx, subjectID)
	if err != nil || persona == nil {
		return subjectID
	}
	return persona.UserID
}

func (s *FollowService) reconcileCounter(ctx context.Context, ownerID, field string) {
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" || !hasFollowRepository(s.follows) || s.profiles == nil {
		return
	}
	profile, err := s.profiles.FindByID(ctx, ownerID)
	if err != nil || profile == nil {
		return
	}
	expected, err := s.expectedCounterValue(ctx, ownerID, field)
	if err != nil {
		return
	}
	var current int64
	switch field {
	case "follower_count":
		current = profile.FollowerCount
	case "following_count":
		current = profile.FollowingCount
	default:
		return
	}
	if current == expected {
		return
	}
	followtelemetry.Collector().RecordCounterMismatch()
	if err := s.profiles.IncrementCounter(ctx, ownerID, field, expected-current); err != nil {
		followtelemetry.Collector().RecordCounterMismatch()
	}
}

func (s *FollowService) expectedCounterValue(ctx context.Context, ownerID, field string) (int64, error) {
	subjectIDs := []string{ownerID}
	if runtimegovernance.PersonaGraphEnabled() && s.personas != nil {
		personas, err := s.personas.FindByUserID(ctx, ownerID)
		if err != nil {
			return 0, err
		}
		subjectIDs = make([]string, 0, len(personas))
		for i := range personas {
			subjectID := strings.TrimSpace(personas[i].SubAccountID)
			if subjectID == "" || strings.EqualFold(strings.TrimSpace(personas[i].Status), "retired") {
				continue
			}
			subjectIDs = append(subjectIDs, subjectID)
		}
		if len(subjectIDs) == 0 {
			subjectIDs = []string{ownerID}
		}
	}
	var total int64
	for _, subjectID := range subjectIDs {
		var count int64
		var err error
		switch field {
		case "follower_count":
			count, err = s.follows.CountByFollowee(ctx, subjectID)
		case "following_count":
			count, err = s.follows.CountByFollower(ctx, subjectID)
		default:
			return 0, nil
		}
		if err != nil {
			return 0, err
		}
		total += count
	}
	return total, nil
}

func defaultFollowSource(source string) string {
	source = strings.TrimSpace(source)
	if source == "" {
		return "profile"
	}
	return source
}

func hasFollowRepository(repo followrepo.FollowRepository) bool {
	if repo == nil {
		return false
	}
	value := reflect.ValueOf(repo)
	switch value.Kind() {
	case reflect.Ptr, reflect.Map, reflect.Slice, reflect.Interface, reflect.Func:
		return !value.IsNil()
	default:
		return true
	}
}
