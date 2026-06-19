// ignore_for_file: depend_on_referenced_packages

library;

import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/providers/welcome_state_provider.dart';
import 'package:quwoquan_app/app_bootstrap.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';

/// T4 Patrol tests should only run under `patrol test`.
///
/// We guard them behind an explicit dart-define so `flutter test` can run the
/// regular test suite without trying to execute native Patrol flows.
const bool kRunPatrolT4 = bool.fromEnvironment('RUN_T4_PATROL');
const String kPatrolT4CurrentUserId = String.fromEnvironment(
  'APP_CURRENT_USER_ID',
  defaultValue: 'fixture_user_current',
);
const String _patrolT4AuthToken = String.fromEnvironment(
  'TEST_AUTH_TOKEN',
  defaultValue: 'local-t4-token',
);

bool _patrolAppStarted = false;

Future<void> launchPatrolAppOnce(PatrolIntegrationTester $) async {
  if (!_patrolAppStarted) {
    _patrolAppStarted = true;
    await runQuwoquanApp(
      providerScopeOverrides: [
        welcomeCompletedProvider.overrideWith(
          _PatrolWelcomeCompletedNotifier.new,
        ),
        authSessionControllerProvider.overrideWith(
          _PatrolAuthSessionController.new,
        ),
      ],
    );
  }
  // gamma 远端冷启动会带来持续中的初始化任务，直接等待全局 settle
  // 容易把 T4 卡死在启动阶段。这里仅给首帧和首轮路由足够时间，
  // 后续由具体用例等待目标元素出现。
  await $.pump();
  await $.pump(const Duration(milliseconds: 300));
  await $.pump(const Duration(seconds: 1));
}

final class _PatrolWelcomeCompletedNotifier extends WelcomeCompletedNotifier {
  @override
  bool build() => true;
}

final class _PatrolAuthSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: _patrolT4AuthToken.isEmpty
        ? 'local-t4-token'
        : _patrolT4AuthToken,
    refreshToken: 'local-t4-refresh-token',
    ownerId: kPatrolT4CurrentUserId,
    activeSubAccountId: kPatrolT4CurrentUserId,
    accountState: 'active',
    identityOrigin: 'patrol-t4',
    installId: 'patrol-t4-install',
  );
}
