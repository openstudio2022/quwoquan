// Package ports 定义 UserSettings 对象专属 Store 与 named Reader 合同。
package ports

import (
	"context"
	"time"

	"quwoquan_service/services/user-service/internal/account/user_settings/domain/model"
)

// AggregateStore 只负责 UserSettings 聚合；Commit 必须以 expectedVersion 做
// 服务端内部 CAS，并在同一事务写入 state 与 UserSettingsChanged outbox。
type AggregateStore interface {
	Load(
		ctx context.Context,
		userID string,
	) (settings model.UserSettings, found bool, err error)
	Commit(
		ctx context.Context,
		expectedVersion int64,
		change model.ChangeSet,
	) error
}

// SnapshotReader 是查询侧唯一持久化端口，不向 application 暴露可变聚合。
type SnapshotReader interface {
	ReadUserSettingsSnapshot(
		ctx context.Context,
		userID string,
	) (snapshot model.Snapshot, found bool, err error)
}

type GetNotificationSettingsSlice struct {
	UserID          string           `json:"userId"`
	EnablePush      bool             `json:"enablePush"`
	EnableMarketing bool             `json:"enableMarketing"`
	QuietHoursStart *model.TimeOfDay `json:"quietHoursStart"`
	QuietHoursEnd   *model.TimeOfDay `json:"quietHoursEnd"`
	Version         int64            `json:"version"`
	UpdatedAt       time.Time        `json:"updatedAt"`
}

type GetPrivacySettingsSlice struct {
	UserID            string                  `json:"userId"`
	AllowStrangerMsg  bool                    `json:"allowStrangerMsg"`
	ProfileVisibility model.ProfileVisibility `json:"profileVisibility"`
	ContentLanguage   *string                 `json:"contentLanguage"`
	FeedPreference    *model.FeedPreference   `json:"feedPreference"`
	AssistantEnabled  bool                    `json:"assistantEnabled"`
	BlockedKeywords   []string                `json:"blockedKeywords"`
	Version           int64                   `json:"version"`
	UpdatedAt         time.Time               `json:"updatedAt"`
}

type AssistantDeliveryPolicyView struct {
	UserID           string           `json:"userId"`
	AssistantEnabled bool             `json:"assistantEnabled"`
	QuietHoursStart  *model.TimeOfDay `json:"quietHoursStart"`
	QuietHoursEnd    *model.TimeOfDay `json:"quietHoursEnd"`
	Version          int64            `json:"version"`
	UpdatedAt        time.Time        `json:"updatedAt"`
}

type GetCallSettingsSlice struct {
	UserID                        string                    `json:"userId"`
	DefaultIncomingCallRingtoneID *model.OfficialRingtoneID `json:"defaultIncomingCallRingtoneId"`
	AllowCallerRingtoneOverride   bool                      `json:"allowCallerRingtoneOverride"`
	EnableCallVibration           bool                      `json:"enableCallVibration"`
	EnableGroupCallRing           bool                      `json:"enableGroupCallRing"`
	Version                       int64                     `json:"version"`
	UpdatedAt                     time.Time                 `json:"updatedAt"`
}

// GetAppearanceSettingsSlice 是 UserSettings owner-default 部分的 typed slice。
// Persona override 由父级 coordinator 通过 Persona named Reader 合成。
type GetAppearanceSettingsSlice struct {
	ThemeMode                  model.ThemeMode        `json:"themeMode"`
	FontSizePreset             model.FontSizePreset   `json:"fontSizePreset"`
	Source                     model.AppearanceSource `json:"source"`
	OwnerDefaultThemeMode      model.ThemeMode        `json:"ownerDefaultThemeMode"`
	OwnerDefaultFontSizePreset model.FontSizePreset   `json:"ownerDefaultFontSizePreset"`
	HasPersonaOverride         bool                   `json:"hasPersonaOverride"`
	Version                    int64                  `json:"version"`
	UpdatedAt                  time.Time              `json:"updatedAt"`
}
