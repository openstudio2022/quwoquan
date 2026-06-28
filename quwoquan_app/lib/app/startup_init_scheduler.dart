import 'dart:async';

import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show appLogUploaderProvider, realtimeConnectionManagerProvider;

/// 冷启动初始化分档调度：系统路径只做轻量 sync；业务 IO 滞后到欢迎页窗口。
final class StartupInitScheduler {
  StartupInitScheduler({
    required this.ref,
    required this.logException,
    this.startupPrerequisites,
    this.startupPrerequisiteBudget = const Duration(milliseconds: 2500),
  });

  final WidgetRef ref;
  final void Function({
    required String source,
    required String exceptionText,
    required String stackText,
  })
  logException;
  final Future<void>? startupPrerequisites;
  final Duration startupPrerequisiteBudget;

  bool _firstFrameHandled = false;
  bool _welcomeWindowStarted = false;
  bool _shellServicesStarted = false;

  void onFirstFrame({
    required void Function() syncWindow,
    required void Function() syncTheme,
  }) {
    if (_firstFrameHandled) {
      return;
    }
    _firstFrameHandled = true;
    AppStartupRuntime.instance.markFirstFramePainted();
    // 避免在 TickerMode 切换帧内同步触发 provider rebuild。
    scheduleMicrotask(() {
      _bestEffort('startup_sync_window', syncWindow);
      _bestEffort('startup_theme', syncTheme);
    });
  }

  /// 欢迎页首帧可见后启动：auth、appearance、debug prerequisites。
  void onWelcomeVisible({required void Function(bool ready) onShellReady}) {
    if (_welcomeWindowStarted) {
      return;
    }
    _welcomeWindowStarted = true;
    AppStartupRuntime.instance.markWelcomeWindowInitStarted();
    unawaited(AppStartupRuntime.instance.hydrateNativeProcessSegments());
    scheduleMicrotask(() {
      ref.read(startupAuthRestoreGateProvider.notifier).open();
      _bestEffort('startup_auth_session', () {
        ref.read(authSessionControllerProvider);
      });
      _bestEffort('startup_appearance_ensure_loaded', () {
        unawaited(
          ref
              .read(appearanceSettingsControllerProvider.notifier)
              .ensureLoaded()
              .catchError((Object e, StackTrace stack) {
                logException(
                  source: 'startup_appearance_ensure_loaded',
                  exceptionText: e.toString(),
                  stackText: stack.toString(),
                );
              }),
        );
      });
      _completeStartupPrerequisitesThenReady(onShellReady);
    });
  }

  /// 欢迎动效结束、进入主壳前启动：日志、实时连接、analytics 预热。
  void onWelcomeCompleted() {
    if (_shellServicesStarted) {
      return;
    }
    _shellServicesStarted = true;
    AppStartupRuntime.instance.markWelcomeCompleted();
    _bestEffort('startup_log_uploader', () {
      ref.read(appLogUploaderProvider);
    });
    _bestEffort('startup_realtime_foreground', () {
      ref.read(realtimeConnectionManagerProvider.notifier).onAppForeground();
    });
    _bestEffort('startup_post_first_frame_warmup', () {
      AppStartupRuntime.instance.schedulePostFirstFrameWarmup(
        (provider) => ref.read(provider),
      );
    });
  }

  void _completeStartupPrerequisitesThenReady(
    void Function(bool ready) onShellReady,
  ) {
    final prerequisites = startupPrerequisites;
    if (prerequisites == null) {
      onShellReady(true);
      return;
    }
    unawaited(() async {
      try {
        await prerequisites.timeout(startupPrerequisiteBudget);
      } catch (e, stack) {
        logException(
          source: 'startup_prerequisites',
          exceptionText: e.toString(),
          stackText: stack.toString(),
        );
      } finally {
        onShellReady(true);
      }
    }());
  }

  void _bestEffort(String source, void Function() action) {
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
