package local_contract

import (
	"errors"
	"testing"
	"time"

	runtimeerrors "quwoquan_service/runtime/errors"
	settingsapp "quwoquan_service/services/user-service/internal/account/user_settings/application"
	settingsmodel "quwoquan_service/services/user-service/internal/account/user_settings/domain/model"
)

func assertSettingsErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) || appErr.Code.String() != wantCode {
		t.Fatalf("expected %s, got %T: %v", wantCode, err, err)
	}
}

func TestUserSettingsCommandFacadeRejectsUnknownAppearanceScope(t *testing.T) {
	t.Parallel()

	current, err := settingsmodel.NewDefault(
		"account-invalid-scope",
		time.Date(2026, 8, 12, 9, 0, 0, 0, time.UTC),
	)
	if err != nil {
		t.Fatalf("创建默认设置: %v", err)
	}
	facade := settingsapp.NewUserSettingsCommandFacade(
		&fakeUserSettingsStore{current: current, found: true},
	)

	_, err = facade.UpdateAppearanceSettings(
		trustedAccountContext("account-invalid-scope"),
		settingsapp.UpdateAppearanceSettingsCommand{
			ThemeMode:      settingsmodel.ThemeModeDark,
			FontSizePreset: settingsmodel.FontSizePresetLG,
			ApplyScope:     settingsmodel.AppearanceApplyScope("everything"),
		},
	)
	assertSettingsErrorCode(t, err, "USER.SETTING.invalid_appearance_scope")
}

func TestUserSettingsCommandFacadeSurfacesVersionConflictAfterCASRetries(
	t *testing.T,
) {
	t.Parallel()

	current, err := settingsmodel.NewDefault(
		"account-cas-exhausted",
		time.Date(2026, 8, 12, 9, 0, 0, 0, time.UTC),
	)
	if err != nil {
		t.Fatalf("创建默认设置: %v", err)
	}
	current.Version = 2
	store := &fakeUserSettingsStore{
		current: current,
		found:   true,
		// CAS 重试上限为 3 次；持续冲突必须以 settings_version_conflict 收敛。
		conflicts: 3,
		concurrentChange: func(latest *settingsmodel.UserSettings) {
			latest.Privacy.AssistantEnabled = !latest.Privacy.AssistantEnabled
		},
	}
	facade := settingsapp.NewUserSettingsCommandFacade(store)

	_, err = facade.UpdateNotificationSettings(
		trustedAccountContext("account-cas-exhausted"),
		settingsapp.UpdateNotificationSettingsCommand{
			EnablePush: settingsapp.Set(false),
		},
	)
	assertSettingsErrorCode(t, err, "USER.SETTING.settings_version_conflict")
	if store.commitCalls != 3 {
		t.Fatalf("CAS 冲突应耗尽 3 次提交重试, 实际 commits=%d", store.commitCalls)
	}
}
