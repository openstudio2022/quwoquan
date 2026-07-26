package persistence

import (
	"errors"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"

	settingsmodel "quwoquan_service/services/user-service/internal/account/user_settings/domain/model"
)

type rowScanner interface {
	Scan(...any) error
}

func scanUserSettings(
	row rowScanner,
) (settingsmodel.UserSettings, bool, error) {
	var (
		userID                        string
		enablePush                    bool
		enableMarketing               bool
		quietHoursStart               *string
		quietHoursEnd                 *string
		defaultIncomingCallRingtoneID *string
		allowCallerRingtoneOverride   bool
		enableCallVibration           bool
		enableGroupCallRing           bool
		allowStrangerMsg              bool
		profileVisibility             string
		contentLanguage               *string
		feedPreference                *string
		assistantEnabled              bool
		defaultThemeMode              string
		defaultFontSizePreset         string
		appearanceVersion             int64
		appearanceUpdatedAt           time.Time
		blockedKeywords               []string
		version                       int64
		updatedAt                     time.Time
	)
	err := row.Scan(
		&userID,
		&enablePush,
		&enableMarketing,
		&quietHoursStart,
		&quietHoursEnd,
		&defaultIncomingCallRingtoneID,
		&allowCallerRingtoneOverride,
		&enableCallVibration,
		&enableGroupCallRing,
		&allowStrangerMsg,
		&profileVisibility,
		&contentLanguage,
		&feedPreference,
		&assistantEnabled,
		&defaultThemeMode,
		&defaultFontSizePreset,
		&appearanceVersion,
		&appearanceUpdatedAt,
		&blockedKeywords,
		&version,
		&updatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return settingsmodel.UserSettings{}, false, nil
	}
	if err != nil {
		return settingsmodel.UserSettings{}, false, err
	}

	start, err := parseOptionalTimeOfDay(quietHoursStart)
	if err != nil {
		return settingsmodel.UserSettings{}, false, err
	}
	end, err := parseOptionalTimeOfDay(quietHoursEnd)
	if err != nil {
		return settingsmodel.UserSettings{}, false, err
	}
	ringtoneID, err := parseOptionalRingtoneID(defaultIncomingCallRingtoneID)
	if err != nil {
		return settingsmodel.UserSettings{}, false, err
	}
	feed, err := parseOptionalFeedPreference(feedPreference)
	if err != nil {
		return settingsmodel.UserSettings{}, false, err
	}
	if len(blockedKeywords) == 0 {
		blockedKeywords = []string{}
	}
	settings := settingsmodel.UserSettings{
		UserID: userID,
		Notification: settingsmodel.NotificationSettings{
			EnablePush:      enablePush,
			EnableMarketing: enableMarketing,
			QuietHoursStart: start,
			QuietHoursEnd:   end,
		},
		Privacy: settingsmodel.PrivacySettings{
			AllowStrangerMsg:  allowStrangerMsg,
			ProfileVisibility: settingsmodel.ProfileVisibility(profileVisibility),
			ContentLanguage:   canonicalOptionalString(contentLanguage),
			FeedPreference:    feed,
			AssistantEnabled:  assistantEnabled,
			BlockedKeywords:   blockedKeywords,
		},
		Call: settingsmodel.CallSettings{
			DefaultIncomingCallRingtoneID: ringtoneID,
			AllowCallerRingtoneOverride:   allowCallerRingtoneOverride,
			EnableCallVibration:           enableCallVibration,
			EnableGroupCallRing:           enableGroupCallRing,
		},
		Appearance: settingsmodel.AppearanceSettings{
			DefaultThemeMode:      settingsmodel.ThemeMode(defaultThemeMode),
			DefaultFontSizePreset: settingsmodel.FontSizePreset(defaultFontSizePreset),
			Version:               appearanceVersion,
			UpdatedAt:             appearanceUpdatedAt.UTC(),
		},
		Version:   version,
		UpdatedAt: updatedAt.UTC(),
	}
	if err := settings.Validate(); err != nil {
		return settingsmodel.UserSettings{}, false, err
	}
	return settings, true, nil
}

func parseOptionalTimeOfDay(
	raw *string,
) (*settingsmodel.TimeOfDay, error) {
	if raw == nil || strings.TrimSpace(*raw) == "" {
		return nil, nil
	}
	value, err := settingsmodel.ParseTimeOfDay(*raw)
	if err != nil {
		return nil, err
	}
	return &value, nil
}

func parseOptionalRingtoneID(
	raw *string,
) (*settingsmodel.OfficialRingtoneID, error) {
	if raw == nil || strings.TrimSpace(*raw) == "" {
		return nil, nil
	}
	value, err := settingsmodel.ParseOfficialRingtoneID(*raw)
	if err != nil {
		return nil, err
	}
	return &value, nil
}

func parseOptionalFeedPreference(
	raw *string,
) (*settingsmodel.FeedPreference, error) {
	if raw == nil || strings.TrimSpace(*raw) == "" {
		return nil, nil
	}
	value := settingsmodel.FeedPreference(strings.TrimSpace(*raw))
	if !value.Valid() {
		return nil, settingsmodel.ErrInvalidArgument
	}
	return &value, nil
}

func nullableTimeOfDay(value *settingsmodel.TimeOfDay) *string {
	if value == nil {
		return nil
	}
	raw := string(*value)
	return &raw
}

func nullableRingtoneID(value *settingsmodel.OfficialRingtoneID) *string {
	if value == nil {
		return nil
	}
	raw := string(*value)
	return &raw
}

func nullableFeedPreference(value *settingsmodel.FeedPreference) *string {
	if value == nil {
		return nil
	}
	raw := string(*value)
	return &raw
}

func canonicalOptionalString(value *string) *string {
	if value == nil {
		return nil
	}
	normalized := strings.TrimSpace(*value)
	if normalized == "" {
		return nil
	}
	return &normalized
}

func nonNilStrings(values []string) []string {
	if len(values) == 0 {
		return []string{}
	}
	return values
}
