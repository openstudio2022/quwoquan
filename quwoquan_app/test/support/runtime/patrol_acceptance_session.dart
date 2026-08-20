library;

import 'package:quwoquan_app/runtime/auth/auth_session.dart';

/// Patrol 验收会话的身份契约与运行期交接状态。
///
/// 会话构造规则不需要 `package:patrol`，而生产 pubspec 已不含该插件。把规则放在
/// 这里，主 App 的 local_contract 与 test host 的 Patrol 目标就消费同一份实现，
/// 不会为「完整凭证才允许装配」再造第二真相源。
const String patrolRuntimeInstallId = String.fromEnvironment(
  'QWQ_PATROL_INSTALL_ID',
  defaultValue: 'patrol-local-remote-acceptance',
);

bool _patrolAppLaunchStarted = false;
AuthSessionState? _runnerInstalledAcceptanceSession;

/// Whether the Patrol target has already started mounting the production App.
bool get patrolAppLaunchStarted => _patrolAppLaunchStarted;

/// The session installed by the host-side runner, absent until it hands one off.
AuthSessionState? get patrolRunnerInstalledAcceptanceSession =>
    _runnerInstalledAcceptanceSession;

/// Records that the App launch has begun so late session installs fail closed.
void markPatrolAppLaunchStarted() {
  _patrolAppLaunchStarted = true;
}

/// Installs the protected actor opened by the host-side test-live runner.
///
/// This handoff is called only from the runner-owned ephemeral Patrol wrapper,
/// before the production App is mounted. It keeps bearer credentials out of
/// Flutter/Gradle command arguments and out of UAT reports.
AuthSessionState installPatrolAcceptanceSessionForRunner({
  required String accessToken,
  required String refreshToken,
  required String ownerId,
  required String personaId,
}) {
  if (_patrolAppLaunchStarted) {
    throw StateError(
      'Patrol acceptance session must be installed before App launch',
    );
  }
  final session = buildPatrolAcceptanceSession(
    accessToken: accessToken,
    refreshToken: refreshToken,
    ownerId: ownerId,
    personaId: personaId,
  );
  _runnerInstalledAcceptanceSession = session;
  return session;
}

/// Clears the runtime handoff between local-contract cases.
void resetPatrolAcceptanceSessionForTest() {
  if (_patrolAppLaunchStarted) {
    throw StateError('Patrol App has already launched');
  }
  _runnerInstalledAcceptanceSession = null;
}

AuthSessionState buildPatrolAcceptanceSession({
  required String accessToken,
  required String refreshToken,
  required String ownerId,
  required String personaId,
}) {
  if (accessToken.trim().isEmpty ||
      refreshToken.trim().isEmpty ||
      ownerId.trim().isEmpty ||
      personaId.trim().isEmpty) {
    throw StateError(
      'Patrol user_acceptance requires a complete access/refresh/owner/persona session',
    );
  }
  return AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: accessToken.trim(),
    refreshToken: refreshToken.trim(),
    ownerId: ownerId.trim(),
    activePersonaId: personaId.trim(),
    accountState: 'active',
    identityOrigin: 'patrol-user-acceptance',
    installId: 'patrol-user-acceptance-install',
  );
}

AuthSessionState buildPatrolAnonymousPublicVideoSession() =>
    const AuthSessionState(status: AuthSessionStatus.guest);

AuthSessionState buildPatrolUnauthenticatedAuthEntrySession() =>
    AuthSessionState(
      status: AuthSessionStatus.guest,
      // 此模式只去掉登录凭证，不能去掉安装身份。新鲜 iOS
      // Keychain 没有可回退的 persisted installId；空 deviceId 会让
      // OTP 验证成功后的 AccountSession Issue 在服务端 fail-closed。
      installId: patrolRuntimeInstallId,
    );
