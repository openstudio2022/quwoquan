// Package model 定义 Account 级 UserSettings 聚合及其不变量。
package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"slices"
	"strconv"
	"strings"
	"time"
)

var (
	ErrInvalidArgument        = errors.New("user settings are invalid")
	ErrInvalidCallRingtone    = errors.New("user settings call ringtone is invalid")
	ErrInvalidAppearanceScope = errors.New("user settings appearance scope is invalid")
	ErrVersionConflict        = errors.New("user settings version conflict")
)

const UserSettingsChangedEvent = "UserSettingsChanged"

type NotificationSettings struct {
	EnablePush      bool
	EnableMarketing bool
	QuietHoursStart *TimeOfDay
	QuietHoursEnd   *TimeOfDay
}

type PrivacySettings struct {
	AllowStrangerMsg  bool
	ProfileVisibility ProfileVisibility
	ContentLanguage   *string
	FeedPreference    *FeedPreference
	AssistantEnabled  bool
	BlockedKeywords   []string
}

type CallSettings struct {
	DefaultIncomingCallRingtoneID *OfficialRingtoneID
	AllowCallerRingtoneOverride   bool
	EnableCallVibration           bool
	EnableGroupCallRing           bool
}

type AppearanceSettings struct {
	DefaultThemeMode      ThemeMode
	DefaultFontSizePreset FontSizePreset
	Version               int64
	UpdatedAt             time.Time
}

type UserSettings struct {
	UserID       string
	Notification NotificationSettings
	Privacy      PrivacySettings
	Call         CallSettings
	Appearance   AppearanceSettings
	Version      int64
	UpdatedAt    time.Time
}

type Snapshot struct {
	UserID       string
	Notification NotificationSettings
	Privacy      PrivacySettings
	Call         CallSettings
	Appearance   AppearanceSettings
	Version      int64
	UpdatedAt    time.Time
}

type Event struct {
	ID               string
	Type             string
	AggregateID      string
	AggregateVersion int64
	OccurredAt       time.Time
}

type ChangeSet struct {
	Aggregate UserSettings
	Events    []Event
	Changed   bool
}

func NewDefault(userID string, now time.Time) (UserSettings, error) {
	settings := UserSettings{
		UserID: strings.TrimSpace(userID),
		Notification: NotificationSettings{
			EnablePush: true,
		},
		Privacy: PrivacySettings{
			AllowStrangerMsg:  true,
			ProfileVisibility: ProfileVisibilityPublic,
			AssistantEnabled:  true,
			BlockedKeywords:   []string{},
		},
		Call: CallSettings{
			AllowCallerRingtoneOverride: true,
			EnableCallVibration:         true,
			EnableGroupCallRing:         true,
		},
		Appearance: AppearanceSettings{
			DefaultThemeMode:      ThemeModeSystem,
			DefaultFontSizePreset: FontSizePresetMD,
			Version:               1,
			UpdatedAt:             now.UTC(),
		},
		Version:   0,
		UpdatedAt: now.UTC(),
	}
	if err := settings.Validate(); err != nil {
		return UserSettings{}, err
	}
	return settings, nil
}

func (settings UserSettings) Clone() UserSettings {
	clone := settings
	clone.Notification.QuietHoursStart = clonePointer(settings.Notification.QuietHoursStart)
	clone.Notification.QuietHoursEnd = clonePointer(settings.Notification.QuietHoursEnd)
	clone.Privacy.ContentLanguage = clonePointer(settings.Privacy.ContentLanguage)
	clone.Privacy.FeedPreference = clonePointer(settings.Privacy.FeedPreference)
	clone.Privacy.BlockedKeywords = append([]string(nil), settings.Privacy.BlockedKeywords...)
	clone.Call.DefaultIncomingCallRingtoneID = clonePointer(
		settings.Call.DefaultIncomingCallRingtoneID,
	)
	return clone
}

func (settings UserSettings) Snapshot() Snapshot {
	clone := settings.Clone()
	return Snapshot{
		UserID:       clone.UserID,
		Notification: clone.Notification,
		Privacy:      clone.Privacy,
		Call:         clone.Call,
		Appearance:   clone.Appearance,
		Version:      clone.Version,
		UpdatedAt:    clone.UpdatedAt,
	}
}

func (settings UserSettings) Validate() error {
	if settings.UserID == "" || strings.TrimSpace(settings.UserID) != settings.UserID ||
		len(settings.UserID) > 96 {
		return fmt.Errorf("%w: userId is required and must not exceed 96 bytes", ErrInvalidArgument)
	}
	if settings.Version < 0 || settings.UpdatedAt.IsZero() {
		return fmt.Errorf("%w: version and updatedAt are required", ErrInvalidArgument)
	}
	if err := validateNotification(settings.Notification); err != nil {
		return err
	}
	if err := validatePrivacy(settings.Privacy); err != nil {
		return err
	}
	if err := validateCall(settings.Call); err != nil {
		return err
	}
	if err := validateAppearance(settings.Appearance); err != nil {
		return err
	}
	if settings.Appearance.UpdatedAt.After(settings.UpdatedAt) {
		return fmt.Errorf(
			"%w: appearanceUpdatedAt cannot be after aggregate updatedAt",
			ErrInvalidArgument,
		)
	}
	return nil
}

func (settings UserSettings) UpdateNotification(
	next NotificationSettings,
	now time.Time,
) (ChangeSet, error) {
	if err := settings.Validate(); err != nil {
		return ChangeSet{}, err
	}
	if err := validateNotification(next); err != nil {
		return ChangeSet{}, err
	}
	next = cloneNotification(next)
	if equalNotification(settings.Notification, next) {
		return unchanged(settings), nil
	}
	updated := settings.Clone()
	updated.Notification = next
	return settings.finish(updated, now)
}

func (settings UserSettings) UpdatePrivacy(
	next PrivacySettings,
	now time.Time,
) (ChangeSet, error) {
	if err := settings.Validate(); err != nil {
		return ChangeSet{}, err
	}
	next = normalizePrivacy(next)
	if err := validatePrivacy(next); err != nil {
		return ChangeSet{}, err
	}
	if equalPrivacy(settings.Privacy, next) {
		return unchanged(settings), nil
	}
	updated := settings.Clone()
	updated.Privacy = next
	return settings.finish(updated, now)
}

func (settings UserSettings) UpdateCall(
	next CallSettings,
	now time.Time,
) (ChangeSet, error) {
	if err := settings.Validate(); err != nil {
		return ChangeSet{}, err
	}
	if err := validateCall(next); err != nil {
		return ChangeSet{}, err
	}
	next.DefaultIncomingCallRingtoneID = clonePointer(
		next.DefaultIncomingCallRingtoneID,
	)
	if equalCall(settings.Call, next) {
		return unchanged(settings), nil
	}
	updated := settings.Clone()
	updated.Call = next
	return settings.finish(updated, now)
}

func (settings UserSettings) UpdateAppearance(
	themeMode ThemeMode,
	fontSizePreset FontSizePreset,
	now time.Time,
) (ChangeSet, error) {
	if err := settings.Validate(); err != nil {
		return ChangeSet{}, err
	}
	if !themeMode.Valid() || !fontSizePreset.Valid() {
		return ChangeSet{}, fmt.Errorf(
			"%w: themeMode or fontSizePreset is unknown",
			ErrInvalidArgument,
		)
	}
	if settings.Appearance.DefaultThemeMode == themeMode &&
		settings.Appearance.DefaultFontSizePreset == fontSizePreset {
		return unchanged(settings), nil
	}
	if now.IsZero() {
		return ChangeSet{}, fmt.Errorf("%w: mutation time is required", ErrInvalidArgument)
	}
	updated := settings.Clone()
	updated.Appearance.DefaultThemeMode = themeMode
	updated.Appearance.DefaultFontSizePreset = fontSizePreset
	updated.Appearance.Version++
	updated.Appearance.UpdatedAt = now.UTC()
	return settings.finish(updated, now)
}

func (settings UserSettings) finish(updated UserSettings, now time.Time) (ChangeSet, error) {
	if now.IsZero() {
		return ChangeSet{}, fmt.Errorf("%w: mutation time is required", ErrInvalidArgument)
	}
	updated.Version = settings.Version + 1
	updated.UpdatedAt = now.UTC()
	if err := updated.Validate(); err != nil {
		return ChangeSet{}, err
	}
	event := Event{
		ID:               eventID(updated.UserID, updated.Version),
		Type:             UserSettingsChangedEvent,
		AggregateID:      updated.UserID,
		AggregateVersion: updated.Version,
		OccurredAt:       now.UTC(),
	}
	return ChangeSet{
		Aggregate: updated,
		Events:    []Event{event},
		Changed:   true,
	}, nil
}

func unchanged(settings UserSettings) ChangeSet {
	return ChangeSet{Aggregate: settings.Clone()}
}

func validateNotification(settings NotificationSettings) error {
	if (settings.QuietHoursStart == nil) != (settings.QuietHoursEnd == nil) {
		return fmt.Errorf(
			"%w: quietHoursStart and quietHoursEnd must be set together",
			ErrInvalidArgument,
		)
	}
	if settings.QuietHoursStart != nil &&
		(!settings.QuietHoursStart.Valid() || !settings.QuietHoursEnd.Valid()) {
		return fmt.Errorf("%w: quiet hours must use HH:mm", ErrInvalidArgument)
	}
	return nil
}

func validatePrivacy(settings PrivacySettings) error {
	if !settings.ProfileVisibility.Valid() {
		return fmt.Errorf("%w: profileVisibility is unknown", ErrInvalidArgument)
	}
	if settings.ContentLanguage != nil {
		language := *settings.ContentLanguage
		if language == "" || strings.TrimSpace(language) != language || len(language) > 16 {
			return fmt.Errorf("%w: contentLanguage is invalid", ErrInvalidArgument)
		}
	}
	if settings.FeedPreference != nil && !settings.FeedPreference.Valid() {
		return fmt.Errorf("%w: feedPreference is unknown", ErrInvalidArgument)
	}
	if !slices.Equal(settings.BlockedKeywords, normalizeKeywords(settings.BlockedKeywords)) {
		return fmt.Errorf("%w: blockedKeywords must be normalized and unique", ErrInvalidArgument)
	}
	return nil
}

func validateCall(settings CallSettings) error {
	if settings.DefaultIncomingCallRingtoneID != nil &&
		!settings.DefaultIncomingCallRingtoneID.Valid() {
		return fmt.Errorf(
			"%w: ringtone id must use the official namespace",
			ErrInvalidCallRingtone,
		)
	}
	return nil
}

func validateAppearance(settings AppearanceSettings) error {
	if !settings.DefaultThemeMode.Valid() ||
		!settings.DefaultFontSizePreset.Valid() ||
		settings.Version < 1 ||
		settings.UpdatedAt.IsZero() {
		return fmt.Errorf("%w: appearance defaults are invalid", ErrInvalidArgument)
	}
	return nil
}

func normalizePrivacy(settings PrivacySettings) PrivacySettings {
	settings.ContentLanguage = normalizeOptionalString(settings.ContentLanguage)
	settings.FeedPreference = clonePointer(settings.FeedPreference)
	settings.BlockedKeywords = normalizeKeywords(settings.BlockedKeywords)
	return settings
}

func normalizeOptionalString(value *string) *string {
	if value == nil {
		return nil
	}
	normalized := strings.TrimSpace(*value)
	if normalized == "" {
		return nil
	}
	return &normalized
}

func normalizeKeywords(values []string) []string {
	if len(values) == 0 {
		return []string{}
	}
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		normalized := strings.TrimSpace(value)
		if normalized == "" {
			continue
		}
		if _, exists := seen[normalized]; exists {
			continue
		}
		seen[normalized] = struct{}{}
		result = append(result, normalized)
	}
	return result
}

func cloneNotification(settings NotificationSettings) NotificationSettings {
	settings.QuietHoursStart = clonePointer(settings.QuietHoursStart)
	settings.QuietHoursEnd = clonePointer(settings.QuietHoursEnd)
	return settings
}

func equalNotification(left, right NotificationSettings) bool {
	return left.EnablePush == right.EnablePush &&
		left.EnableMarketing == right.EnableMarketing &&
		equalPointer(left.QuietHoursStart, right.QuietHoursStart) &&
		equalPointer(left.QuietHoursEnd, right.QuietHoursEnd)
}

func equalPrivacy(left, right PrivacySettings) bool {
	return left.AllowStrangerMsg == right.AllowStrangerMsg &&
		left.ProfileVisibility == right.ProfileVisibility &&
		equalPointer(left.ContentLanguage, right.ContentLanguage) &&
		equalPointer(left.FeedPreference, right.FeedPreference) &&
		left.AssistantEnabled == right.AssistantEnabled &&
		slices.Equal(left.BlockedKeywords, right.BlockedKeywords)
}

func equalCall(left, right CallSettings) bool {
	return equalPointer(
		left.DefaultIncomingCallRingtoneID,
		right.DefaultIncomingCallRingtoneID,
	) &&
		left.AllowCallerRingtoneOverride == right.AllowCallerRingtoneOverride &&
		left.EnableCallVibration == right.EnableCallVibration &&
		left.EnableGroupCallRing == right.EnableGroupCallRing
}

func clonePointer[T any](value *T) *T {
	if value == nil {
		return nil
	}
	clone := *value
	return &clone
}

func equalPointer[T comparable](left, right *T) bool {
	if left == nil || right == nil {
		return left == nil && right == nil
	}
	return *left == *right
}

func eventID(userID string, version int64) string {
	digest := sha256.Sum256([]byte(
		userID + "\x00" + strconv.FormatInt(version, 10) + "\x00" +
			UserSettingsChangedEvent,
	))
	return "use_" + hex.EncodeToString(digest[:16])
}
