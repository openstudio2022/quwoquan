// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/notification-privacy-settings/spec.md#gwt-001
// readiness_case: user_settings_settings_notifications_app_uat
/// Patrol UAT：一次性真实账号通过 production Remote 修改并回读通知设置。
///
/// 测试只操作真实页面，不读取 Provider、port 或本地缓存。运行器必须注入专用
/// disposable actor；测试结束前会通过同一 UI 恢复原值，任何 Remote 错误都直接失败。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_notifications_page.dart';

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
    'notification_settings_remote_update_reopen_and_restore',
    tags: const ['user-acceptance', 'user', 'settings', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      await launchPatrolAppOnce($);

      bool? originalValue;
      try {
        originalValue = await _openAndReadMarketingSetting($);
        await _setMarketingSetting($, !originalValue);

        await patrolGoTo($, AppRoutePaths.home);
        final persistedValue = await _openAndReadMarketingSetting($);
        expect(
          persistedValue,
          !originalValue,
          reason: '重新进入页面必须从 production Remote 回读已提交的通知设置',
        );
      } finally {
        if (originalValue != null) {
          await _openAndReadMarketingSetting($);
          await _setMarketingSetting($, originalValue);
          await patrolGoTo($, AppRoutePaths.home);
          final restoredValue = await _openAndReadMarketingSetting($);
          expect(
            restoredValue,
            originalValue,
            reason: '一次性账号的原通知设置必须通过同一 Remote UI 路径恢复',
          );
        }
      }
    },
  );
}

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

Future<bool> _openAndReadMarketingSetting(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.settingsNotifications);
  await $(
    find.byType(SettingsNotificationsPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  final switchFinder = _marketingSwitch();
  await $(switchFinder).waitUntilVisible(timeout: const Duration(seconds: 20));
  _expectNoSettingsFailure();
  return $.tester.widget<CupertinoSwitch>(switchFinder).value;
}

Future<void> _setMarketingSetting(
  PatrolIntegrationTester $,
  bool expectedValue,
) async {
  final switchFinder = _marketingSwitch();
  final current = $.tester.widget<CupertinoSwitch>(switchFinder).value;
  if (current != expectedValue) {
    await $(switchFinder).tap();
  }

  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoSettingsFailure();
    final candidates = switchFinder.evaluate();
    if (candidates.isNotEmpty &&
        $.tester.widget<CupertinoSwitch>(switchFinder).value == expectedValue) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('通知设置未收敛到 production Remote 返回的目标值: $expectedValue');
}

Finder _marketingSwitch() => find.descendant(
  of: find.ancestor(
    of: find.text(SettingsText.settingsEnableMarketing),
    matching: find.byType(SettingsInsetSwitchRow),
  ),
  matching: find.byType(CupertinoSwitch),
);

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
    reason: '通知设置命令失败必须阻断 UAT，不得继续验证乐观状态',
  );
}
