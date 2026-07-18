import 'dart:async';
import 'dart:isolate';
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/app/bootstrap_recovery.dart';
import 'package:quwoquan_app/app/startup/startup_telemetry.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/remote/ops/startup_telemetry_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/di/app_cloud_client_context_provider.dart';
import 'package:quwoquan_app/core/platform/local_dev_https_trust.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_session_store.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/quwoquan_app_shell.dart';

RawReceivePort? _rootIsolateErrorPort;
bool _bootstrapErrorBoundaryInstalled = false;
bool _bootstrapLifecycleObserverInstalled = false;
bool _bootstrapFirstFrameConfirmed = false;
bool _bootstrapRecoveryMounted = false;
bool _bootstrapRecoveryScheduled = false;
List<Override> _bootstrapProviderScopeOverrides = const <Override>[];

/// 共享启动：默认入口 [main] 与 [main_prod] 均经此函数，后者可注入 [providerScopeOverrides]。
///
/// [WidgetsFlutterBinding.ensureInitialized] 与 [runApp] 必须在同一 Zone 内调用，
/// 否则 debug 下会触发 `Zone mismatch`（见 [BindingBase.debugCheckZone]）。
Future<void> runQuwoquanApp({
  List<Override> providerScopeOverrides = const [],
}) async {
  await runZonedGuarded<Future<void>>(
    () async {
      WidgetsFlutterBinding.ensureInitialized();
      _bootstrapProviderScopeOverrides = List<Override>.unmodifiable(
        providerScopeOverrides,
      );
      _installBootstrapErrorBoundary();
      _installRootIsolateErrorListener();
      _configureStartupTelemetry();
      AppStartupRuntime.instance.markBootstrapStarted();
      try {
        CloudRuntimeConfig.validateRequiredEndpoints();
        AppStartupRuntime.instance.markConfigurationValidated();
        // SecureStorage / package_info / 连通性探测不得阻塞 runApp。
        // 日志中 native_first_frame_timeout 后才出现 FlutterSecureStorage migration
        // 即旧路径在首帧预算内卡住的实证。
        AppTelemetrySessionStore.instance.bootstrapForColdStart();
        AppTelemetryContextProvider.instance.bootstrapForColdStart(
          appVersion: const String.fromEnvironment(
            'APP_VERSION',
            defaultValue: 'dev',
          ),
        );
        CloudClientContextRegistry.configure(
          const AppCloudClientContextProvider(),
        );
        assert(() {
          debugPaintSizeEnabled = false;
          debugPaintBaselinesEnabled = false;
          debugPaintPointersEnabled = false;
          debugRepaintRainbowEnabled = false;
          return true;
        }());

        SystemChrome.setSystemUIOverlayStyle(
          AppTheme.systemUiOverlayStyleFor(Brightness.light),
        );
        unawaited(
          SystemChrome.setPreferredOrientations([
            DeviceOrientation.portraitUp,
            DeviceOrientation.portraitDown,
            DeviceOrientation.landscapeLeft,
            DeviceOrientation.landscapeRight,
          ]),
        );

        if (!_bootstrapLifecycleObserverInstalled) {
          WidgetsBinding.instance.addObserver(_AppExceptionLifecycleObserver());
          _bootstrapLifecycleObserverInstalled = true;
        }
        AppStartupRuntime.instance.markRunAppCalled();
        runApp(
          ProviderScope(
            overrides: providerScopeOverrides,
            child: QuWoQuanAppRoot(
              postFirstFrameTasks: _hydratePostFirstFrameStartupState,
              authNetworkPrerequisites: kReleaseMode
                  ? null
                  : _installLocalDevHttpsTrustBeforeMediaClients,
            ),
          ),
        );
        _bootstrapRecoveryMounted = false;
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _bootstrapFirstFrameConfirmed = true;
          AppStartupRuntime.instance.markFirstFramePainted();
        });
      } catch (error, stack) {
        _showBootstrapRecovery(
          error: error,
          stack: stack,
          providerScopeOverrides: providerScopeOverrides,
        );
      }
    },
    (Object error, StackTrace stack) {
      _handleBootstrapZoneError(
        error: error,
        stack: stack,
        providerScopeOverrides: providerScopeOverrides,
      );
    },
  );
}

Future<void> _installLocalDevHttpsTrustBeforeMediaClients() {
  return LocalDevHttpsTrust.installForCurrentRuntime();
}

void _configureStartupTelemetry() {
  StartupTelemetryRuntime.instance.configure(
    StartupTelemetryReporter(
      journal: StartupJournal(SharedPreferencesStartupJournalStore()),
      transport: RemoteStartupTelemetryTransport.fromRuntimeConfig(
        httpClient: CloudHttpClient(
          authTokenProvider: const StubCloudAuthTokenProvider(),
        ),
      ),
      platform: platformWireName(currentAppPlatform),
      runtimeEnv: CloudRuntimeConfig.appRuntimeEnv,
      appVersion: const String.fromEnvironment('APP_VERSION'),
    ),
  );
}

void _installBootstrapErrorBoundary() {
  if (_bootstrapErrorBoundaryInstalled) {
    return;
  }
  _bootstrapErrorBoundaryInstalled = true;
  final previousFlutterErrorHandler = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final message = details.exceptionAsString();
    if (message.contains('_needsLayout') &&
        message.contains('childSemantics.renderObject')) {
      return;
    }
    try {
      if (previousFlutterErrorHandler != null) {
        previousFlutterErrorHandler(details);
      } else {
        FlutterError.presentError(details);
      }
    } catch (_) {
      // 原 handler 的日志异常不能阻止 recovery 根接管。
    }
    _logBootstrapException(
      source: 'flutter_error',
      exceptionText: message,
      stackText: details.stack?.toString() ?? '',
    );
    _scheduleBootstrapRecoveryBeforeFirstFrame(
      details.exception,
      details.stack ?? StackTrace.current,
    );
  };
  final previousPlatformDispatcherHandler = PlatformDispatcher.instance.onError;
  PlatformDispatcher.instance.onError = (Object error, StackTrace stack) {
    _logBootstrapException(
      source: 'platform_dispatcher',
      exceptionText: error.toString(),
      stackText: stack.toString(),
    );
    _scheduleBootstrapRecoveryBeforeFirstFrame(error, stack);
    if (!_bootstrapFirstFrameConfirmed) {
      return true;
    }
    if (previousPlatformDispatcherHandler != null) {
      try {
        return previousPlatformDispatcherHandler(error, stack);
      } catch (_) {
        return false;
      }
    }
    return false;
  };
}

void _handleBootstrapZoneError({
  required Object error,
  required StackTrace stack,
  required List<Override> providerScopeOverrides,
}) {
  if (!_bootstrapFirstFrameConfirmed) {
    _showBootstrapRecovery(
      error: error,
      stack: stack,
      providerScopeOverrides: providerScopeOverrides,
    );
    return;
  }
  _logBootstrapException(
    source: 'zone_guarded',
    exceptionText: error.toString(),
    stackText: stack.toString(),
  );
}

void _scheduleBootstrapRecoveryBeforeFirstFrame(
  Object error,
  StackTrace stack,
) {
  if (_bootstrapFirstFrameConfirmed ||
      _bootstrapRecoveryMounted ||
      _bootstrapRecoveryScheduled) {
    return;
  }
  _bootstrapRecoveryScheduled = true;
  scheduleMicrotask(() {
    _bootstrapRecoveryScheduled = false;
    _showBootstrapRecovery(
      error: error,
      stack: stack,
      providerScopeOverrides: _bootstrapProviderScopeOverrides,
    );
  });
}

void _showBootstrapRecovery({
  required Object error,
  required StackTrace stack,
  required List<Override> providerScopeOverrides,
}) {
  if (_bootstrapFirstFrameConfirmed || _bootstrapRecoveryMounted) {
    _logBootstrapException(
      source: 'bootstrap_failure_after_root',
      exceptionText: error.toString(),
      stackText: stack.toString(),
    );
    return;
  }
  _bootstrapRecoveryMounted = true;
  final failure = BootstrapFailure.fromError(error);
  AppStartupRuntime.instance.recordBootstrapFailure(failure.runtimeFailure);
  _logBootstrapException(
    source: 'bootstrap_failure',
    exceptionText: error.toString(),
    stackText: stack.toString(),
  );
  runApp(
    BootstrapRecoveryApp(
      failure: failure,
      onRetry: () async {
        _bootstrapRecoveryMounted = false;
        _bootstrapFirstFrameConfirmed = false;
        _bootstrapRecoveryScheduled = false;
        await runQuwoquanApp(providerScopeOverrides: providerScopeOverrides);
      },
    ),
  );
  WidgetsBinding.instance.addPostFrameCallback((_) {
    _bootstrapFirstFrameConfirmed = true;
    AppStartupRuntime.instance.markFirstFramePainted();
    AppStartupRuntime.instance.markBootstrapRecoverySurfacePainted();
  });
}

/// 首帧后才允许发起的产品遥测水合。
///
/// 不能在 `runApp` 前调用：async function 在第一个 await 前已发起
/// SecureStorage/PackageInfo/Connectivity 平台调用，足以挤爆原生首帧预算。
Future<void> _hydratePostFirstFrameStartupState() {
  return Future.wait<void>(<Future<void>>[
    AppTelemetrySessionStore.instance.reconcilePersistedGuestKey(),
    AppTelemetryContextProvider.instance.initialize(),
  ]).then((_) {});
}

void _installRootIsolateErrorListener() {
  if (currentAppPlatform == AppPlatform.web) {
    return;
  }
  if (_rootIsolateErrorPort != null) {
    return;
  }
  final port = RawReceivePort((Object? message) {
    if (message is List<Object?> && message.isNotEmpty) {
      final error =
          message.first ?? StateError('root isolate error without value');
      final Object? stack = message.length > 1 ? message[1] : '';
      _logBootstrapException(
        source: 'root_isolate',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
      _scheduleBootstrapRecoveryBeforeFirstFrame(
        error,
        StackTrace.fromString(stack.toString()),
      );
    }
  });
  _rootIsolateErrorPort = port;
  Isolate.current.addErrorListener(port.sendPort);
}

void _logBootstrapException({
  required String source,
  required String exceptionText,
  required String stackText,
}) {
  try {
    logQuwoquanAppException(
      source: source,
      exceptionText: exceptionText,
      stackText: stackText,
    );
  } catch (_) {
    // 启动失败路径只能观测，不得因日志二次失败阻断恢复根。
  }
}

class _AppExceptionLifecycleObserver extends WidgetsBindingObserver {
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.resumed) {
      unawaited(AppExceptionTelemetryService.instance.flushPending());
    }
  }
}
