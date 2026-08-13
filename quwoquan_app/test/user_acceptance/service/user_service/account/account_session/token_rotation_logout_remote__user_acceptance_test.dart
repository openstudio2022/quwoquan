// readiness_case: account_session_token_rotation_app_uat
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/auth-token-lifecycle/spec.md#gwt-002
/// disposable actor 先经 production Remote 轮换 refresh token 并证明旧 token 失效；
/// production App 再从设置页执行 hard logout，只有新 token 也被服务端拒绝且 UI 进入
/// LoginPage 才算完成。测试结束后以公开 CloseAccount command 清理账号。
///
/// 当前 Gamma 尚无同一 candidate Android+iPhone ResultBundle，因此本 source runner
/// 不登记 readiness_case，也不把本地编译或单设备执行冒充商用准出。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/presentation/login_page.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _disposableActorConfirmed = bool.fromEnvironment(
  'QWQ_ACCOUNT_SESSION_DISPOSABLE_ACTOR_ACK',
);

void main() {
  patrolTest(
    'account_session_rotates_then_hard_logout_revokes_the_remote_session',
    tags: const ['user-acceptance', 'user', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      UserApiContractHarness? harness;

      try {
        harness = await UserApiContractHarness.create();
        final original = await harness.loginDisposableAccount(
          'token-rotation-$suffix',
        );
        final personaId = original.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError('Disposable User actor requires an active persona');
        }

        final rotated = await harness.accountSessions.refreshToken(
          RefreshTokenCommand(refreshToken: original.refreshToken),
        );
        expect(rotated.accessToken, isNotEmpty);
        expect(rotated.refreshToken, isNotEmpty);
        expect(rotated.refreshToken, isNot(original.refreshToken));
        await expectLater(
          harness.accountSessions.refreshToken(
            RefreshTokenCommand(refreshToken: original.refreshToken),
          ),
          throwsA(isA<CloudException>()),
        );

        installPatrolAcceptanceSessionForRunner(
          accessToken: rotated.accessToken,
          refreshToken: rotated.refreshToken,
          ownerId: original.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);
        await patrolGoTo($, AppRoutePaths.settings);
        await $(find.byType(SettingsPage)).waitUntilVisible();

        final logoutEntry = find.text(FoundationText.logout);
        await $.tester.ensureVisible(logoutEntry);
        await $.tester.tap(logoutEntry);
        await $.pumpAndSettle();
        expect(find.text(FoundationText.logoutDialogTitle), findsOneWidget);
        final hardLogout = find.descendant(
          of: find.byType(CupertinoAlertDialog),
          matching: find.text(FoundationText.logoutDialogHardAction),
        );
        await $.tester.tap(hardLogout);
        await _waitForLoginPage($);

        await expectLater(
          harness.accountSessions.refreshToken(
            RefreshTokenCommand(refreshToken: rotated.refreshToken),
          ),
          throwsA(isA<CloudException>()),
        );
      } finally {
        if (harness != null) {
          try {
            await harness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'account-session-cleanup-$suffix',
              ),
            );
          } finally {
            await harness.close();
          }
        }
      }
    },
  );
}

Future<void> _waitForLoginPage(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(LoginPage).evaluate().isNotEmpty) {
      expect(
        find.byKey(const ValueKey<String>('loginOneTapPrimary')),
        findsOneWidget,
      );
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('hard logout did not enter the production LoginPage');
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'AccountSession UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError('AccountSession UAT installs its own disposable session');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError('AccountSession UAT requires absolute HTTPS gateways');
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError('AccountSession UAT requires one App/API gateway');
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'Set QWQ_ACCOUNT_SESSION_DISPOSABLE_ACTOR_ACK=true only when account '
      'closure cleanup is permitted',
    );
  }
}

bool _isAbsoluteHttps(Uri? value) =>
    value != null &&
    value.isAbsolute &&
    value.scheme == 'https' &&
    value.host.isNotEmpty;

String _normalizedGateway(Uri value) {
  final path = value.path.replaceFirst(RegExp(r'/+$'), '');
  return value.replace(path: path, query: null, fragment: null).toString();
}
