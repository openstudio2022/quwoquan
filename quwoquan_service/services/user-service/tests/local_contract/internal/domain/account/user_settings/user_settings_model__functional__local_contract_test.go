package local_contract

import (
	"errors"
	"testing"
	"time"

	settingsmodel "quwoquan_service/services/user-service/internal/domain/account/user_settings/model"
)

func TestUserSettingsModelValidatesSectionInvariants(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	settings, err := settingsmodel.NewDefault("account-1", now)
	if err != nil {
		t.Fatalf("创建默认设置: %v", err)
	}
	if err := settings.Validate(); err != nil {
		t.Fatalf("默认设置应通过校验: %v", err)
	}

	start, err := settingsmodel.ParseTimeOfDay("22:30")
	if err != nil {
		t.Fatalf("解析免打扰开始时间: %v", err)
	}
	invalidQuietHours := settings
	invalidQuietHours.Notification.QuietHoursStart = &start
	if err := invalidQuietHours.Validate(); !errors.Is(err, settingsmodel.ErrInvalidArgument) {
		t.Fatalf("单边免打扰时间应被拒绝，得到: %v", err)
	}

	invalidRingtone := settingsmodel.OfficialRingtoneID("custom.upload")
	invalidCall := settings
	invalidCall.Call.DefaultIncomingCallRingtoneID = &invalidRingtone
	if err := invalidCall.Validate(); !errors.Is(err, settingsmodel.ErrInvalidCallRingtone) {
		t.Fatalf("非官方铃声应被拒绝，得到: %v", err)
	}

	invalidAppearance := settings
	invalidAppearance.Appearance.DefaultThemeMode = settingsmodel.ThemeMode("sepia")
	if err := invalidAppearance.Validate(); !errors.Is(err, settingsmodel.ErrInvalidArgument) {
		t.Fatalf("未知主题模式应被拒绝，得到: %v", err)
	}
}

func TestUserSettingsModelNoopDoesNotAdvanceVersionOrEmitEvent(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	settings, err := settingsmodel.NewDefault("account-1", now)
	if err != nil {
		t.Fatalf("创建默认设置: %v", err)
	}

	noop, err := settings.UpdateNotification(settings.Notification, now.Add(time.Minute))
	if err != nil {
		t.Fatalf("执行同值更新: %v", err)
	}
	if noop.Changed {
		t.Fatal("同值更新不应标记为 changed")
	}
	if noop.Aggregate.Version != settings.Version || len(noop.Events) != 0 {
		t.Fatalf(
			"同值更新不得推进版本或发事件: version=%d events=%d",
			noop.Aggregate.Version,
			len(noop.Events),
		)
	}

	changedNotification := settings.Notification
	changedNotification.EnablePush = false
	change, err := settings.UpdateNotification(
		changedNotification,
		now.Add(2*time.Minute),
	)
	if err != nil {
		t.Fatalf("执行通知设置更新: %v", err)
	}
	if !change.Changed || change.Aggregate.Version != settings.Version+1 {
		t.Fatalf("真实变更应推进一个版本: %+v", change)
	}
	if len(change.Events) != 1 ||
		change.Events[0].Type != settingsmodel.UserSettingsChangedEvent ||
		change.Events[0].AggregateVersion != change.Aggregate.Version {
		t.Fatalf("真实变更应产生版本对齐的 UserSettingsChanged: %+v", change.Events)
	}
}
