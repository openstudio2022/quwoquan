package model

import (
	"fmt"
	"strings"
	"time"
)

type TimeOfDay string

func ParseTimeOfDay(raw string) (TimeOfDay, error) {
	raw = strings.TrimSpace(raw)
	for _, layout := range []string{"15:04", "15:04:05", "15:04:05.999999"} {
		parsed, err := time.Parse(layout, raw)
		if err == nil {
			return TimeOfDay(parsed.Format("15:04")), nil
		}
	}
	return "", fmt.Errorf("%w: quiet hours must use HH:mm", ErrInvalidArgument)
}

func (value TimeOfDay) Valid() bool {
	parsed, err := ParseTimeOfDay(string(value))
	return err == nil && parsed == value
}

type ProfileVisibility string

const (
	ProfileVisibilityPublic  ProfileVisibility = "public"
	ProfileVisibilityFriends ProfileVisibility = "friends"
	ProfileVisibilityPrivate ProfileVisibility = "private"
)

func (value ProfileVisibility) Valid() bool {
	switch value {
	case ProfileVisibilityPublic, ProfileVisibilityFriends, ProfileVisibilityPrivate:
		return true
	default:
		return false
	}
}

type FeedPreference string

const (
	FeedPreferenceRecommend     FeedPreference = "recommend"
	FeedPreferenceChronological FeedPreference = "chronological"
)

func (value FeedPreference) Valid() bool {
	return value == FeedPreferenceRecommend || value == FeedPreferenceChronological
}

type ThemeMode string

const (
	ThemeModeSystem ThemeMode = "system"
	ThemeModeLight  ThemeMode = "light"
	ThemeModeDark   ThemeMode = "dark"
)

func (value ThemeMode) Valid() bool {
	return value == ThemeModeSystem || value == ThemeModeLight || value == ThemeModeDark
}

type FontSizePreset string

const (
	FontSizePresetXS FontSizePreset = "xs"
	FontSizePresetSM FontSizePreset = "sm"
	FontSizePresetMD FontSizePreset = "md"
	FontSizePresetLG FontSizePreset = "lg"
	FontSizePresetXL FontSizePreset = "xl"
)

func (value FontSizePreset) Valid() bool {
	switch value {
	case FontSizePresetXS, FontSizePresetSM, FontSizePresetMD,
		FontSizePresetLG, FontSizePresetXL:
		return true
	default:
		return false
	}
}

type AppearanceApplyScope string

const (
	AppearanceApplyScopeAllAccounts         AppearanceApplyScope = "all_accounts"
	AppearanceApplyScopeCurrentPersona      AppearanceApplyScope = "current_persona"
	AppearanceApplyScopeInheritOwnerDefault AppearanceApplyScope = "inherit_owner_default"
)

func (value AppearanceApplyScope) Valid() bool {
	switch value {
	case AppearanceApplyScopeAllAccounts,
		AppearanceApplyScopeCurrentPersona,
		AppearanceApplyScopeInheritOwnerDefault:
		return true
	default:
		return false
	}
}

type AppearanceSource string

const (
	AppearanceSourceOwnerDefault  AppearanceSource = "owner_default"
	AppearanceSourceSubOverride   AppearanceSource = "sub_override"
	AppearanceSourceSystemDefault AppearanceSource = "system_default"
)

type OfficialRingtoneID string

func ParseOfficialRingtoneID(raw string) (OfficialRingtoneID, error) {
	raw = strings.TrimSpace(raw)
	value := OfficialRingtoneID(raw)
	if !value.Valid() {
		return "", fmt.Errorf(
			"%w: ringtone id must use the official namespace",
			ErrInvalidCallRingtone,
		)
	}
	return value, nil
}

func (value OfficialRingtoneID) Valid() bool {
	raw := string(value)
	return len(raw) <= 64 &&
		strings.HasPrefix(raw, "official.") &&
		strings.TrimSpace(raw) == raw
}
