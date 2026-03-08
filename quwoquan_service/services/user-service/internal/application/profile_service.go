package application

import (
	"context"
	"fmt"

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
}

func NewProfileService(
	profiles userrepo.ProfileRepository,
	personas userrepo.PersonaRepository,
	settings userrepo.SettingRepository,
	pcache *cache.ProfileCache,
	scache *cache.SettingCache,
) *ProfileService {
	return &ProfileService{
		profiles: profiles,
		personas: personas,
		settings: settings,
		pcache:   pcache,
		scache:   scache,
	}
}

func (s *ProfileService) GetProfile(ctx context.Context, userID string) (*model.FullSnapshot, error) {
	if cached, err := s.pcache.Get(ctx, userID); err == nil && cached != nil {
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

	snap := &model.FullSnapshot{
		Profile:       profile,
		ActivePersona: activePersona,
		Settings:      setting,
	}

	_ = s.pcache.Set(ctx, userID, snap)
	return snap, nil
}

func (s *ProfileService) UpdateProfile(ctx context.Context, userID string, data map[string]any) (*model.UserProfile, error) {
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
	if v, ok := data["avatarUrl"].(string); ok {
		profile.AvatarURL = v
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
	return profile, nil
}

func (s *ProfileService) GetStats(ctx context.Context, userID string) (map[string]any, error) {
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
