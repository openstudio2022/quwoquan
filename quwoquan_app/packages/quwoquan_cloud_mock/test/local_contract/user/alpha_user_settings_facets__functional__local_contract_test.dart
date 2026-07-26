import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  test(
    'alpha UserSettings preserves every section and same-value no-op',
    () async {
      var tick = 0;
      final facet = AlphaUserSettingsFacet(
        initialUpdatedAt: DateTime.utc(2026, 7, 20),
        now: () => DateTime.utc(2026, 7, 20, 0, 0, ++tick),
      );

      final notificationCommand = UpdateNotificationSettingsCommand(
        enablePush: false,
        enableMarketing: true,
        quietHoursStart: NullableSettingMutation<QuietHoursTime>.set(
          QuietHoursTime(hour: 22, minute: 30),
        ),
        quietHoursEnd: NullableSettingMutation<QuietHoursTime>.set(
          QuietHoursTime(hour: 7, minute: 15),
        ),
      );
      final notificationWrite = await facet.updateNotificationSettings(
        notificationCommand,
      );
      final notificationReplay = await facet.updateNotificationSettings(
        notificationCommand,
      );
      final notification = await facet.getNotificationSettings();
      expect(notificationWrite.idempotentReplay, isFalse);
      expect(notificationReplay.idempotentReplay, isTrue);
      expect(notificationReplay.version, notificationWrite.version);
      expect(notification.enablePush, isFalse);
      expect(notification.enableMarketing, isTrue);
      expect(
        notification.quietHoursStart,
        QuietHoursTime(hour: 22, minute: 30),
      );
      expect(notification.quietHoursEnd, QuietHoursTime(hour: 7, minute: 15));
      expect(notification.version, notificationWrite.version);

      final privacyCommand = UpdatePrivacySettingsCommand(
        allowStrangerMsg: false,
        profileVisibility: ProfileVisibility.friends,
        blockedKeywords: const <String>['alpha', ' beta ', 'alpha'],
        assistantEnabled: false,
      );
      final privacyWrite = await facet.updatePrivacySettings(privacyCommand);
      final privacyReplay = await facet.updatePrivacySettings(privacyCommand);
      final privacy = await facet.getPrivacySettings();
      expect(privacyWrite.idempotentReplay, isFalse);
      expect(privacyReplay.idempotentReplay, isTrue);
      expect(privacyReplay.version, privacyWrite.version);
      expect(privacy.allowStrangerMsg, isFalse);
      expect(privacy.profileVisibility, ProfileVisibility.friends);
      expect(privacy.contentLanguage, isNull);
      expect(privacy.feedPreference, isNull);
      expect(privacy.assistantEnabled, isFalse);
      expect(privacy.blockedKeywords, <String>['alpha', 'beta']);

      final callCommand = UpdateCallSettingsCommand(
        defaultIncomingCallRingtoneId:
            NullableSettingMutation<OfficialRingtoneId>.set(
              OfficialRingtoneId('official.classic'),
            ),
        allowCallerRingtoneOverride: false,
        enableCallVibration: false,
        enableGroupCallRing: false,
      );
      final callWrite = await facet.updateCallSettings(callCommand);
      final callReplay = await facet.updateCallSettings(callCommand);
      final call = await facet.getCallSettings();
      expect(callWrite.idempotentReplay, isFalse);
      expect(callReplay.idempotentReplay, isTrue);
      expect(callReplay.version, callWrite.version);
      expect(call.defaultIncomingCallRingtoneId?.wireValue, 'official.classic');
      expect(call.allowCallerRingtoneOverride, isFalse);
      expect(call.enableCallVibration, isFalse);
      expect(call.enableGroupCallRing, isFalse);

      final clearCallWrite = await facet.updateCallSettings(
        const UpdateCallSettingsCommand(
          defaultIncomingCallRingtoneId:
              NullableSettingMutation<OfficialRingtoneId>.clear(),
        ),
      );
      final clearCallReplay = await facet.updateCallSettings(
        const UpdateCallSettingsCommand(
          defaultIncomingCallRingtoneId:
              NullableSettingMutation<OfficialRingtoneId>.clear(),
        ),
      );
      expect(clearCallWrite.idempotentReplay, isFalse);
      expect(clearCallReplay.idempotentReplay, isTrue);
      expect(
        (await facet.getCallSettings()).defaultIncomingCallRingtoneId,
        isNull,
      );
    },
  );

  test(
    'alpha appearance follows owner/override scopes with no-op versions',
    () async {
      var tick = 0;
      final facet = AlphaUserSettingsFacet(
        initialUpdatedAt: DateTime.utc(2026, 7, 20),
        now: () => DateTime.utc(2026, 7, 20, 0, 0, ++tick),
      );

      const overrideCommand = UpdateAppearanceSettingsCommand(
        themeMode: ThemeModeSetting.dark,
        fontSizePreset: FontSizePreset.lg,
        applyScope: AppearanceApplyScope.currentSubAccount,
      );
      final override = await facet.updateAppearanceSettings(overrideCommand);
      final overrideReplay = await facet.updateAppearanceSettings(
        overrideCommand,
      );
      expect(override.source, AppearanceSource.subOverride);
      expect(override.themeMode, ThemeModeSetting.dark);
      expect(override.fontSizePreset, FontSizePreset.lg);
      expect(override.hasSubAccountOverride, isTrue);
      expect(overrideReplay.version, override.version);
      expect(overrideReplay.updatedAt, override.updatedAt);

      const inheritCommand = UpdateAppearanceSettingsCommand(
        themeMode: ThemeModeSetting.system,
        fontSizePreset: FontSizePreset.md,
        applyScope: AppearanceApplyScope.inheritOwnerDefault,
      );
      final inherited = await facet.updateAppearanceSettings(inheritCommand);
      final inheritReplay = await facet.updateAppearanceSettings(
        inheritCommand,
      );
      expect(inherited.source, AppearanceSource.ownerDefault);
      expect(inherited.themeMode, ThemeModeSetting.system);
      expect(inherited.fontSizePreset, FontSizePreset.md);
      expect(inherited.hasSubAccountOverride, isFalse);
      expect(inheritReplay.version, inherited.version);
      expect(inheritReplay.updatedAt, inherited.updatedAt);

      const ownerCommand = UpdateAppearanceSettingsCommand(
        themeMode: ThemeModeSetting.light,
        fontSizePreset: FontSizePreset.xl,
        applyScope: AppearanceApplyScope.allAccounts,
      );
      final owner = await facet.updateAppearanceSettings(ownerCommand);
      final ownerReplay = await facet.updateAppearanceSettings(ownerCommand);
      expect(owner.source, AppearanceSource.ownerDefault);
      expect(owner.themeMode, ThemeModeSetting.light);
      expect(owner.fontSizePreset, FontSizePreset.xl);
      expect(owner.ownerDefaultThemeMode, ThemeModeSetting.light);
      expect(owner.ownerDefaultFontSizePreset, FontSizePreset.xl);
      expect(owner.hasSubAccountOverride, isFalse);
      expect(ownerReplay.version, owner.version);
      expect(ownerReplay.updatedAt, owner.updatedAt);
    },
  );
}
