package persistence

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

// PgSettingStore extends pgSettingStoreBase with domain-specific methods.
type PgSettingStore struct{ pgSettingStoreBase }

var _ repository.SettingRepository = (*PgSettingStore)(nil)

func NewPgSettingStore(pool *pgxpool.Pool) *PgSettingStore {
	return &PgSettingStore{pgSettingStoreBase{pool: pool}}
}

// FindByUserID retrieves settings by user ID (PK = user_id).
func (s *PgSettingStore) FindByUserID(ctx context.Context, userID string) (*model.UserSetting, error) {
	row := s.pool.QueryRow(ctx, `
		SELECT user_id, enable_push, enable_marketing, quiet_hours_start, quiet_hours_end,
		    COALESCE(default_incoming_call_ringtone_id, ''), allow_caller_ringtone_override,
		    enable_call_vibration, enable_group_call_ring, allow_stranger_msg,
		    profile_visibility, content_language, feed_preference, assistant_enabled,
		    default_theme_mode, default_font_size_preset, appearance_version,
		    appearance_updated_at, COALESCE(blocked_keywords, '{}'::TEXT[]), updated_at
		FROM user_settings
		WHERE user_id = $1`,
		userID,
	)
	return scanUserSetting(row)
}

// Upsert inserts or updates user settings atomically.
func (s *PgSettingStore) Upsert(ctx context.Context, st *model.UserSetting) error {
	st.UpdatedAt = time.Now().UTC()
	if st.BlockedKeywords == nil {
		st.BlockedKeywords = []string{}
	}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO user_settings (user_id, enable_push, enable_marketing, quiet_hours_start,
		    quiet_hours_end, allow_stranger_msg, profile_visibility, content_language,
		    feed_preference, assistant_enabled, blocked_keywords, updated_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
		ON CONFLICT (user_id) DO UPDATE SET
		    enable_push=$2, enable_marketing=$3, quiet_hours_start=$4, quiet_hours_end=$5,
		    allow_stranger_msg=$6, profile_visibility=$7, content_language=$8,
		    feed_preference=$9, assistant_enabled=$10, blocked_keywords=$11, updated_at=$12`,
		st.UserID, st.EnablePush, st.EnableMarketing, st.QuietHoursStart,
		st.QuietHoursEnd, st.AllowStrangerMsg, st.ProfileVisibility, st.ContentLanguage,
		st.FeedPreference, st.AssistantEnabled, st.BlockedKeywords, st.UpdatedAt)
	return err
}
