package application

import (
	"context"
	"strings"

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
		st = &model.UserSetting{
			UserID:            userID,
			EnablePush:        true,
			AllowStrangerMsg:  true,
			ProfileVisibility: "public",
			AssistantEnabled:  true,
			BlockedKeywords:   []string{},
		}
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
	st, err := s.GetNotificationSettings(ctx, userID)
	if err != nil {
		return nil, err
	}
	if st != nil && st.BlockedKeywords == nil {
		st.BlockedKeywords = []string{}
	}
	return st, nil
}

func (s *SettingService) UpdatePrivacySettings(ctx context.Context, userID string, data map[string]any) error {
	st, err := s.settings.FindByUserID(ctx, userID)
	if err != nil {
		return err
	}
	if st == nil {
		st = &model.UserSetting{
			UserID:            userID,
			EnablePush:        true,
			AllowStrangerMsg:  true,
			ProfileVisibility: "public",
			AssistantEnabled:  true,
			BlockedKeywords:   []string{},
		}
	}
	if v, ok := data["allowStrangerMsg"].(bool); ok {
		st.AllowStrangerMsg = v
	}
	if v, ok := data["profileVisibility"].(string); ok {
		st.ProfileVisibility = v
	}
	if blockedKeywords, ok := normalizeBlockedKeywords(data["blockedKeywords"]); ok {
		st.BlockedKeywords = blockedKeywords
	}
	if err := s.settings.Upsert(ctx, st); err != nil {
		return err
	}
	_ = s.scache.Del(ctx, userID)
	return nil
}

func normalizeBlockedKeywords(raw any) ([]string, bool) {
	if raw == nil {
		return nil, false
	}
	var values []string
	switch typed := raw.(type) {
	case []string:
		values = append(values, typed...)
	case []any:
		for _, item := range typed {
			text, ok := item.(string)
			if !ok {
				continue
			}
			values = append(values, text)
		}
	default:
		return nil, false
	}
	seen := make(map[string]struct{}, len(values))
	normalized := make([]string, 0, len(values))
	for _, value := range values {
		keyword := strings.TrimSpace(value)
		if keyword == "" {
			continue
		}
		if _, exists := seen[keyword]; exists {
			continue
		}
		seen[keyword] = struct{}{}
		normalized = append(normalized, keyword)
	}
	return normalized, true
}
