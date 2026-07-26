// Package persistence 实现 UserSettings 对象专属 PostgreSQL Store/Reader。
package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	settingsmodel "quwoquan_service/services/user-service/internal/account/user_settings/domain/model"
	settingsports "quwoquan_service/services/user-service/internal/account/user_settings/domain/ports"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("UserSettings PostgreSQL pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

var (
	_ settingsports.AggregateStore = (*PostgresStore)(nil)
	_ settingsports.SnapshotReader = (*PostgresStore)(nil)
)

func (store *PostgresStore) Load(
	ctx context.Context,
	userID string,
) (settingsmodel.UserSettings, bool, error) {
	return store.read(ctx, userID)
}

func (store *PostgresStore) ReadUserSettingsSnapshot(
	ctx context.Context,
	userID string,
) (settingsmodel.Snapshot, bool, error) {
	settings, found, err := store.read(ctx, userID)
	if err != nil || !found {
		return settingsmodel.Snapshot{}, found, err
	}
	return settings.Snapshot(), true, nil
}

// Commit 以 expectedVersion 做内部 CAS，并将 state 与 UserSettingsChanged
// outbox 事实放在同一个 PostgreSQL 事务中提交。
func (store *PostgresStore) Commit(
	ctx context.Context,
	expectedVersion int64,
	change settingsmodel.ChangeSet,
) error {
	event, err := validateChange(expectedVersion, change)
	if err != nil {
		return err
	}

	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var tag pgconn.CommandTag
	if expectedVersion == 0 {
		tag, err = insertSettings(ctx, tx, change.Aggregate)
	} else {
		tag, err = updateSettings(
			ctx,
			tx,
			expectedVersion,
			change.Aggregate,
		)
	}
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return settingsmodel.ErrVersionConflict
	}

	payload, err := json.Marshal(struct {
		UserID string `json:"userId"`
	}{UserID: change.Aggregate.UserID})
	if err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO user_settings_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,$4,$5,$6)`,
		event.ID,
		event.AggregateID,
		event.AggregateVersion,
		event.Type,
		payload,
		event.OccurredAt,
	); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (store *PostgresStore) read(
	ctx context.Context,
	userID string,
) (settingsmodel.UserSettings, bool, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return settingsmodel.UserSettings{}, false, fmt.Errorf(
			"%w: userId is required",
			settingsmodel.ErrInvalidArgument,
		)
	}
	return scanUserSettings(store.pool.QueryRow(ctx, `
SELECT
  user_id, enable_push, enable_marketing, quiet_hours_start, quiet_hours_end,
  default_incoming_call_ringtone_id, allow_caller_ringtone_override,
  enable_call_vibration, enable_group_call_ring, allow_stranger_msg,
  profile_visibility, content_language, feed_preference, assistant_enabled,
  default_theme_mode, default_font_size_preset, appearance_version,
  appearance_updated_at, blocked_keywords, version, updated_at
FROM user_settings
WHERE user_id=$1`, userID))
}

func validateChange(
	expectedVersion int64,
	change settingsmodel.ChangeSet,
) (settingsmodel.Event, error) {
	if expectedVersion < 0 ||
		!change.Changed ||
		change.Aggregate.Version != expectedVersion+1 {
		return settingsmodel.Event{}, settingsmodel.ErrVersionConflict
	}
	if err := change.Aggregate.Validate(); err != nil {
		return settingsmodel.Event{}, err
	}
	if len(change.Events) != 1 {
		return settingsmodel.Event{}, fmt.Errorf(
			"%w: commit requires exactly one UserSettingsChanged event",
			settingsmodel.ErrInvalidArgument,
		)
	}
	event := change.Events[0]
	if event.ID == "" ||
		len(event.ID) > 64 ||
		event.Type != settingsmodel.UserSettingsChangedEvent ||
		event.AggregateID != change.Aggregate.UserID ||
		event.AggregateVersion != change.Aggregate.Version ||
		event.OccurredAt.IsZero() {
		return settingsmodel.Event{}, fmt.Errorf(
			"%w: outbox event is not aligned with aggregate state",
			settingsmodel.ErrInvalidArgument,
		)
	}
	return event, nil
}

func insertSettings(
	ctx context.Context,
	tx pgx.Tx,
	settings settingsmodel.UserSettings,
) (pgconn.CommandTag, error) {
	return tx.Exec(ctx, `
INSERT INTO user_settings(
  user_id, enable_push, enable_marketing, quiet_hours_start, quiet_hours_end,
  default_incoming_call_ringtone_id, allow_caller_ringtone_override,
  enable_call_vibration, enable_group_call_ring, allow_stranger_msg,
  profile_visibility, content_language, feed_preference, assistant_enabled,
  default_theme_mode, default_font_size_preset, appearance_version,
  appearance_updated_at, blocked_keywords, version, updated_at
) VALUES (
  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21
) ON CONFLICT (user_id) DO NOTHING`,
		settings.UserID,
		settings.Notification.EnablePush,
		settings.Notification.EnableMarketing,
		nullableTimeOfDay(settings.Notification.QuietHoursStart),
		nullableTimeOfDay(settings.Notification.QuietHoursEnd),
		nullableRingtoneID(settings.Call.DefaultIncomingCallRingtoneID),
		settings.Call.AllowCallerRingtoneOverride,
		settings.Call.EnableCallVibration,
		settings.Call.EnableGroupCallRing,
		settings.Privacy.AllowStrangerMsg,
		settings.Privacy.ProfileVisibility,
		settings.Privacy.ContentLanguage,
		nullableFeedPreference(settings.Privacy.FeedPreference),
		settings.Privacy.AssistantEnabled,
		settings.Appearance.DefaultThemeMode,
		settings.Appearance.DefaultFontSizePreset,
		settings.Appearance.Version,
		settings.Appearance.UpdatedAt,
		nonNilStrings(settings.Privacy.BlockedKeywords),
		settings.Version,
		settings.UpdatedAt,
	)
}

func updateSettings(
	ctx context.Context,
	tx pgx.Tx,
	expectedVersion int64,
	settings settingsmodel.UserSettings,
) (pgconn.CommandTag, error) {
	return tx.Exec(ctx, `
UPDATE user_settings SET
  enable_push=$2, enable_marketing=$3, quiet_hours_start=$4, quiet_hours_end=$5,
  default_incoming_call_ringtone_id=$6, allow_caller_ringtone_override=$7,
  enable_call_vibration=$8, enable_group_call_ring=$9, allow_stranger_msg=$10,
  profile_visibility=$11, content_language=$12, feed_preference=$13,
  assistant_enabled=$14, default_theme_mode=$15, default_font_size_preset=$16,
  appearance_version=$17, appearance_updated_at=$18, blocked_keywords=$19,
  version=$20, updated_at=$21
WHERE user_id=$1 AND version=$22`,
		settings.UserID,
		settings.Notification.EnablePush,
		settings.Notification.EnableMarketing,
		nullableTimeOfDay(settings.Notification.QuietHoursStart),
		nullableTimeOfDay(settings.Notification.QuietHoursEnd),
		nullableRingtoneID(settings.Call.DefaultIncomingCallRingtoneID),
		settings.Call.AllowCallerRingtoneOverride,
		settings.Call.EnableCallVibration,
		settings.Call.EnableGroupCallRing,
		settings.Privacy.AllowStrangerMsg,
		settings.Privacy.ProfileVisibility,
		settings.Privacy.ContentLanguage,
		nullableFeedPreference(settings.Privacy.FeedPreference),
		settings.Privacy.AssistantEnabled,
		settings.Appearance.DefaultThemeMode,
		settings.Appearance.DefaultFontSizePreset,
		settings.Appearance.Version,
		settings.Appearance.UpdatedAt,
		nonNilStrings(settings.Privacy.BlockedKeywords),
		settings.Version,
		settings.UpdatedAt,
		expectedVersion,
	)
}
