// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/notification-privacy-settings/spec.md#gwt-001
// readiness_case: user_settings_blocked_keywords_app_uat
/// Patrol UAT：一次性真实账号经 production Remote 新增、重入回读并清理屏蔽词。
///
/// 测试只操作真实页面；不读取 Provider、port 或本地缓存。运行器必须注入唯一关键词
/// 与 disposable actor 确认，任何 Remote 失败、未收敛或清理失败都直接阻断。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/blocked_keywords_page.dart';

import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _keyword = String.fromEnvironment('QWQ_BLOCKED_KEYWORD_UAT_VALUE');
const _disposableActorConfirmed = bool.fromEnvironment(
  'QWQ_USER_SETTINGS_DISPOSABLE_ACTOR_ACK',
);

void main() {
  patrolTest(
    'blocked_keywords_remote_add_reopen_remove_and_verify',
    tags: const ['user-acceptance', 'user', 'settings', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      await launchPatrolAppOnce($);

      var keywordMayExist = false;
      try {
        await _openAndWaitForRemote($);
        if (find.text(_keyword).evaluate().isNotEmpty) {
          keywordMayExist = true;
          await _removeKeyword($);
          await _reopenAndExpect($, present: false);
          keywordMayExist = false;
        }

        await $(find.text(ContentText.blockedKeywordsAdd)).tap();
        await $(find.byType(CupertinoTextField)).waitUntilVisible();
        await $(find.byType(CupertinoTextField)).enterText(_keyword);
        await $(find.text(CommunityText.done)).tap();
        keywordMayExist = true;
        await _waitForKeyword($, present: true);

        await _reopenAndExpect($, present: true);
        await _removeKeyword($);
        await _reopenAndExpect($, present: false);
        keywordMayExist = false;
      } finally {
        if (keywordMayExist) {
          await _openAndWaitForRemote($);
          if (find.text(_keyword).evaluate().isNotEmpty) {
            await _removeKeyword($);
            await _reopenAndExpect($, present: false);
          }
        }
      }
    },
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'BlockedKeywords UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError(
      'BlockedKeywords UAT requires an injected authenticated disposable actor',
    );
  }
  final gateway = Uri.tryParse(_gatewayBaseUrl);
  if (gateway == null || gateway.scheme != 'https' || gateway.host.isEmpty) {
    throw StateError(
      'BlockedKeywords UAT requires an absolute HTTPS CLOUD_GATEWAY_BASE_URL',
    );
  }
  final normalizedKeyword = _keyword.trim();
  if (normalizedKeyword.isEmpty ||
      normalizedKeyword.length > 64 ||
      normalizedKeyword != _keyword) {
    throw StateError(
      'BlockedKeywords UAT requires a unique 1..64 character '
      'QWQ_BLOCKED_KEYWORD_UAT_VALUE',
    );
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'BlockedKeywords UAT requires '
      'QWQ_USER_SETTINGS_DISPOSABLE_ACTOR_ACK=true',
    );
  }
}

Future<void> _openAndWaitForRemote(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.blockedKeywords);
  await $(
    find.byType(BlockedKeywordsPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  await $(
    find.text(ContentText.blockedKeywordsAdd),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  _expectNoFailure();
}

Future<void> _reopenAndExpect(
  PatrolIntegrationTester $, {
  required bool present,
}) async {
  await patrolGoTo($, AppRoutePaths.home);
  await _openAndWaitForRemote($);
  await _waitForKeyword($, present: present);
}

Future<void> _waitForKeyword(
  PatrolIntegrationTester $, {
  required bool present,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoFailure();
    final visible = find.text(_keyword).evaluate().isNotEmpty;
    if (visible == present) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail(
    'blocked keyword did not converge through production Remote: '
    'present=$present',
  );
}

Future<void> _removeKeyword(PatrolIntegrationTester $) async {
  final row = find.ancestor(
    of: find.text(_keyword),
    matching: find.byType(Row),
  );
  expect(row, findsOneWidget);
  final remove = find.descendant(
    of: row,
    matching: find.text(ContentText.blockedKeywordsRemove),
  );
  await $(remove).tap();
  await $(
    find.byType(CupertinoAlertDialog),
  ).waitUntilVisible(timeout: const Duration(seconds: 10));
  await $(find.text(ContentText.blockedKeywordsRemove).last).tap();
  await _waitForKeyword($, present: false);
}

void _expectNoFailure() {
  expect(
    find.byType(AppPageErrorState),
    findsNothing,
    reason: 'UserSettings query failure cannot masquerade as a keyword state',
  );
}
