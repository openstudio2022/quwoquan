package application

import (
	"context"
	"fmt"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	runtimesync "quwoquan_service/runtime/sync"
	event "quwoquan_service/services/user-service/internal/domain/user/event"
	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
)

type ProfileService struct {
	profiles userrepo.ProfileRepository
	personas userrepo.PersonaRepository
	settings userrepo.SettingRepository
	pcache   *cache.ProfileCache
	scache   *cache.SettingCache
	events   UserEventPublisher
	sync     UserSyncStream
}

func NewProfileService(
	profiles userrepo.ProfileRepository,
	personas userrepo.PersonaRepository,
	settings userrepo.SettingRepository,
	pcache *cache.ProfileCache,
	scache *cache.SettingCache,
	events UserEventPublisher,
	sync UserSyncStream,
) *ProfileService {
	if events == nil {
		events = NoopUserEventPublisher()
	}
	return &ProfileService{
		profiles: profiles,
		personas: personas,
		settings: settings,
		pcache:   pcache,
		scache:   scache,
		events:   events,
		sync:     sync,
	}
}

func (s *ProfileService) GetProfile(ctx context.Context, userID string) (snap *model.FullSnapshot, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.GetProfile",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	cached, cacheErr := s.pcache.Get(ctx, userID)
	if cacheErr == nil && cached != nil {
		return cached, nil
	}

	profile, err := s.profiles.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if profile == nil {
		return nil, nil
	}

	activePersona, _ := s.personas.FindActiveByUserID(ctx, userID)
	setting, _ := s.settings.FindByUserID(ctx, userID)

	snap = &model.FullSnapshot{
		Profile:       profile,
		ActivePersona: activePersona,
		Settings:      setting,
	}

	_ = s.pcache.Set(ctx, userID, snap)
	return snap, nil
}

func (s *ProfileService) UpdateProfile(ctx context.Context, userID string, data map[string]any) (_ *model.UserProfile, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.UpdateProfile",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	profile, err := s.profiles.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if profile == nil {
		return nil, fmt.Errorf("user not found: %s", userID)
	}

	if v, ok := data["nickname"].(string); ok && v != "" {
		existing, _ := s.profiles.FindByNickname(ctx, v)
		if existing != nil && existing.UserID != userID {
			return nil, fmt.Errorf("nickname_taken: %s", v)
		}
		profile.Nickname = v
	}
	oldAvatarURL := strings.TrimSpace(profile.AvatarURL)
	oldAvatarVersion := profile.AvatarVersion
	if v, ok := data["avatarUrl"].(string); ok {
		profile.AvatarURL = strings.TrimSpace(v)
		if strings.TrimSpace(profile.AvatarURL) != oldAvatarURL {
			profile.AvatarVersion++
			if profile.AvatarVersion <= 0 {
				profile.AvatarVersion = 1
			}
			profile.AvatarAssetID = fmt.Sprintf("ua_%s", userID)
		}
	}
	if v, ok := data["bio"].(string); ok {
		profile.Bio = v
	}
	if v, ok := data["gender"].(string); ok {
		profile.Gender = v
	}
	if v, ok := data["birthDate"].(string); ok {
		profile.BirthDate = &v
	}
	if v, ok := data["region"].(string); ok {
		profile.Region = v
	}

	if err := s.profiles.Update(ctx, profile); err != nil {
		return nil, err
	}

	_ = s.pcache.Del(ctx, userID)
	updatedAt := profile.UpdatedAt.UTC().Format("2006-01-02T15:04:05.999999999Z07:00")
	if err := s.events.PublishUserEvent(ctx, event.UserProfileUpdated, userID, userID, map[string]any{
		"userId":         profile.UserID,
		"nickname":       profile.Nickname,
		"bio":            profile.Bio,
		"avatarUrl":      profile.AvatarURL,
		"profileVersion": profile.ProfileVersion,
		"updatedAt":      updatedAt,
	}); err != nil {
		return nil, err
	}
	if profile.AvatarVersion != oldAvatarVersion {
		avatarPayload := map[string]any{
			"userId":         profile.UserID,
			"avatarAssetId":  profile.AvatarAssetID,
			"avatarVersion":  profile.AvatarVersion,
			"avatarUrl":      profile.AvatarURL,
			"profileVersion": profile.ProfileVersion,
			"updatedAt":      updatedAt,
		}
		if err := s.events.PublishUserEvent(ctx, event.UserAvatarUpdated, userID, userID, avatarPayload); err != nil {
			return nil, err
		}
		if s.sync != nil {
			if _, err := s.sync.AppendPatch(ctx, userID, "user.avatar.updated", avatarPayload); err != nil {
				return nil, err
			}
		}
	}
	return profile, nil
}

func (s *ProfileService) GetStats(ctx context.Context, userID string) (_ map[string]any, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.GetStats",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	profile, err := s.profiles.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if profile == nil {
		return nil, nil
	}
	return map[string]any{
		"followerCount":  profile.FollowerCount,
		"followingCount": profile.FollowingCount,
		"postCount":      profile.PostCount,
		"circleCount":    profile.CircleCount,
		"likeCount":      profile.LikeCount,
	}, nil
}

func (s *ProfileService) PullSync(
	ctx context.Context,
	userID string,
	afterSeq int64,
	limit int,
) (_ runtimesync.PullResponse, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.PullSync",
		attribute.String("user.id", userID),
		attribute.Int64("sync.after_seq", afterSeq))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.sync == nil {
		return runtimesync.PullResponse{
			Patches:        []runtimesync.Patch{},
			LatestSyncSeq:  0,
			HasMore:        false,
			RequiresResync: false,
		}, nil
	}
	return s.sync.Pull(ctx, userID, afterSeq, limit)
}
