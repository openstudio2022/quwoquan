package application

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
)

type SettingService struct {
	settings userrepo.SettingRepository
	scache   *cache.SettingCache
}

func NewSettingService(settings userrepo.SettingRepository, scache *cache.SettingCache) *SettingService {
	return &SettingService{settings: settings, scache: scache}
}

func (s *SettingService) GetNotificationSettings(ctx context.Context, userID string) (*model.UserSetting, error) {
	if cached, err := s.scache.Get(ctx, userID); err == nil && cached != nil {
		return cached, nil
	}
	st, err := s.settings.FindByUserID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if st != nil {
		_ = s.scache.Set(ctx, userID, st)
	}
	return st, nil
}

func (s *SettingService) UpdateNotificationSettings(ctx context.Context, userID string, data map[string]any) error {
	st, err := s.settings.FindByUserID(ctx, userID)
	if err != nil {
		return err
	}
	if st == nil {
		st = &model.UserSetting{UserID: userID, EnablePush: true, AllowStrangerMsg: true, ProfileVisibility: "public", AssistantEnabled: true}
	}
	if v, ok := data["enablePush"].(bool); ok {
		st.EnablePush = v
	}
	if v, ok := data["enableMarketing"].(bool); ok {
		st.EnableMarketing = v
	}
	if v, ok := data["assistantEnabled"].(bool); ok {
		st.AssistantEnabled = v
	}
	if err := s.settings.Upsert(ctx, st); err != nil {
		return err
	}
	_ = s.scache.Del(ctx, userID)
	return nil
}

func (s *SettingService) GetPrivacySettings(ctx context.Context, userID string) (*model.UserSetting, error) {
	return s.GetNotificationSettings(ctx, userID)
}

func (s *SettingService) UpdatePrivacySettings(ctx context.Context, userID string, data map[string]any) error {
	st, err := s.settings.FindByUserID(ctx, userID)
	if err != nil {
		return err
	}
	if st == nil {
		st = &model.UserSetting{UserID: userID, EnablePush: true, AllowStrangerMsg: true, ProfileVisibility: "public", AssistantEnabled: true}
	}
	if v, ok := data["allowStrangerMsg"].(bool); ok {
		st.AllowStrangerMsg = v
	}
	if v, ok := data["profileVisibility"].(string); ok {
		st.ProfileVisibility = v
	}
	if err := s.settings.Upsert(ctx, st); err != nil {
		return err
	}
	_ = s.scache.Del(ctx, userID)
	return nil
}
