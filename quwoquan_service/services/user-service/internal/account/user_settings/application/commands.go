package user_settings

import settingsmodel "quwoquan_service/services/user-service/internal/account/user_settings/domain/model"

// Patch 显式区分“字段未提供”与“提供零值”；nullable 字段使用 Patch[*T]，
// 从而不需要动态 map patch。
type Patch[T any] struct {
	Present bool
	Value   T
}

func Set[T any](value T) Patch[T] {
	return Patch[T]{Present: true, Value: value}
}

type UpdateNotificationSettingsCommand struct {
	EnablePush      Patch[bool]
	EnableMarketing Patch[bool]
	QuietHoursStart Patch[*settingsmodel.TimeOfDay]
	QuietHoursEnd   Patch[*settingsmodel.TimeOfDay]
}

type UpdatePrivacySettingsCommand struct {
	AllowStrangerMsg  Patch[bool]
	ProfileVisibility Patch[settingsmodel.ProfileVisibility]
	BlockedKeywords   Patch[[]string]
	AssistantEnabled  Patch[bool]
}

type UpdateCallSettingsCommand struct {
	DefaultIncomingCallRingtoneID Patch[*settingsmodel.OfficialRingtoneID]
	AllowCallerRingtoneOverride   Patch[bool]
	EnableCallVibration           Patch[bool]
	EnableGroupCallRing           Patch[bool]
}

type UpdateAppearanceSettingsCommand struct {
	ThemeMode      settingsmodel.ThemeMode
	FontSizePreset settingsmodel.FontSizePreset
	ApplyScope     settingsmodel.AppearanceApplyScope
}

type CommandResult struct {
	UserID           string `json:"userId"`
	Version          int64  `json:"version"`
	IdempotentReplay bool   `json:"idempotentReplay"`
}
