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
import 'package:quwoquan_app/app/recovery/recovery_failure_reporter.dart';
import 'package:quwoquan_app/app/recovery/runtime_recovery_host.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/di/app_cloud_client_context_provider.dart';
import 'package:quwoquan_app/core/platform/firebase_incoming_call_runtime.dart';
import 'package:quwoquan_app/core/platform/app_recovery_native_bridge.dart';
import 'package:quwoquan_app/core/platform/native_runtime_config_bridge.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_session_store.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/quwoquan_app_shell.dart';
import 'package:quwoquan_app/runtime/di/ops_dependencies.dart';

RawReceivePort? _rootIsolateErrorPort;
bool _bootstrapErrorBoundaryInstalled = false;
bool _bootstrapLifecycleObserverInstalled = false;
bool _bootstrapFirstFrameConfirmed = false;
bool _bootstrapRecoveryMounted = false;
bool _bootstrapRecoveryScheduled = false;
List<Override> _bootstrapProviderScopeOverrides = const <Override>[];

/// 首次 [runZonedGuarded] 建立的 bootstrap Zone。
///
/// [WidgetsFlutterBinding.ensureInitialized] 与全部 [runApp]（含 recovery / retry）
/// 必须始终落在该 Zone；重试禁止再次 `runZonedGuarded`，否则 debug 下会触发
/// `Zone mismatch`（见 [BindingBase.debugCheckZone]）。
Zone? _bootstrapZone;

/// 共享启动：默认入口 [main] 与 [main_prod] 均经此函数，后者可注入 [providerScopeOverrides]。
Future<void> runQuwoquanApp({
  List<Override> providerScopeOverrides = const [],
  bool autoCompleteStartupWelcomeForTest = false,
}) {
  final existingZone = _bootstrapZone;
  if (existingZone != null) {
    return existingZone.run(
      () => _runQuwoquanAppInBootstrapZone(
        providerScopeOverrides: providerScopeOverrides,
        autoCompleteStartupWelcomeForTest: autoCompleteStartupWelcomeForTest,
      ),
    );
  }

  final done = Completer<void>();
  runZonedGuarded(
    () {
      _bootstrapZone = Zone.current;
      unawaited(
        _runQuwoquanAppInBootstrapZone(
          providerScopeOverrides: providerScopeOverrides,
          autoCompleteStartupWelcomeForTest: autoCompleteStartupWelcomeForTest,
        ).then<void>(
          (_) {
            if (!done.isCompleted) {
              done.complete();
            }
          },
          onError: (Object error, StackTrace stack) {
            if (!done.isCompleted) {
              done.completeError(error, stack);
            }
          },
        ),
      );
    },
    (Object error, StackTrace stack) {
      _handleBootstrapZoneError(
        error: error,
        stack: stack,
        providerScopeOverrides: providerScopeOverrides,
      );
      if (!done.isCompleted) {
        done.complete();
      }
    },
  );
  return done.future;
}

Future<void> _runQuwoquanAppInBootstrapZone({
  required List<Override> providerScopeOverrides,
  required bool autoCompleteStartupWelcomeForTest,
}) async {
  WidgetsFlutterBinding.ensureInitialized();
  registerFirebaseIncomingCallBackgroundHandler();
  _bootstrapProviderScopeOverrides = List<Override>.unmodifiable(
    providerScopeOverrides,
  );
  _installBootstrapErrorBoundary();
  _installRootIsolateErrorListener();
  AppStartupRuntime.instance.markBootstrapStarted();
  try {
    await AppStartupRuntime.instance.beginNativeStartupAttempt();
    CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
      await NativeRuntimeConfigBridge.readRuntimePackage(),
      enforceNativeLaunchBinding: currentAppPlatform != AppPlatform.web,
    );
    CloudRuntimeConfig.validateRequiredEndpoints();
    configureStartupTelemetryRuntime();
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
    CloudClientContextRegistry.configure(const AppCloudClientContextProvider());
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
      RuntimeRecoveryHost(
        childBuilder: (generationKey, isRuntimeReentry) => ProviderScope(
          key: generationKey,
          overrides: providerScopeOverrides,
          child: QuWoQuanAppRoot(
            autoCompleteStartupWelcomeForTest:
                autoCompleteStartupWelcomeForTest,
            skipStartupWelcome: isRuntimeReentry,
            postFirstFrameTasks: _hydratePostFirstFrameStartupState,
            authNetworkPrerequisites: null,
          ),
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
    if (details.exception is UnrecoverableRuntimeException) {
      RuntimeRecoveryCoordinator.instance.enter(
        error: details.exception,
        stack: details.stack ?? StackTrace.current,
        source: (details.exception as UnrecoverableRuntimeException).source,
      );
    }
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
    if (_bootstrapFirstFrameConfirmed &&
        error is UnrecoverableRuntimeException) {
      RuntimeRecoveryCoordinator.instance.enter(
        error: error,
        stack: stack,
        source: error.source,
      );
      return true;
    }
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
  if (error is UnrecoverableRuntimeException) {
    RuntimeRecoveryCoordinator.instance.enter(
      error: error,
      stack: stack,
      source: error.source,
    );
  }
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
  final zone = _bootstrapZone ?? Zone.current;
  zone.scheduleMicrotask(() {
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
  final zone = _bootstrapZone;
  if (zone != null && !identical(Zone.current, zone)) {
    zone.run(
      () => _showBootstrapRecovery(
        error: error,
        stack: stack,
        providerScopeOverrides: providerScopeOverrides,
      ),
    );
    return;
  }
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
  unawaited(
    AppRecoveryNativeBridge().recordFatalStartup(
      attemptId: AppStartupRuntime.instance.startupAttemptId,
      failureCode: failure.runtimeFailure.code,
    ),
  );
  unawaited(
    RecoveryFailureReporter.instance.record(
      errorSource: 'flutter',
      errorType: error.runtimeType.toString(),
      errorMessage: error.toString(),
      stackTrace: stack.toString(),
    ),
  );
  AppStartupRuntime.instance.recordBootstrapFailure(failure.runtimeFailure);
  _logBootstrapException(
    source: 'bootstrap_failure',
    exceptionText: error.toString(),
    stackText: stack.toString(),
  );
  runApp(BootstrapRecoveryApp(failure: failure));
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
    RecoveryFailureReporter.instance.recordPendingNativeStartupFatal(),
    RecoveryFailureReporter.instance.flush(),
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
  // runtime package 缺失必须在控制台可见，不能只进遥测。
  final hint =
      exceptionText.contains('runtime_define_validation') ||
          exceptionText.contains('App runtime package is missing')
      ? ' Repair: Debug may use `flutter run`; Profile/Release and explicit '
            'environments require a complete canonical launcher handoff.'
      : '';
  debugPrint('[bootstrap] source=$source exception=$exceptionText$hint');
  if (stackText.isNotEmpty) {
    debugPrint('[bootstrap] stack=$stackText');
  }
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
      unawaited(RecoveryFailureReporter.instance.flush());
    }
  }
}
