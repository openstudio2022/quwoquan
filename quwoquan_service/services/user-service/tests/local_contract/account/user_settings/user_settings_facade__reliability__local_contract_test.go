// spec_ref: specs/feature-tree/runtime/runtime-assistant/proactive-subscription-delivery/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/settings-audit/spec.md#gwt-001
// readiness_case: get-notification-settings-local
// readiness_case: get-privacy-settings-local
// readiness_case: resolve-assistant-delivery-policy-local
// readiness_case: get-call-settings-local
// readiness_case: get-appearance-settings-local
// readiness_case: update-notification-settings-local
// readiness_case: update-privacy-settings-local
// readiness_case: update-call-settings-local
// readiness_case: update-appearance-settings-local
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	settingsapp "quwoquan_service/services/user-service/internal/account/user_settings/application"
	settingsmodel "quwoquan_service/services/user-service/internal/account/user_settings/domain/model"
)

type fakeUserSettingsStore struct {
	current          settingsmodel.UserSettings
	found            bool
	conflicts        int
	loadCalls        int
	commitCalls      int
	committedEvents  []settingsmodel.Event
	concurrentChange func(*settingsmodel.UserSettings)
}

func (s *fakeUserSettingsStore) Load(
	_ context.Context,
	_ string,
) (settingsmodel.UserSettings, bool, error) {
	s.loadCalls++
	return s.current.Clone(), s.found, nil
}

func (s *fakeUserSettingsStore) ReadUserSettingsSnapshot(
	_ context.Context,
	_ string,
) (settingsmodel.Snapshot, bool, error) {
	return s.current.Snapshot(), s.found, nil
}

func (s *fakeUserSettingsStore) Commit(
	_ context.Context,
	expectedVersion int64,
	change settingsmodel.ChangeSet,
) error {
	s.commitCalls++
	if s.conflicts > 0 {
		s.conflicts--
		if s.concurrentChange != nil {
			s.concurrentChange(&s.current)
		}
		s.current.Version++
		s.current.UpdatedAt = change.Aggregate.UpdatedAt
		return settingsmodel.ErrVersionConflict
	}
	if !s.found || s.current.Version != expectedVersion {
		return settingsmodel.ErrVersionConflict
	}
	if !change.Changed || len(change.Events) != 1 {
		return errors.New("fake store received invalid change set")
	}
	s.current = change.Aggregate.Clone()
	s.committedEvents = append(s.committedEvents, change.Events...)
	return nil
}

func TestUserSettingsCommandFacadeRetriesInternalCASAndReplaysIntent(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	current, err := settingsmodel.NewDefault("account-1", now)
	if err != nil {
		t.Fatalf("创建默认设置: %v", err)
	}
	current.Version = 4
	store := &fakeUserSettingsStore{
		current:   current,
		found:     true,
		conflicts: 1,
		concurrentChange: func(latest *settingsmodel.UserSettings) {
			latest.Privacy.AssistantEnabled = false
		},
	}
	facade := settingsapp.NewUserSettingsCommandFacade(store)

	result, err := facade.UpdateNotificationSettings(
		trustedAccountContext("account-1"),
		settingsapp.UpdateNotificationSettingsCommand{
			EnablePush: settingsapp.Set(false),
		},
	)
	if err != nil {
		t.Fatalf("CAS 重放后更新失败: %v", err)
	}
	if result.Version != 6 || result.IdempotentReplay {
		t.Fatalf("CAS 重放应提交 latest+1，得到: %+v", result)
	}
	if store.loadCalls != 2 || store.commitCalls != 2 {
		t.Fatalf(
			"CAS 冲突应重新加载并重放一次: loads=%d commits=%d",
			store.loadCalls,
			store.commitCalls,
		)
	}
	if store.current.Notification.EnablePush ||
		store.current.Privacy.AssistantEnabled ||
		len(store.committedEvents) != 1 {
		t.Fatalf("重放必须保留并发字段且只提交一个事件: %+v", store.current)
	}

	commitsBeforeNoop := store.commitCalls
	noop, err := facade.UpdateNotificationSettings(
		trustedAccountContext("account-1"),
		settingsapp.UpdateNotificationSettingsCommand{
			EnablePush: settingsapp.Set(false),
		},
	)
	if err != nil {
		t.Fatalf("同值更新失败: %v", err)
	}
	if !noop.IdempotentReplay || noop.Version != result.Version {
		t.Fatalf("同值更新应返回当前版本的 no-op 回执: %+v", noop)
	}
	if store.commitCalls != commitsBeforeNoop || len(store.committedEvents) != 1 {
		t.Fatal("同值更新不得调用 Commit 或追加 outbox 事件")
	}
}

func TestUserSettingsCommandFacadeKeepsUpdatedAtMonotonicAcrossClockSkew(
	t *testing.T,
) {
	t.Parallel()

	databaseNow := time.Date(2099, 7, 20, 8, 0, 0, 0, time.UTC)
	current, err := settingsmodel.NewDefault("account-clock-skew", databaseNow)
	if err != nil {
		t.Fatalf("创建数据库时钟设置: %v", err)
	}
	current.Version = 3
	store := &fakeUserSettingsStore{current: current, found: true}
	facade := settingsapp.NewUserSettingsCommandFacade(store)

	result, err := facade.UpdatePrivacySettings(
		trustedAccountContext("account-clock-skew"),
		settingsapp.UpdatePrivacySettingsCommand{
			BlockedKeywords: settingsapp.Set([]string{"after"}),
		},
	)
	if err != nil {
		t.Fatalf("应用时钟落后数据库时钟时更新不应失败: %v", err)
	}
	if result.Version != 4 ||
		!store.current.UpdatedAt.Equal(databaseNow) ||
		len(store.committedEvents) != 1 ||
		!store.committedEvents[0].OccurredAt.Equal(databaseNow) {
		t.Fatalf(
			"CAS/version 应推进且时间不得回退: result=%+v state=%+v events=%+v",
			result,
			store.current,
			store.committedEvents,
		)
	}
}

func TestUserSettingsCommandFacadeUpdatesCallAndAppearanceSections(t *testing.T) {
	t.Parallel()
	current, err := settingsmodel.NewDefault(
		"account-sections",
		time.Date(2026, 8, 5, 9, 0, 0, 0, time.UTC),
	)
	if err != nil {
		t.Fatal(err)
	}
	store := &fakeUserSettingsStore{current: current, found: true}
	facade := settingsapp.NewUserSettingsCommandFacade(store)
	ringtone := settingsmodel.OfficialRingtoneID("official.classic")
	callResult, err := facade.UpdateCallSettings(
		trustedAccountContext("account-sections"),
		settingsapp.UpdateCallSettingsCommand{
			DefaultIncomingCallRingtoneID: settingsapp.Set(&ringtone),
			EnableGroupCallRing:           settingsapp.Set(false),
		},
	)
	if err != nil || callResult.Version != 1 ||
		store.current.Call.DefaultIncomingCallRingtoneID == nil ||
		*store.current.Call.DefaultIncomingCallRingtoneID != ringtone {
		t.Fatalf("UpdateCallSettings: result=%+v state=%+v err=%v", callResult, store.current.Call, err)
	}
	appearanceResult, err := facade.UpdateAppearanceSettings(
		trustedAccountContext("account-sections"),
		settingsapp.UpdateAppearanceSettingsCommand{
			ThemeMode:      settingsmodel.ThemeModeDark,
			FontSizePreset: settingsmodel.FontSizePresetLG,
			ApplyScope:     settingsmodel.AppearanceApplyScopeAllAccounts,
		},
	)
	if err != nil || appearanceResult.Version != 2 ||
		store.current.Appearance.DefaultThemeMode != settingsmodel.ThemeModeDark ||
		store.current.Appearance.DefaultFontSizePreset != settingsmodel.FontSizePresetLG {
		t.Fatalf("UpdateAppearanceSettings: result=%+v state=%+v err=%v", appearanceResult, store.current.Appearance, err)
	}
}

func TestUserSettingsQueryFacadeReturnsTypedSnapshotAndSectionSlices(
	t *testing.T,
) {
	t.Parallel()

	now := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	current, err := settingsmodel.NewDefault("account-1", now)
	if err != nil {
		t.Fatalf("创建默认设置: %v", err)
	}
	current.Version = 7
	language := "zh-CN"
	feed := settingsmodel.FeedPreferenceChronological
	ringtone := settingsmodel.OfficialRingtoneID("official.classic")
	current.Privacy.ContentLanguage = &language
	current.Privacy.FeedPreference = &feed
	current.Privacy.BlockedKeywords = []string{"spoiler"}
	current.Call.DefaultIncomingCallRingtoneID = &ringtone
	store := &fakeUserSettingsStore{current: current, found: true}
	facade := settingsapp.NewUserSettingsQueryFacade(store)
	ctx := trustedAccountContext("account-1")

	snapshot, err := facade.GetSnapshot(ctx)
	if err != nil {
		t.Fatalf("读取 typed snapshot: %v", err)
	}
	notifications, err := facade.GetNotificationSettings(ctx)
	if err != nil {
		t.Fatalf("读取 notification slice: %v", err)
	}
	privacy, err := facade.GetPrivacySettings(ctx)
	if err != nil {
		t.Fatalf("读取 privacy slice: %v", err)
	}
	calls, err := facade.GetCallSettings(ctx)
	if err != nil {
		t.Fatalf("读取 call slice: %v", err)
	}
	appearance, err := facade.GetAppearanceSettings(ctx)
	if err != nil {
		t.Fatalf("读取 appearance slice: %v", err)
	}

	if snapshot.Version != 7 || !notifications.EnablePush ||
		privacy.ContentLanguage == nil ||
		*privacy.ContentLanguage != language ||
		privacy.FeedPreference == nil ||
		*privacy.FeedPreference != feed ||
		len(privacy.BlockedKeywords) != 1 {
		t.Fatalf("snapshot/privacy slice 丢失字段: snapshot=%+v privacy=%+v", snapshot, privacy)
	}
	if calls.DefaultIncomingCallRingtoneID == nil ||
		*calls.DefaultIncomingCallRingtoneID != ringtone {
		t.Fatalf("call slice 丢失铃声字段: %+v", calls)
	}
	if appearance.Source != settingsmodel.AppearanceSourceOwnerDefault ||
		appearance.OwnerDefaultThemeMode != settingsmodel.ThemeModeSystem ||
		appearance.Version != current.Appearance.Version {
		t.Fatalf("appearance slice 不符合 owner 默认值: %+v", appearance)
	}
}

func TestAssistantDeliveryPolicyReadsSubscriptionOwnerSettings(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	current, err := settingsmodel.NewDefault("account-policy", now)
	if err != nil {
		t.Fatalf("创建默认设置: %v", err)
	}
	start, err := settingsmodel.ParseTimeOfDay("22:30")
	if err != nil {
		t.Fatal(err)
	}
	end, err := settingsmodel.ParseTimeOfDay("07:00")
	if err != nil {
		t.Fatal(err)
	}
	current.Privacy.AssistantEnabled = false
	current.Notification.QuietHoursStart = &start
	current.Notification.QuietHoursEnd = &end
	current.Version = 9

	facade := settingsapp.NewUserSettingsQueryFacade(
		&fakeUserSettingsStore{current: current, found: true},
	)
	policy, err := facade.ResolveAssistantDeliveryPolicy(
		context.Background(),
		"account-policy",
	)
	if err != nil {
		t.Fatalf("解析助手投递策略: %v", err)
	}
	if policy.UserID != "account-policy" ||
		policy.AssistantEnabled ||
		policy.QuietHoursStart == nil ||
		*policy.QuietHoursStart != start ||
		policy.QuietHoursEnd == nil ||
		*policy.QuietHoursEnd != end ||
		policy.Version != 9 {
		t.Fatalf("助手投递策略切片漂移: %+v", policy)
	}
}

func TestAssistantDeliveryPolicyUsesCanonicalDefaultsBeforeFirstMutation(
	t *testing.T,
) {
	t.Parallel()
	facade := settingsapp.NewUserSettingsQueryFacade(
		&fakeUserSettingsStore{found: false},
	)
	policy, err := facade.ResolveAssistantDeliveryPolicy(
		context.Background(),
		"account-policy-default",
	)
	if err != nil {
		t.Fatalf("解析默认助手投递策略: %v", err)
	}
	if policy.UserID != "account-policy-default" ||
		!policy.AssistantEnabled ||
		policy.QuietHoursStart != nil ||
		policy.QuietHoursEnd != nil ||
		policy.Version != 0 {
		t.Fatalf("默认助手投递策略漂移: %+v", policy)
	}
}

func trustedAccountContext(accountID string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID: "UpdateNotificationSettings",
		RequestID:   "request-1",
		TraceID:     "trace-1",
		Actor: operation.ActorContext{
			AccountID: accountID,
		},
	})
}
