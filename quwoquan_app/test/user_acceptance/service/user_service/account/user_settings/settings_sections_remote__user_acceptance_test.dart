// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/notification-privacy-settings/spec.md#gwt-001
// readiness_case: user_settings_settings_privacy_app_uat
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/settings-audit/spec.md#gwt-001
// readiness_case: user_settings_settings_calls_app_uat
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/appearance-accessibility-settings/spec.md#gwt-001
// readiness_case: user_settings_settings_dark_mode_app_uat
/// Patrol UAT：一次性真实账号通过 production Remote 修改、重入回读并恢复设置。
///
/// 测试只操作真实页面，不读取 Provider、port 或本地缓存。任何 Remote 错误、同步失败
/// 或未收敛状态都会阻断；Android 与 iPhone 必须分别生成同一 candidate 的结果回执。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/settings/appearance_settings_models.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_calls_page.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_dark_mode_page.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_privacy_page.dart';

import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _disposableActorConfirmed = bool.fromEnvironment(
  'QWQ_USER_SETTINGS_DISPOSABLE_ACTOR_ACK',
);

void main() {
  patrolTest(
    'privacy_settings_remote_update_reopen_and_restore',
    tags: const ['user-acceptance', 'user', 'settings', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: _patrolConfig,
    ($) async {
      _validateRuntimeInputs();
      await launchPatrolAppOnce($);

      bool? originalValue;
      try {
        originalValue = await _openAndReadSwitch(
          $,
          route: AppRoutePaths.settingsPrivacy,
          pageType: SettingsPrivacyPage,
          label: SettingsText.settingsAllowStrangerMessage,
        );
        await _setSwitch(
          $,
          SettingsText.settingsAllowStrangerMessage,
          !originalValue,
        );

        await patrolGoTo($, AppRoutePaths.home);
        final persistedValue = await _openAndReadSwitch(
          $,
          route: AppRoutePaths.settingsPrivacy,
          pageType: SettingsPrivacyPage,
          label: SettingsText.settingsAllowStrangerMessage,
        );
        expect(
          persistedValue,
          !originalValue,
          reason: '重新进入隐私页必须从 production Remote 回读命令结果',
        );
      } finally {
        if (originalValue != null) {
          await _restoreSwitch(
            $,
            route: AppRoutePaths.settingsPrivacy,
            pageType: SettingsPrivacyPage,
            label: SettingsText.settingsAllowStrangerMessage,
            originalValue: originalValue,
          );
        }
      }
    },
  );

  patrolTest(
    'call_settings_remote_update_reopen_and_restore',
    tags: const ['user-acceptance', 'user', 'settings', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: _patrolConfig,
    ($) async {
      _validateRuntimeInputs();
      await launchPatrolAppOnce($);

      bool? originalValue;
      try {
        originalValue = await _openAndReadSwitch(
          $,
          route: AppRoutePaths.settingsCalls,
          pageType: SettingsCallsPage,
          label: SettingsText.settingsEnableCallVibration,
        );
        await _setSwitch(
          $,
          SettingsText.settingsEnableCallVibration,
          !originalValue,
        );

        await patrolGoTo($, AppRoutePaths.home);
        final persistedValue = await _openAndReadSwitch(
          $,
          route: AppRoutePaths.settingsCalls,
          pageType: SettingsCallsPage,
          label: SettingsText.settingsEnableCallVibration,
        );
        expect(
          persistedValue,
          !originalValue,
          reason: '重新进入通话页必须从 production Remote 回读命令结果',
        );
      } finally {
        if (originalValue != null) {
          await _restoreSwitch(
            $,
            route: AppRoutePaths.settingsCalls,
            pageType: SettingsCallsPage,
            label: SettingsText.settingsEnableCallVibration,
            originalValue: originalValue,
          );
        }
      }
    },
  );

  patrolTest(
    'appearance_settings_remote_update_reopen_and_restore',
    tags: const ['user-acceptance', 'user', 'settings', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: _patrolConfig,
    ($) async {
      _validateRuntimeInputs();
      await launchPatrolAppOnce($);

      AppearanceFontSizePreset? originalPreset;
      try {
        originalPreset = await _openAndReadFontPreset($);
        final targetPreset = originalPreset == AppearanceFontSizePreset.lg
            ? AppearanceFontSizePreset.sm
            : AppearanceFontSizePreset.lg;
        await _setFontPreset($, targetPreset);

        await patrolGoTo($, AppRoutePaths.home);
        final persistedPreset = await _openAndReadFontPreset($);
        expect(
          persistedPreset,
          targetPreset,
          reason: '重新进入外观页必须从 production Remote 回读字号设置',
        );
      } finally {
        if (originalPreset != null) {
          await _openAndReadFontPreset($);
          await _setFontPreset($, originalPreset);
          await patrolGoTo($, AppRoutePaths.home);
          final restoredPreset = await _openAndReadFontPreset($);
          expect(
            restoredPreset,
            originalPreset,
            reason: '一次性账号的原字号设置必须通过同一 Remote UI 路径恢复',
          );
        }
      }
    },
  );
}

const _patrolConfig = PatrolTesterConfig(
  visibleTimeout: Duration(seconds: 20),
  printLogs: true,
);

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'UserSettings UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError(
      'UserSettings UAT requires an injected authenticated disposable actor; '
      'anonymous Patrol session modes are not evidence',
    );
  }
  final gateway = Uri.tryParse(_gatewayBaseUrl);
  if (gateway == null || gateway.scheme != 'https' || gateway.host.isEmpty) {
    throw StateError(
      'UserSettings UAT requires an absolute HTTPS CLOUD_GATEWAY_BASE_URL',
    );
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'UserSettings UAT requires QWQ_USER_SETTINGS_DISPOSABLE_ACTOR_ACK=true',
    );
  }
}

Future<bool> _openAndReadSwitch(
  PatrolIntegrationTester $, {
  required String route,
  required Type pageType,
  required String label,
}) async {
  await patrolGoTo($, route);
  await $(
    find.byType(pageType),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  final switchFinder = _switchForLabel(label);
  await _waitForSettingsControl($, switchFinder);
  return $.tester.widget<CupertinoSwitch>(switchFinder).value;
}

Future<void> _setSwitch(
  PatrolIntegrationTester $,
  String label,
  bool expectedValue,
) async {
  final switchFinder = _switchForLabel(label);
  final current = $.tester.widget<CupertinoSwitch>(switchFinder).value;
  if (current != expectedValue) {
    await $(switchFinder).tap();
  }
  await _waitForValue(
    $,
    currentValue: () => $.tester.widget<CupertinoSwitch>(switchFinder).value,
    expectedValue: expectedValue,
    description: label,
  );
}

Future<void> _restoreSwitch(
  PatrolIntegrationTester $, {
  required String route,
  required Type pageType,
  required String label,
  required bool originalValue,
}) async {
  await _openAndReadSwitch($, route: route, pageType: pageType, label: label);
  await _setSwitch($, label, originalValue);
  await patrolGoTo($, AppRoutePaths.home);
  final restoredValue = await _openAndReadSwitch(
    $,
    route: route,
    pageType: pageType,
    label: label,
  );
  expect(
    restoredValue,
    originalValue,
    reason: '一次性账号的原设置必须通过同一 Remote UI 路径恢复: $label',
  );
}

Finder _switchForLabel(String label) => find.descendant(
  of: find.ancestor(
    of: find.text(label),
    matching: find.byType(SettingsInsetSwitchRow),
  ),
  matching: find.byType(CupertinoSwitch),
);

Future<AppearanceFontSizePreset> _openAndReadFontPreset(
  PatrolIntegrationTester $,
) async {
  await patrolGoTo($, AppRoutePaths.settingsDarkMode);
  await $(
    find.byType(SettingsDarkModePage),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  _expectNoSettingsFailure();
  for (final preset in AppearanceFontSizePreset.values) {
    final finder = find.byKey(ValueKey<AppearanceFontSizePreset>(preset));
    await $.tester.scrollUntilVisible(
      finder,
      160,
      scrollable: find.byType(Scrollable).last,
    );
    await $.pump();
    _expectNoSettingsFailure();
    if ($.tester.widget<SettingsInsetChoiceRow>(finder).isSelected) {
      return preset;
    }
  }
  throw StateError('AppearanceSettings Remote snapshot has no selected preset');
}

Future<void> _setFontPreset(
  PatrolIntegrationTester $,
  AppearanceFontSizePreset expectedPreset,
) async {
  final finder = find.byKey(ValueKey<AppearanceFontSizePreset>(expectedPreset));
  await $.tester.scrollUntilVisible(
    finder,
    160,
    scrollable: find.byType(Scrollable).last,
  );
  if (!$.tester.widget<SettingsInsetChoiceRow>(finder).isSelected) {
    await $(finder).tap();
  }
  await _waitForValue(
    $,
    currentValue: () =>
        $.tester.widget<SettingsInsetChoiceRow>(finder).isSelected,
    expectedValue: true,
    description: expectedPreset.name,
  );
}

Future<void> _waitForSettingsControl(
  PatrolIntegrationTester $,
  Finder finder,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoSettingsFailure();
    if (finder.evaluate().isNotEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('设置页未从 production Remote 加载目标控件');
}

Future<void> _waitForValue<T>(
  PatrolIntegrationTester $, {
  required T Function() currentValue,
  required T expectedValue,
  required String description,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoSettingsFailure();
    if (currentValue() == expectedValue) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('设置未收敛到 production Remote 目标值: $description=$expectedValue');
}

void _expectNoSettingsFailure() {
  expect(
    find.byType(AppPageErrorState),
    findsNothing,
    reason:
        'UserSettings Remote failure cannot masquerade as a persisted value',
  );
  expect(
    find.byType(CupertinoAlertDialog),
    findsNothing,
    reason: 'UserSettings command failure must block UAT',
  );
  expect(
    find.text(SettingsText.settingsSyncFailed),
    findsNothing,
    reason:
        'Appearance pending-sync failure cannot count as Remote persistence',
  );
}
