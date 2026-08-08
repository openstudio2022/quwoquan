// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/settings-audit/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/appearance-accessibility-settings/spec.md#gwt-001
// readiness_case: user_settings_get_notification_settings_app_api
// readiness_case: user_settings_update_notification_settings_app_api
// readiness_case: user_settings_get_call_settings_app_api
// readiness_case: user_settings_update_call_settings_app_api
// readiness_case: user_settings_get_appearance_settings_app_api
// readiness_case: user_settings_update_appearance_settings_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  late UserApiContractHarness harness;

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
    await harness.loginDisposableAccount('settings');
  });
  tearDownAll(() => harness.close());

  test('UserSettings notification/call roundtrip 与稳定命令回执', () async {
    final notification = await harness.settingsReader.getNotificationSettings();
    expect(notification.userId, harness.session.ownerId);
    expect(notification.updatedAt, isNotNull);

    final originalMarketing = notification.enableMarketing;
    final notificationReceipt = await harness.settingsCommands
        .updateNotificationSettings(
          UpdateNotificationSettingsCommand(
            enableMarketing: !originalMarketing,
          ),
        );
    expect(notificationReceipt.userId, harness.session.ownerId);
    expect(notificationReceipt.version, greaterThanOrEqualTo(1));

    final notificationReadback = await harness.settingsReader
        .getNotificationSettings();
    expect(notificationReadback.enableMarketing, !originalMarketing);

    final call = await harness.settingsReader.getCallSettings();
    expect(call.userId, harness.session.ownerId);
    expect(call.updatedAt, isNotNull);

    final originalVibration = call.enableCallVibration;
    final callReceipt = await harness.settingsCommands.updateCallSettings(
      UpdateCallSettingsCommand(enableCallVibration: !originalVibration),
    );
    expect(callReceipt.userId, harness.session.ownerId);
    expect(callReceipt.version, greaterThanOrEqualTo(1));
    final callReadback = await harness.settingsReader.getCallSettings();
    expect(callReadback.enableCallVibration, !originalVibration);

    await harness.settingsCommands.updateNotificationSettings(
      UpdateNotificationSettingsCommand(enableMarketing: originalMarketing),
    );
    await harness.settingsCommands.updateCallSettings(
      UpdateCallSettingsCommand(enableCallVibration: originalVibration),
    );
    final telemetryEvents = await harness.telemetry.waitForEvents(
      minimumCount: 1,
    );
    expect(telemetryEvents.every((event) => event.succeeded), isTrue);
  });

  test('AppearanceSettings 通过 production Remote 往返并恢复原值', () async {
    final original = await harness.settingsReader.getAppearanceSettings();
    expect(original.version, greaterThanOrEqualTo(1));

    final targetTheme = original.themeMode == ThemeModeSetting.dark
        ? ThemeModeSetting.light
        : ThemeModeSetting.dark;
    final applyScope = original.hasPersonaOverride
        ? AppearanceApplyScope.currentPersona
        : AppearanceApplyScope.allAccounts;

    try {
      final updated = await harness.settingsCommands.updateAppearanceSettings(
        UpdateAppearanceSettingsCommand(
          themeMode: targetTheme,
          fontSizePreset: original.fontSizePreset,
          applyScope: applyScope,
        ),
      );
      expect(updated.themeMode, targetTheme);
      expect(updated.version, greaterThan(original.version));

      final readback = await harness.settingsReader.getAppearanceSettings();
      expect(readback.themeMode, targetTheme);
      expect(readback.fontSizePreset, original.fontSizePreset);
      expect(readback.version, updated.version);
    } finally {
      await harness.settingsCommands.updateAppearanceSettings(
        UpdateAppearanceSettingsCommand(
          themeMode: original.themeMode,
          fontSizePreset: original.fontSizePreset,
          applyScope: applyScope,
        ),
      );
    }

    final restored = await harness.settingsReader.getAppearanceSettings();
    expect(restored.themeMode, original.themeMode);
    expect(restored.fontSizePreset, original.fontSizePreset);
    expect(restored.hasPersonaOverride, original.hasPersonaOverride);
  });
}
