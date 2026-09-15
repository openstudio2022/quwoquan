import 'dart:async';

import 'package:quwoquan_app/runtime/platform/media/media_orientation_policy.dart';

import 'dart:collection';
import 'dart:isolate';
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/runtime/shell/startup/app_startup_runtime.dart';
import 'package:quwoquan_app/runtime/shell/recovery/bootstrap_recovery.dart';
import 'package:quwoquan_app/runtime/shell/recovery/release_build_failure_placeholder.dart';
import 'package:quwoquan_app/runtime/shell/recovery/runtime_recovery_host.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/observability/runtime_diagnostics.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/di/app_cloud_client_context_provider.dart';
import 'package:quwoquan_app/runtime/platform/firebase_incoming_call_runtime.dart';
import 'package:quwoquan_app/runtime/platform/app_recovery_native_bridge.dart';
import 'package:quwoquan_app/design_system/theme/app_theme.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_session_store.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/runtime/shell/composition/quwoquan_app_shell.dart';
import 'package:quwoquan_app/runtime/di/ops_dependencies.dart';

RawReceivePort? _rootIsolateErrorPort;
bool _bootstrapErrorBoundaryInstalled = false;
bool _bootstrapLifecycleObserverInstalled = false;
bool _bootstrapFirstFrameConfirmed = false;
bool _bootstrapRecoveryMounted = false;
bool _bootstrapRecoveryScheduled = false;
List<Override> _bootstrapProviderScopeOverrides = const <Override>[];
VoidCallback? _configureContentComposition;
VoidCallback Function()? _createReadGeneration;
StartupScopeComposition Function()? _createStartupScope;
final Object _startupLifecycleZoneKey = Object();
int _startupGeneration = 0;

/// 仅在同步创建 composition 期间可捕获；不改变现有零参 factory，不提供 setter。
StartupScopeLifecycle? get installingStartupScopeLifecycle {
  final lifecycle =
      Zone.current[_startupLifecycleZoneKey] as StartupScopeLifecycle?;
  return lifecycle?._installing == true ? lifecycle : null;
}

/// 启动scope本地代际，不是read-generation、持久版本或设备资格。
final class StartupScopeLifecycle {
  StartupScopeLifecycle._(this.generation, this._runtimeIdentity)
    : _attemptId = AppStartupRuntime.instance.startupAttemptId;
  final int generation;
  final String _runtimeIdentity;
  final String _attemptId;
  bool _active = true;
  bool _installing = true;
  bool get isCurrent {
    if (!_active) return false;
    try {
      return CloudRuntimeConfig.runtimeConfigPackageDigest ==
              _runtimeIdentity &&
          AppStartupRuntime.instance.startupAttemptId == _attemptId;
    } catch (_) {
      return false;
    }
  }

  ConfirmedStartupAttempt? get confirmedAttempt =>
      isCurrent ? AppStartupRuntime.instance.confirmedStartupAttempt : null;
  void requireCurrent() {
    if (!isCurrent) throw StateError('Startup scope is no longer current');
  }
}

/// 制品入口提供typed overrides与释放句柄，共享启动层不依赖隔离实现。
final class StartupScopeComposition {
  StartupScopeComposition({
    List<Override> overrides = const [],
    required this.dispose,
  }) : overrides = List.unmodifiable(overrides);
  final List<Override> overrides;
  final VoidCallback dispose;
}

/// 合并基础与启动级 overrides，同一 provider 只保留最后声明的现役装配。
List<Override> mergeStartupScopeOverrides(
  Iterable<Override> base,
  Iterable<Override> startup,
) {
  final seen = HashSet<Object>.identity();
  return <Override>[...base, ...startup].reversed
      .where(
        (override) => seen.add(
          // Riverpod 3拒绝同container重复origin；这里是组合根去重所需身份。
          // ignore: invalid_use_of_visible_for_testing_member
          override.origin,
        ),
      )
      .toList(growable: false)
      .reversed
      .toList(growable: false);
}

void configureAppStartupScope(StartupScopeComposition Function() create) {
  _createStartupScope = create;
}

/// 生命周期高于业务read-generation；R0/R1不重复安装启动级store/auth。
class AppStartupScope extends StatefulWidget {
  const AppStartupScope({
    super.key,
    required this.runtimeIdentity,
    required this.childBuilder,
  });
  final String runtimeIdentity;
  final Widget Function(List<Override> overrides) childBuilder;
  @override
  State<AppStartupScope> createState() => _AppStartupScopeState();
}

class _AppStartupScopeState extends State<AppStartupScope> {
  StartupScopeComposition? _composition;
  StartupScopeLifecycle? _lifecycle;
  @override
  void initState() {
    super.initState();
    _install();
  }

  void _install() {
    if (widget.runtimeIdentity !=
        CloudRuntimeConfig.runtimeConfigPackageDigest) {
      throw StateError('Startup scope must match verified runtime identity');
    }
    final lifecycle = StartupScopeLifecycle._(
      ++_startupGeneration,
      widget.runtimeIdentity,
    );
    _lifecycle = lifecycle;
    try {
      _composition = runZoned(
        () => _createStartupScope?.call(),
        zoneValues: {_startupLifecycleZoneKey: lifecycle},
      );
    } catch (_) {
      lifecycle._active = false;
      rethrow;
    } finally {
      lifecycle._installing = false;
    }
  }

  @override
  void didUpdateWidget(covariant AppStartupScope oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.runtimeIdentity != widget.runtimeIdentity) {
      final previous = _composition;
      _lifecycle?._active = false;
      _composition = null;
      previous?.dispose();
      _install();
    }
  }

  @override
  void dispose() {
    _lifecycle?._active = false;
    _composition?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => KeyedSubtree(
    key: ValueKey(widget.runtimeIdentity),
    child: widget.childBuilder(_composition?.overrides ?? const []),
  );
}

void configureAppReadGeneration(VoidCallback Function() create) {
  _createReadGeneration = create;
}

/// 由制品入口登记装配，在可信运行配置水合后、任何业务 Provider 创建前执行。
/// recovery 重入复用同一入口装配，不在共享启动层导入隔离 adapter。
void configureAppContentComposition(VoidCallback configure) {
  _configureContentComposition = configure;
}

/// 首次 [runZonedGuarded] 建立的 bootstrap Zone。
///
/// [WidgetsFlutterBinding.ensureInitialized] 与全部 [runApp]（含 recovery / retry）
/// 必须始终落在该 Zone；重试禁止再次 `runZonedGuarded`，否则 debug 下会触发
/// `Zone mismatch`（见 [BindingBase.debugCheckZone]）。
Zone? _bootstrapZone;

/// 共享启动：默认入口 [main] 与 [main_prod] 均经此函数，后者可注入 [providerScopeOverrides]。
Future<void> runQuwoquanApp({
  String? expectedOfflineSnapshotDigest,
  List<Override> providerScopeOverrides = const [],
  bool autoCompleteStartupWelcomeForTest = false,
}) {
  final existingZone = _bootstrapZone;
  if (existingZone != null) {
    return existingZone.run(
      () => _runQuwoquanAppInBootstrapZone(
        expectedOfflineSnapshotDigest: expectedOfflineSnapshotDigest,
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
          expectedOfflineSnapshotDigest: expectedOfflineSnapshotDigest,
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
  required String? expectedOfflineSnapshotDigest,
  required List<Override> providerScopeOverrides,
  required bool autoCompleteStartupWelcomeForTest,
}) async {
  WidgetsFlutterBinding.ensureInitialized();
  configureRecoveryRuntimeOperations();
  _bootstrapProviderScopeOverrides = List<Override>.unmodifiable(
    providerScopeOverrides,
  );
  _installBootstrapErrorBoundary();
  _installRootIsolateErrorListener();
  AppStartupRuntime.instance.markBootstrapStarted();
  try {
    if (!_bootstrapLifecycleObserverInstalled) {
      WidgetsBinding.instance.addObserver(MediaOrientationPolicy.instance);
      WidgetsBinding.instance.addObserver(_AppExceptionLifecycleObserver());
      _bootstrapLifecycleObserverInstalled = true;
    }
    // 原生启动声明与 Flutter 共用正向竖屏；配置失败恢复也不放开方向。
    await MediaOrientationPolicy.instance.enforcePortraitUp();
    unawaited(_hydrateNativeStartupTimingForBootstrap());
    await CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
      expectedOfflineSnapshotDigest: expectedOfflineSnapshotDigest,
    );
    _configureContentComposition?.call();
    if (CloudRuntimeConfig.networkAccessAllowed) {
      registerFirebaseIncomingCallBackgroundHandler();
    }
    initializeStartupTelemetryRuntime();
    CloudRuntimeConfig.validateRequiredEndpoints();
    attachStartupTelemetryTransport();
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
    AppStartupRuntime.instance.markRunAppCalled();
    runApp(
      AppStartupScope(
        runtimeIdentity: CloudRuntimeConfig.runtimeConfigPackageDigest,
        childBuilder: (startupOverrides) => RuntimeRecoveryHost(
          createReadGeneration: _createReadGeneration,
          readSourceIdentity: CloudRuntimeConfig.runtimeConfigPackageDigest,
          childBuilder: (generationKey, isRuntimeReentry) => ProviderScope(
            key: generationKey,
            overrides: mergeStartupScopeOverrides(
              providerScopeOverrides,
              startupOverrides,
            ),
            child: QuWoQuanAppRoot(
              autoCompleteStartupWelcomeForTest:
                  autoCompleteStartupWelcomeForTest,
              skipStartupWelcome: isRuntimeReentry,
              postFirstFrameTasks: _hydratePostFirstFrameStartupState,
              authNetworkPrerequisites: null,
            ),
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

Future<void> _hydrateNativeStartupTimingForBootstrap() async {
  try {
    await AppStartupRuntime.instance.beginNativeStartupAttempt();
  } catch (error, stack) {
    // Native timing only calibrates observability/deadline accounting. It is
    // not configuration, security, or a Shell prerequisite and must never
    // convert a slow MethodChannel into a startup failure.
    logQuwoquanAppException(
      source: 'bootstrap_native_timing_hydration',
      exceptionText: error.toString(),
      stackText: stack.toString(),
    );
  }
}

/// release 下把 Widget 构建异常的默认灰屏死块替换为中性可读占位。
///
/// 仅 [kReleaseMode] 生效：debug 保留 Flutter 红屏便于定位，widget 测试
/// 保持默认行为以免构建错误被吞掉造成误通过。异常本身仍先经
/// [FlutterError.onError] 链完成日志与遥测，这里只负责用户可见降级。
void _installReleaseErrorWidgetBuilder() {
  if (!kReleaseMode) {
    return;
  }
  ErrorWidget.builder = (FlutterErrorDetails details) =>
      const ReleaseBuildFailurePlaceholder();
}

void _installBootstrapErrorBoundary() {
  if (_bootstrapErrorBoundaryInstalled) {
    return;
  }
  _bootstrapErrorBoundaryInstalled = true;
  _installReleaseErrorWidgetBuilder();
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
    // 首帧后 AppRuntimeDiagnostics 是未捕获异常的唯一 ES 写入口（它链式包装
    // 本 handler 并自行记录）；此处让位，避免同一异常写出两条不同指纹的记录。
    if (!AppRuntimeDiagnostics.globalUncaughtCaptureActive) {
      _logBootstrapException(
        source: 'flutter_error',
        exceptionText: message,
        stackText: details.stack?.toString() ?? '',
      );
    }
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
    // 同 FlutterError 链：diagnostics 接管后由其单点记录，避免双写。
    if (!AppRuntimeDiagnostics.globalUncaughtCaptureActive) {
      _logBootstrapException(
        source: 'platform_dispatcher',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
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
  // native package 读取/水合本身失败时，仍安装同一个本地 journal；该路径不挂
  // transport，直到下一次拥有通过校验的 runtime config。
  initializeStartupTelemetryRuntime();
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
    }
  }
}
