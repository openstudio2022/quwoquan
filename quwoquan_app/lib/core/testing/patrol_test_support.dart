// ignore_for_file: depend_on_referenced_packages

library;

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/app_router_module.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/app/providers/welcome_state_provider.dart';
import 'package:quwoquan_app/app_bootstrap.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show accountSessionLoginCommandWriterProvider;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show LoginAnonymousCommand;

/// Patrol user_acceptance tests should only run under `patrol test`.
///
/// We guard them behind an explicit dart-define so `flutter test` can run the
/// regular test suite without trying to execute native Patrol flows.
const bool kRunPatrolT4 = bool.fromEnvironment('RUN_T4_PATROL');
const String kPatrolT4CurrentOwnerId = String.fromEnvironment(
  'APP_CURRENT_OWNER_ID',
);
const String kPatrolT4CurrentSubAccountId = String.fromEnvironment(
  'APP_CURRENT_SUB_ACCOUNT_ID',
);
const String _patrolSessionMode = String.fromEnvironment(
  'QWQ_PATROL_SESSION_MODE',
);
const String _patrolT4AuthToken = String.fromEnvironment('TEST_AUTH_TOKEN');
const String _patrolT4RefreshToken = String.fromEnvironment(
  'TEST_REFRESH_TOKEN',
);

bool _patrolAppStarted = false;
Completer<void>? _runtimeAnonymousSessionReady;

bool get _usesRuntimeAnonymousSession =>
    _patrolSessionMode == 'local_gamma_anonymous';

bool get _usesAnonymousPublicVideoSession =>
    _patrolSessionMode == 'beta_local_anonymous_public_video' ||
    _patrolSessionMode == 'gamma_local_anonymous_public_video';

Completer<void> _runtimeAnonymousSessionGate() =>
    _runtimeAnonymousSessionReady ??= Completer<void>();

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
  // 容易把 Patrol user_acceptance 卡死在启动阶段。这里仅给首帧和首轮路由足够时间，
  // 后续由具体用例等待目标元素出现。
  await $.pump();
  await $.pump(const Duration(milliseconds: 300));
  if (_usesRuntimeAnonymousSession) {
    _startRuntimeAnonymousSessionFromMountedApp();
    await _runtimeAnonymousSessionGate().future.timeout(
      const Duration(seconds: 15),
      onTimeout: () => throw StateError(
        'Patrol local Gamma anonymous session did not become ready',
      ),
    );
  }
  await $.pump(const Duration(seconds: 1));
}

void _startRuntimeAnonymousSessionFromMountedApp() {
  final navigators = find.byType(Navigator).evaluate();
  if (navigators.isEmpty) {
    throw StateError(
      'Patrol local Gamma anonymous session requires a mounted Navigator',
    );
  }
  final container = ProviderScope.containerOf(navigators.first);
  // UAT 已绕过欢迎流程，不能依赖欢迎页时序间接打开 auth restore gate。
  // 这里只驱动真实 production Remote composition 发起匿名登录，不注入会话或假数据。
  container.read(startupAuthRestoreGateProvider.notifier).open();
  container.read(authSessionControllerProvider);
}

Future<void> patrolGoTo(
  PatrolIntegrationTester $,
  String location, {
  Duration timeout = const Duration(seconds: 45),
}) async {
  final router = await _waitForPatrolRouter($, timeout: timeout);
  router.go(location);
  await $.pump();
  await $.pump(const Duration(milliseconds: 300));
  await $.pump(const Duration(seconds: 1));
}

Future<GoRouter> _waitForPatrolRouter(
  PatrolIntegrationTester $, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    for (final element in find.byType(Navigator).evaluate()) {
      try {
        return GoRouter.of(element);
      } catch (_) {
        try {
          return ProviderScope.containerOf(
            element,
          ).read(deferredAppRouterProvider);
        } catch (_) {
          continue;
        }
      }
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  throw StateError('GoRouter did not become available within $timeout');
}

final class _PatrolWelcomeCompletedNotifier extends WelcomeCompletedNotifier {
  @override
  bool build() => true;
}

AuthSessionState buildPatrolAcceptanceSession({
  required String accessToken,
  required String refreshToken,
  required String ownerId,
  required String subAccountId,
}) {
  if (accessToken.trim().isEmpty ||
      refreshToken.trim().isEmpty ||
      ownerId.trim().isEmpty ||
      subAccountId.trim().isEmpty) {
    throw StateError(
      'Patrol user_acceptance requires a complete access/refresh/owner/persona session',
    );
  }
  return AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: accessToken.trim(),
    refreshToken: refreshToken.trim(),
    ownerId: ownerId.trim(),
    activeSubAccountId: subAccountId.trim(),
    accountState: 'active',
    identityOrigin: 'patrol-user-acceptance',
    installId: 'patrol-user-acceptance-install',
  );
}

AuthSessionState buildPatrolAnonymousPublicVideoSession() =>
    const AuthSessionState(status: AuthSessionStatus.guest);

final class _PatrolAuthSessionController extends AuthSessionController {
  bool _runtimeAnonymousLoginStarted = false;

  @override
  AuthSessionState build() {
    if (_usesRuntimeAnonymousSession) {
      final startupPrerequisitesReady = ref.watch(
        startupAuthRestoreGateProvider,
      );
      if (startupPrerequisitesReady && !_runtimeAnonymousLoginStarted) {
        _runtimeAnonymousLoginStarted = true;
        unawaited(_authenticateLocalGammaAnonymously());
      }
      return const AuthSessionState.restoring();
    }
    if (_usesAnonymousPublicVideoSession) {
      return buildPatrolAnonymousPublicVideoSession();
    }
    return buildPatrolAcceptanceSession(
      accessToken: _patrolT4AuthToken,
      refreshToken: _patrolT4RefreshToken,
      ownerId: kPatrolT4CurrentOwnerId,
      subAccountId: kPatrolT4CurrentSubAccountId,
    );
  }

  Future<void> _authenticateLocalGammaAnonymously() async {
    final gate = _runtimeAnonymousSessionGate();
    try {
      final result = await ref
          .read(accountSessionLoginCommandWriterProvider)
          .loginAnonymous(
            LoginAnonymousCommand(
              installId: 'patrol-local-gamma-two-province',
              deviceFingerprintHash: 'patrol-local-gamma-two-province',
              platform: CloudRequestHeaders.platform(),
              appVersion: 'local-e2e',
            ),
          );
      final subAccountId = result.activeSub?.subAccountId.trim() ?? '';
      final session = buildPatrolAcceptanceSession(
        accessToken: result.accessToken,
        refreshToken: result.refreshToken,
        ownerId: result.ownerId,
        subAccountId: subAccountId,
      );
      if (ref.mounted) {
        state = session;
      }
      if (!gate.isCompleted) {
        gate.complete();
      }
    } catch (error, stackTrace) {
      if (ref.mounted) {
        state = AuthSessionState(
          status: AuthSessionStatus.guest,
          errorMessage: 'Patrol local Gamma anonymous login failed',
        );
      }
      if (!gate.isCompleted) {
        gate.completeError(error, stackTrace);
      }
    }
  }
}
