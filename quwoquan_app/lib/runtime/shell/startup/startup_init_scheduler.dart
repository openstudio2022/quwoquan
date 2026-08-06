import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_startup_runtime.dart';
import 'package:quwoquan_app/runtime/shell/state/appearance_settings_provider.dart';
import 'package:quwoquan_app/runtime/shell/state/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/startup_native_bridge.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart'
    show appTelemetryReporterProvider, realtimeConnectionManagerProvider;
import 'package:quwoquan_app/runtime/shell/startup/startup_content_warmup_port.dart';

/// 冷启动初始化分档调度：系统路径只做轻量 sync；业务 IO 滞后到欢迎页窗口。
final class StartupInitScheduler {
  StartupInitScheduler({
    required this.ref,
    required this.logException,
    required this.contentWarmupPort,
    this.postFirstFrameTasks,
    this.authNetworkPrerequisites,
    this.startupPrerequisiteBudget = const Duration(milliseconds: 2500),
  });

  final WidgetRef ref;
  final StartupContentWarmupPort contentWarmupPort;
  final void Function({
    required String source,
    required String exceptionText,
    required String stackText,
  })
  logException;
  final Future<void> Function()? postFirstFrameTasks;
  final Future<void> Function()? authNetworkPrerequisites;
  final Duration startupPrerequisiteBudget;

  bool _firstFrameHandled = false;
  bool _welcomeWindowStarted = false;
  bool _authInitializationStarted = false;
  bool _authNetworkPrerequisiteSatisfied = false;
  bool _welcomeCompleted = false;
  bool _shellServicesStarted = false;
  bool _disposed = false;
  Timer? _startupPrerequisiteTimer;
  Future<void>? _postFirstFrameTask;
  Future<void>? _authNetworkPrerequisite;
  void Function()? _stopRealtimeConnection;

  void dispose() {
    _disposed = true;
    _startupPrerequisiteTimer?.cancel();
    _startupPrerequisiteTimer = null;
    final stopRealtimeConnection = _stopRealtimeConnection;
    _stopRealtimeConnection = null;
    if (stopRealtimeConnection != null) {
      try {
        stopRealtimeConnection();
      } catch (error, stack) {
        logException(
          source: 'startup_realtime_dispose',
          exceptionText: error.toString(),
          stackText: stack.toString(),
        );
      }
    }
  }

  void onFirstFrame({
    required void Function() syncWindow,
    required void Function() syncTheme,
  }) {
    if (_disposed || _firstFrameHandled) {
      return;
    }
    _firstFrameHandled = true;
    AppStartupRuntime.instance.markFirstFramePainted();
    _startAuthNetworkPrerequisite();
    // 避免在 TickerMode 切换帧内同步触发 provider rebuild。
    scheduleMicrotask(() {
      if (_disposed) {
        return;
      }
      _bestEffort('startup_sync_window', syncWindow);
      _bestEffort('startup_theme', syncTheme);
    });
  }

  /// 欢迎页首帧可见后启动：auth、appearance、debug prerequisites。
  void onWelcomeVisible({required void Function(bool ready) onShellReady}) {
    if (_disposed || _welcomeWindowStarted) {
      return;
    }
    _welcomeWindowStarted = true;
    AppStartupRuntime.instance.markWelcomeWindowInitStarted();
    scheduleMicrotask(() {
      if (_disposed) {
        return;
      }
      _bestEffort('startup_appearance_ensure_loaded', () {
        unawaited(
          ref
              .read(appearanceSettingsControllerProvider.notifier)
              .ensureLoaded()
              .catchError((Object e, StackTrace stack) {
                if (_disposed) {
                  return;
                }
                logException(
                  source: 'startup_appearance_ensure_loaded',
                  exceptionText: e.toString(),
                  stackText: stack.toString(),
                );
              }),
        );
      });
      _markShellReady(onShellReady);
      _startAuthAfterStartupPrerequisites();
    });
  }

  /// 欢迎动效结束、进入主壳前启动：实时连接与业务队列预热。
  void onWelcomeCompleted() {
    if (_disposed || _welcomeCompleted) {
      return;
    }
    _welcomeCompleted = true;
    AppStartupRuntime.instance.markWelcomeCompleted();
    AppStartupRuntime.instance.bindProductTelemetry(
      ref.read(appTelemetryReporterProvider),
    );
    _bestEffort('startup_runtime_diagnostics', () {
      ref.read(runtimeDiagnosticsProvider).install();
    });
    _startShellServicesIfReady();
  }

  /// Remote 服务必须与认证恢复共用同一个 HTTPS trust 前置门。
  ///
  /// 安全 Shell 和本地诊断可以先交付；若 debug trust 前置任务仍 pending、失败或
  /// 超时，实时连接、业务队列和预热都不得绕过它触发认证网络访问。
  void _startShellServicesIfReady() {
    if (_disposed ||
        _shellServicesStarted ||
        !_welcomeCompleted ||
        !_authNetworkPrerequisiteSatisfied) {
      return;
    }
    _shellServicesStarted = true;
    _bestEffort('startup_realtime_foreground', () {
      final realtime = ref.read(realtimeConnectionManagerProvider.notifier);
      realtime.onAppForeground();
      _stopRealtimeConnection = realtime.onAppBackground;
    });
    _bestEffort('startup_post_publication_queue', () {
      contentWarmupPort.warmUp();
    });
    _bestEffort('startup_post_first_frame_warmup', () {
      AppStartupRuntime.instance.schedulePostFirstFrameWarmup(
        (provider) => ref.read(provider),
      );
    });
  }

  /// Router Shell 已真实绘制且已通知原生 safe terminal 后，才装配可延后的
  /// Android 插件组，避免反射注册与首帧/路由交付争用主线程。
  void onSafeTerminal() {
    if (_disposed) {
      return;
    }
    _startPostFirstFrameTasks();
  }

  void _markShellReady(void Function(bool ready) onShellReady) {
    // 安全 Shell 不依赖本地证书、认证或业务数据。
    _bestEffort('startup_shell_ready', () => onShellReady(true));
  }

  void _startAuthAfterStartupPrerequisites() {
    if (_disposed || _authInitializationStarted) {
      return;
    }
    _authInitializationStarted = true;
    final prerequisites = _authNetworkPrerequisite;
    if (prerequisites == null) {
      _authNetworkPrerequisiteSatisfied = true;
      _startAuthInitialization();
      _startShellServicesIfReady();
      return;
    }
    _startupPrerequisiteTimer?.cancel();
    _startupPrerequisiteTimer = Timer(startupPrerequisiteBudget, () {
      _startupPrerequisiteTimer = null;
      if (!_disposed) {
        logException(
          source: 'startup_prerequisites',
          exceptionText: TimeoutException(
            'startup prerequisites timed out',
            startupPrerequisiteBudget,
          ).toString(),
          stackText: StackTrace.current.toString(),
        );
      }
    });
    unawaited(
      prerequisites.then(
        (_) {
          _finishStartupPrerequisiteObservation();
          _authNetworkPrerequisiteSatisfied = true;
          _startAuthInitialization();
          _startShellServicesIfReady();
        },
        onError: (Object error, StackTrace stack) {
          _finishStartupPrerequisiteObservation();
          if (!_disposed) {
            logException(
              source: 'startup_prerequisites',
              exceptionText: error.toString(),
              stackText: stack.toString(),
            );
          }
        },
      ),
    );
  }

  void _startAuthNetworkPrerequisite() {
    if (_authNetworkPrerequisite != null) {
      return;
    }
    final factory = authNetworkPrerequisites;
    if (factory == null) {
      return;
    }
    try {
      _authNetworkPrerequisite = factory();
    } catch (error, stack) {
      _authNetworkPrerequisite = Future<void>.error(error, stack);
    }
  }

  void _startPostFirstFrameTasks() {
    if (_postFirstFrameTask != null) {
      return;
    }
    final factory = postFirstFrameTasks;
    if (factory == null) {
      return;
    }
    try {
      _postFirstFrameTask = _runPostFirstFrameTasks(factory);
      unawaited(
        _postFirstFrameTask!.catchError((Object error, StackTrace stack) {
          if (_disposed) {
            return;
          }
          logException(
            source: 'startup_post_first_frame_tasks',
            exceptionText: error.toString(),
            stackText: stack.toString(),
          );
        }),
      );
    } catch (error, stack) {
      logException(
        source: 'startup_post_first_frame_tasks',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
  }

  Future<void> _runPostFirstFrameTasks(Future<void> Function() factory) async {
    // iOS 需要等 GeneratedPluginRegistrant 在 renderer 首帧回调完成；Android
    // 则在 safe terminal 之后注册启动后组，避免反射注册与首帧/Router 交付争用。
    await const MethodChannelStartupDeferredPluginsNativeBridge()
        .ensureStartupPostFirstFrame();
    await factory();
  }

  void _startAuthInitialization() {
    if (_disposed) {
      return;
    }
    _bestEffort('startup_auth_restore_gate', () {
      ref.read(startupAuthRestoreGateProvider.notifier).open();
    });
    _bestEffort('startup_auth_session', () {
      ref.read(authSessionControllerProvider);
    });
  }

  void _finishStartupPrerequisiteObservation() {
    _startupPrerequisiteTimer?.cancel();
    _startupPrerequisiteTimer = null;
  }

  void _bestEffort(String source, void Function() action) {
    if (_disposed) {
      return;
    }
    try {
      action();
    } catch (e, stack) {
      logException(
        source: source,
        exceptionText: e.toString(),
        stackText: stack.toString(),
      );
    }
  }
}
