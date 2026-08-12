package user_settings

import (
	"context"
	"strings"
	"time"

	"quwoquan_service/services/user-service/generated/account/user_account"
	settingsmodel "quwoquan_service/services/user-service/internal/account/user_settings/domain/model"
	settingsports "quwoquan_service/services/user-service/internal/account/user_settings/domain/ports"
)

// UserSettingsQueryFacade 只消费 typed SnapshotReader，并输出 snapshot/section slice。
type UserSettingsQueryFacade struct {
	reader settingsports.SnapshotReader
	now    func() time.Time
}

func NewUserSettingsQueryFacade(
	reader settingsports.SnapshotReader,
) *UserSettingsQueryFacade {
	if reader == nil {
		panic("UserSettingsQueryFacade requires a typed SnapshotReader")
	}
	return &UserSettingsQueryFacade{reader: reader, now: time.Now}
}

func (facade *UserSettingsQueryFacade) GetSnapshot(
	ctx context.Context,
) (settingsmodel.Snapshot, error) {
	return facade.loadSnapshot(ctx)
}

func (facade *UserSettingsQueryFacade) GetNotificationSettings(
	ctx context.Context,
) (settingsports.GetNotificationSettingsSlice, error) {
	snapshot, err := facade.loadSnapshot(ctx)
	if err != nil {
		return settingsports.GetNotificationSettingsSlice{}, err
	}
	return settingsports.GetNotificationSettingsSlice{
		UserID:          snapshot.UserID,
		EnablePush:      snapshot.Notification.EnablePush,
		EnableMarketing: snapshot.Notification.EnableMarketing,
		QuietHoursStart: clonePointer(snapshot.Notification.QuietHoursStart),
		QuietHoursEnd:   clonePointer(snapshot.Notification.QuietHoursEnd),
		Version:         snapshot.Version,
		UpdatedAt:       snapshot.UpdatedAt,
	}, nil
}

func (facade *UserSettingsQueryFacade) GetPrivacySettings(
	ctx context.Context,
) (settingsports.GetPrivacySettingsSlice, error) {
	snapshot, err := facade.loadSnapshot(ctx)
	if err != nil {
		return settingsports.GetPrivacySettingsSlice{}, err
	}
	return settingsports.GetPrivacySettingsSlice{
		UserID:            snapshot.UserID,
		AllowStrangerMsg:  snapshot.Privacy.AllowStrangerMsg,
		ProfileVisibility: snapshot.Privacy.ProfileVisibility,
		ContentLanguage:   clonePointer(snapshot.Privacy.ContentLanguage),
		FeedPreference:    clonePointer(snapshot.Privacy.FeedPreference),
		AssistantEnabled:  snapshot.Privacy.AssistantEnabled,
		BlockedKeywords: append(
			[]string{},
			snapshot.Privacy.BlockedKeywords...,
		),
		Version:   snapshot.Version,
		UpdatedAt: snapshot.UpdatedAt,
	}, nil
}

func (facade *UserSettingsQueryFacade) ResolveAssistantDeliveryPolicy(
	ctx context.Context,
	userID string,
) (settingsports.AssistantDeliveryPolicyView, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return settingsports.AssistantDeliveryPolicyView{},
			generated.AppErrorFromUserNotFound(
				"assistant delivery policy owner is unavailable",
			)
	}
	snapshot, err := facade.loadSnapshotForUser(ctx, userID)
	if err != nil {
		return settingsports.AssistantDeliveryPolicyView{}, err
	}
	return settingsports.AssistantDeliveryPolicyView{
		UserID:           snapshot.UserID,
		AssistantEnabled: snapshot.Privacy.AssistantEnabled,
		QuietHoursStart:  clonePointer(snapshot.Notification.QuietHoursStart),
		QuietHoursEnd:    clonePointer(snapshot.Notification.QuietHoursEnd),
		Version:          snapshot.Version,
		UpdatedAt:        snapshot.UpdatedAt,
	}, nil
}

func (facade *UserSettingsQueryFacade) GetCallSettings(
	ctx context.Context,
) (settingsports.GetCallSettingsSlice, error) {
	snapshot, err := facade.loadSnapshot(ctx)
	if err != nil {
		return settingsports.GetCallSettingsSlice{}, err
	}
	return settingsports.GetCallSettingsSlice{
		UserID: snapshot.UserID,
		DefaultIncomingCallRingtoneID: clonePointer(
			snapshot.Call.DefaultIncomingCallRingtoneID,
		),
		AllowCallerRingtoneOverride: snapshot.Call.AllowCallerRingtoneOverride,
		EnableCallVibration:         snapshot.Call.EnableCallVibration,
		EnableGroupCallRing:         snapshot.Call.EnableGroupCallRing,
		Version:                     snapshot.Version,
		UpdatedAt:                   snapshot.UpdatedAt,
	}, nil
}

func (facade *UserSettingsQueryFacade) GetAppearanceSettings(
	ctx context.Context,
) (settingsports.GetAppearanceSettingsSlice, error) {
	snapshot, err := facade.loadSnapshot(ctx)
	if err != nil {
		return settingsports.GetAppearanceSettingsSlice{}, err
	}
	return settingsports.GetAppearanceSettingsSlice{
		ThemeMode:                  snapshot.Appearance.DefaultThemeMode,
		FontSizePreset:             snapshot.Appearance.DefaultFontSizePreset,
		Source:                     settingsmodel.AppearanceSourceOwnerDefault,
		OwnerDefaultThemeMode:      snapshot.Appearance.DefaultThemeMode,
		OwnerDefaultFontSizePreset: snapshot.Appearance.DefaultFontSizePreset,
		HasPersonaOverride:         false,
		Version:                    snapshot.Appearance.Version,
		UpdatedAt:                  snapshot.Appearance.UpdatedAt,
	}, nil
}

func (facade *UserSettingsQueryFacade) loadSnapshot(
	ctx context.Context,
) (settingsmodel.Snapshot, error) {
	userID, err := trustedAccountID(ctx)
	if err != nil {
		return settingsmodel.Snapshot{}, err
	}
	return facade.loadSnapshotForUser(ctx, userID)
}

func (facade *UserSettingsQueryFacade) loadSnapshotForUser(
	ctx context.Context,
	userID string,
) (settingsmodel.Snapshot, error) {
	snapshot, found, err := facade.reader.ReadUserSettingsSnapshot(ctx, userID)
	if err != nil {
		return settingsmodel.Snapshot{}, generated.AppErrorFromInternalError(err.Error())
	}
	if found {
		return snapshot, nil
	}
	defaults, err := settingsmodel.NewDefault(userID, facade.now())
	if err != nil {
		return settingsmodel.Snapshot{}, mapMutationError(err)
	}
	return defaults.Snapshot(), nil
}
