// ignore_for_file: depend_on_referenced_packages

library;

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/di/navigation/app_router_module.dart';
import 'package:quwoquan_app/runtime/shell/state/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_bootstrap.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart'
    show accountSessionLoginCommandWriterProvider;
import 'package:quwoquan_app/runtime/transport/cloud_request_headers.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AuthSessionGrant, LoginAnonymousCommand;

import '../patrol_acceptance_session.dart';

// 会话身份契约由 patrol_acceptance_session.dart 拥有，这里只做转发，
// 让既有 UAT 的单一 import 不变。
export '../patrol_acceptance_session.dart';

/// Patrol user_acceptance tests should only run under `patrol test`.
///
/// We guard them behind an explicit dart-define so `flutter test` can run the
/// regular test suite without trying to execute native Patrol flows.
const bool kRunPatrolAcceptance = bool.fromEnvironment('RUN_PATROL_ACCEPTANCE');
const String kPatrolAcceptanceCurrentOwnerId = String.fromEnvironment(
  'APP_CURRENT_OWNER_ID',
);
const String kPatrolAcceptanceCurrentPersonaId = String.fromEnvironment(
  'APP_CURRENT_PERSONA_ID',
);
const String _patrolSessionMode = String.fromEnvironment(
  'QWQ_PATROL_SESSION_MODE',
);
const String _patrolAcceptanceAuthToken = String.fromEnvironment(
  'TEST_AUTH_TOKEN',
);
const String _patrolAcceptanceRefreshToken = String.fromEnvironment(
  'TEST_REFRESH_TOKEN',
);
const int _patrolAnonymousLoginSetupAttempts = 3;

Future<void>? _patrolAppLaunch;
Completer<void>? _runtimeAnonymousSessionReady;
String _runtimeAnonymousSessionFailure = '';
Future<void>? _runtimeAnonymousSessionLogin;

bool get _usesRuntimeAnonymousSession =>
    _patrolSessionMode == 'runtime_anonymous_session';

bool get _usesAnonymousPublicVideoSession =>
    _patrolSessionMode == 'anonymous_public_video_session';

bool get _usesUnauthenticatedAuthEntry =>
    _patrolSessionMode == 'unauthenticated_auth_entry';

Completer<void> _runtimeAnonymousSessionGate() =>
    _runtimeAnonymousSessionReady ??= Completer<void>();

/// Starts the real App exactly once from the generated Patrol target.
///
/// 仅认证会话控制器允许测试装配；业务 Query/Command 始终使用 production
/// Remote composition，调用方不能注入业务 Provider double。
Future<void> launchPatrolAppOnce(PatrolIntegrationTester $) async {
  markPatrolAppLaunchStarted();
  _patrolAppLaunch ??= runQuwoquanApp(
    autoCompleteStartupWelcomeForTest: true,
    providerScopeOverrides: [
      authSessionControllerProvider.overrideWith(
        _PatrolAuthSessionController.new,
      ),
    ],
  );
  await _completePatrolAppLaunch($, startRuntimeAnonymousSession: true);
}

/// Starts the production Remote App without replacing its authentication
/// controller. Runtime-recovery acceptance uses this entrypoint so the rebuilt
/// root must restore the device's real persisted session instead of receiving
/// a test-installed session again.
Future<void> launchPatrolAppWithPersistedSessionOnce(
  PatrolIntegrationTester $,
) async {
  markPatrolAppLaunchStarted();
  _patrolAppLaunch ??= runQuwoquanApp(
    autoCompleteStartupWelcomeForTest: true,
    providerScopeOverrides: const [],
  );
  await _completePatrolAppLaunch($, startRuntimeAnonymousSession: false);
}

Future<void> _completePatrolAppLaunch(
  PatrolIntegrationTester $, {
  required bool startRuntimeAnonymousSession,
}) async {
  await _patrolAppLaunch!;
  // 本地 Remote 冷启动会带来持续中的初始化任务，直接等待全局 settle
  // 容易把 Patrol user_acceptance 卡死在启动阶段。这里仅给首帧和首轮路由足够时间，
  // 后续由具体用例等待目标元素出现。
  await $.pump();
  await $.pump(const Duration(milliseconds: 300));
  await _awaitPatrolBootstrap($);
  if (startRuntimeAnonymousSession && _usesRuntimeAnonymousSession) {
    await _startRuntimeAnonymousSessionFromMountedApp();
    await _runtimeAnonymousSessionGate().future.timeout(
      const Duration(seconds: 45),
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
    if (find.text(FoundationText.startupRecoveryTitle).evaluate().isNotEmpty) {
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
    final result = await _loginAnonymousForPatrolWithRetry(container);
    final controller = container.read(authSessionControllerProvider.notifier);
    await controller.applyTrustedGuestGrant(result);
    final session = container.read(authSessionControllerProvider);
    if (!session.hasTrustedSession ||
        session.isAuthenticated ||
        session.activePersonaId.trim().isEmpty) {
      throw StateError(
        'anonymous login did not install a trusted guest session',
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
          '$_runtimeAnonymousSessionFailure',
        ),
        stackTrace,
      );
    }
  }
}

Future<AuthSessionGrant> _loginAnonymousForPatrolWithRetry(
  ProviderContainer container,
) async {
  final command = LoginAnonymousCommand(
    installId: patrolRuntimeInstallId,
    deviceFingerprintHash: patrolRuntimeInstallId,
    platform: CloudRequestHeaders.platform(),
    appVersion: 'local-e2e',
  );
  for (
    var attempt = 1;
    attempt <= _patrolAnonymousLoginSetupAttempts;
    attempt++
  ) {
    try {
      return await container
          .read(accountSessionLoginCommandWriterProvider)
          .loginAnonymous(command);
    } on CloudException catch (error) {
      _runtimeAnonymousSessionFailure = _describeRuntimeAnonymousSessionFailure(
        error,
      );
      final retryable =
          error.runtimeFailure.recovery.action.trim().toLowerCase() == 'retry';
      if (!retryable || attempt == _patrolAnonymousLoginSetupAttempts) {
        rethrow;
      }
      await Future<void>.delayed(Duration(seconds: attempt));
    }
  }
  throw StateError('Patrol anonymous login retry loop exhausted');
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
    if (find.text(FoundationText.startupRecoveryTitle).evaluate().isNotEmpty) {
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

final class _PatrolAuthSessionController extends AuthSessionController {
  @override
  AuthSessionState build() {
    if (_usesRuntimeAnonymousSession) {
      return const AuthSessionState.restoring();
    }
    if (_usesAnonymousPublicVideoSession) {
      return buildPatrolAnonymousPublicVideoSession();
    }
    if (_usesUnauthenticatedAuthEntry) {
      return buildPatrolUnauthenticatedAuthEntrySession();
    }
    final runnerSession = patrolRunnerInstalledAcceptanceSession;
    if (runnerSession != null) {
      return runnerSession;
    }
    return buildPatrolAcceptanceSession(
      accessToken: _patrolAcceptanceAuthToken,
      refreshToken: _patrolAcceptanceRefreshToken,
      ownerId: kPatrolAcceptanceCurrentOwnerId,
      personaId: kPatrolAcceptanceCurrentPersonaId,
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
