// ignore_for_file: depend_on_referenced_packages

library;

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/app_router_module.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/app_bootstrap.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/local_dev_https_trust.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show accountSessionLoginCommandWriterProvider;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
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
const String _patrolRuntimeInstallId = String.fromEnvironment(
  'QWQ_PATROL_INSTALL_ID',
  defaultValue: 'patrol-local-remote-acceptance',
);

Future<void>? _patrolAppLaunch;
Completer<void>? _runtimeAnonymousSessionReady;
String _runtimeAnonymousSessionFailure = '';
Future<void>? _runtimeAnonymousSessionLogin;

bool get _usesRuntimeAnonymousSession =>
    _patrolSessionMode == 'beta_local_anonymous_runtime' ||
    _patrolSessionMode == 'gamma_local_anonymous_runtime' ||
    _patrolSessionMode == 'prod_sim_anonymous_runtime';

bool get _usesAnonymousPublicVideoSession =>
    _patrolSessionMode == 'beta_local_anonymous_public_video' ||
    _patrolSessionMode == 'gamma_local_anonymous_public_video';

Completer<void> _runtimeAnonymousSessionGate() =>
    _runtimeAnonymousSessionReady ??= Completer<void>();

/// Starts the real App exactly once from the generated Patrol target.
///
/// Environment-specific test wiring is supplied by the caller so production
/// libraries never retain an Alpha fixture or Mock composition callback.
Future<void> launchPatrolAppOnce(
  PatrolIntegrationTester $, {
  List<Override> providerScopeOverrides = const <Override>[],
}) async {
  _patrolAppLaunch ??= runQuwoquanApp(
    autoCompleteStartupWelcomeForTest: true,
    providerScopeOverrides: [
      ...providerScopeOverrides,
      authSessionControllerProvider.overrideWith(
        _PatrolAuthSessionController.new,
      ),
    ],
  );
  await _patrolAppLaunch!;
  // 本地 Remote 冷启动会带来持续中的初始化任务，直接等待全局 settle
  // 容易把 Patrol user_acceptance 卡死在启动阶段。这里仅给首帧和首轮路由足够时间，
  // 后续由具体用例等待目标元素出现。
  await $.pump();
  await $.pump(const Duration(milliseconds: 300));
  await _awaitPatrolBootstrap($);
  if (_usesRuntimeAnonymousSession) {
    await _startRuntimeAnonymousSessionFromMountedApp();
    await _runtimeAnonymousSessionGate().future.timeout(
      const Duration(seconds: 30),
      onTimeout: () => throw StateError(
        'Patrol local Remote anonymous session did not become ready'
        '${_runtimeAnonymousSessionFailure.isEmpty ? '' : ': $_runtimeAnonymousSessionFailure'}',
      ),
    );
  }
  await $.pump(const Duration(seconds: 1));
}

Future<void> _awaitPatrolBootstrap(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 12));
  while (DateTime.now().isBefore(deadline)) {
    if (_tryReadPatrolRouter() != null) {
      return;
    }
    if (find.text(UITextConstants.startupRecoveryTitle).evaluate().isNotEmpty) {
      throw StateError(
        _patrolBootstrapFailureDescription(recoveryVisible: true),
      );
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  throw StateError(_patrolBootstrapFailureDescription());
}

String _patrolBootstrapFailureDescription({bool recoveryVisible = false}) {
  final routerError = appRouterLibraryLastLoadError;
  return 'Patrol bootstrap did not mount a Navigator '
      '(recoveryVisible=$recoveryVisible, '
      'routerLibraryLoaded=$isAppRouterLibraryLoaded, '
      'routerLoadAttempt=$appRouterLibraryLoadAttempt, '
      'routerLoadError=${routerError?.runtimeType})';
}

Future<void> _startRuntimeAnonymousSessionFromMountedApp() async {
  final navigators = find.byType(Navigator).evaluate();
  if (navigators.isEmpty) {
    throw StateError(
      'Patrol local Remote anonymous session requires a mounted Navigator',
    );
  }
  final container = ProviderScope.containerOf(navigators.first);
  // UAT 已绕过欢迎流程，不能依赖欢迎页时序间接打开 auth restore gate。
  // 这里先完成真实本地 HTTPS 信任安装，再驱动 production Remote composition
  // 发起匿名登录；不注入会话或假数据。
  await LocalDevHttpsTrust.installForCurrentRuntime();
  container.read(startupAuthRestoreGateProvider.notifier).open();
  container.read(authSessionControllerProvider);
  _runtimeAnonymousSessionLogin ??= _authenticateLocalRuntimeAnonymously(
    container,
  );
  unawaited(_runtimeAnonymousSessionLogin!);
}

Future<void> _authenticateLocalRuntimeAnonymously(
  ProviderContainer container,
) async {
  final gate = _runtimeAnonymousSessionGate();
  try {
    final result = await container
        .read(accountSessionLoginCommandWriterProvider)
        .loginAnonymous(
          LoginAnonymousCommand(
            installId: _patrolRuntimeInstallId,
            deviceFingerprintHash: _patrolRuntimeInstallId,
            platform: CloudRequestHeaders.platform(),
            appVersion: 'local-e2e',
          ),
        );
    final controller = container.read(authSessionControllerProvider.notifier);
    await controller.applyLoginGrant(result);
    final session = container.read(authSessionControllerProvider);
    if (!session.isAuthenticated || session.activeSubAccountId.trim().isEmpty) {
      throw StateError(
        'anonymous login did not install a complete authenticated session',
      );
    }
    if (!gate.isCompleted) {
      gate.complete();
    }
  } catch (error, stackTrace) {
    _runtimeAnonymousSessionFailure = _describeRuntimeAnonymousSessionFailure(
      error,
    );
    if (!gate.isCompleted) {
      // 仅暴露已结构化的错误码、状态和类别；原始 CloudException 不含网络根因，
      // 会使 Patrol 只报 APP.SYSTEM.unknown_error，无法判断是 TLS、网关还是鉴权。
      gate.completeError(
        StateError(
          'Patrol local Remote anonymous session failed: '
          '$_runtimeAnonymousSessionFailure, '
          'localHttpsTrustInstalled=${LocalDevHttpsTrust.isInstalled}',
        ),
        stackTrace,
      );
    }
  }
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
    final router = _tryReadPatrolRouter();
    if (router != null) {
      return router;
    }
    if (find.text(UITextConstants.startupRecoveryTitle).evaluate().isNotEmpty) {
      throw StateError(
        _patrolBootstrapFailureDescription(recoveryVisible: true),
      );
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  throw StateError(_patrolBootstrapFailureDescription());
}

GoRouter? _tryReadPatrolRouter() {
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
  return null;
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
  @override
  AuthSessionState build() {
    if (_usesRuntimeAnonymousSession) {
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
}

String _describeRuntimeAnonymousSessionFailure(Object error) {
  if (error is CloudException) {
    final code = error.code?.trim() ?? '';
    final status = error.statusCode?.toString() ?? '';
    return [
      if (code.isNotEmpty) 'code=$code',
      if (status.isNotEmpty) 'status=$status',
      'kind=${error.type.name}',
      if (error.cause != null) 'cause=${error.cause.runtimeType}',
    ].join(', ');
  }
  return 'kind=${error.runtimeType}';
}
