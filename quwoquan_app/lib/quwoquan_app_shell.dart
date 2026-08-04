// ignore_for_file: unnecessary_import, unnecessary_overrides

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/app/bootstrap_recovery.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/app_router_module.dart';
import 'package:quwoquan_app/app/recovery/recovery_surface.dart';
import 'package:quwoquan_app/app/recovery/recovery_failure_reporter.dart';
import 'package:quwoquan_app/app/recovery/runtime_recovery_host.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/app/providers/welcome_state_provider.dart';
import 'package:quwoquan_app/app/startup_init_scheduler.dart';
import 'package:quwoquan_app/app/startup_screen_util_scope.dart';
import 'package:quwoquan_app/app/startup/startup_state_machine.dart';
import 'package:quwoquan_app/app/startup_welcome_appearance.dart';
import 'package:quwoquan_app/user/account/user_account/application/account_closure_local_data_purger_provider.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/core/design_system/theme/app_theme.dart';
import 'package:quwoquan_app/core/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/core/services/app_permission_lifecycle_binding.dart';
import 'package:quwoquan_app/core/platform/app_recovery_native_bridge.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show
        appTelemetryReporterProvider,
        appResourceCacheProfileProvider,
        cacheTelemetrySinkProvider,
        mediaDownloadCacheProvider,
        postObjectCacheProvider,
        realtimeConnectionManagerProvider;
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/telemetry/app_page_experience_tracker.dart';
import 'package:quwoquan_app/core/trackers/feed_performance_observability_provider.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/welcome/pages/welcome_screen.dart';
import 'package:quwoquan_app/ui/welcome/welcome_motion_timeline.dart';

part 'quwoquan_app_shell_runtime_support.dart';

/// 根组件：冷启动先直出轻量欢迎页，首帧后再并行恢复会话、装配路由与预热首页。
class QuWoQuanAppRoot extends ConsumerStatefulWidget {
  const QuWoQuanAppRoot({
    super.key,
    this.autoCompleteStartupWelcomeForTest = false,
    this.skipStartupWelcome = false,
    this.postFirstFrameTasks,
    this.authNetworkPrerequisites,
  });

  /// Patrol bootstrap 专用：首帧完成后走与 WelcomeScreen 相同的 router handoff。
  ///
  /// 默认入口始终为 false；生产欢迎动效与完成时序不受此测试注入影响。
  final bool autoCompleteStartupWelcomeForTest;

  /// R1 受控重建时恢复层已经承担可见过渡，不再播放欢迎序列。
  final bool skipStartupWelcome;

  /// 首帧已实际绘制后才创建的非关键水合任务。
  ///
  /// 这里必须是 factory，不能传入已启动的 [Future]；否则 SecureStorage、
  /// PackageInfo 或 Connectivity 会在 `runApp` 前抢占 Android/iOS 首帧。
  final Future<void> Function()? postFirstFrameTasks;

  /// 仅用于必须先于认证网络访问完成的本地能力（当前为 debug HTTPS trust）。
  ///
  /// 它同样只能在首帧后创建，且不会阻断安全 Shell。
  final Future<void> Function()? authNetworkPrerequisites;

  @override
  ConsumerState<QuWoQuanAppRoot> createState() => _QuWoQuanAppRootState();
}

class _QuWoQuanAppRootState extends ConsumerState<QuWoQuanAppRoot>
    with WidgetsBindingObserver {
  static const Duration _startupPrerequisiteBudget = Duration(
    milliseconds: 2500,
  );

  bool _startupShellReady = false;
  bool _routerShellFirstPainted = false;
  Timer? _welcomeOverlayRemovalTimer;
  Timer? _startupDeadlineTimer;
  Future<void>? _routerPreload;
  final Completer<void> _disposeSignal = Completer<void>();
  late final StartupInitScheduler _startupInitScheduler;
  late final StartupStateMachine _startupStateMachine;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // 在欢迎页首帧之前安装全局异常和帧时序采集，避免冷启动阶段的诊断空窗。
    AppPageExperienceTracker.instance.attachReporter(
      ref.read(appTelemetryReporterProvider),
    );
    ref.read(runtimeDiagnosticsProvider).install();
    _startupStateMachine = StartupStateMachine();
    _startupInitScheduler = StartupInitScheduler(
      ref: ref,
      logException: logQuwoquanAppException,
      postFirstFrameTasks: widget.postFirstFrameTasks,
      authNetworkPrerequisites: widget.authNetworkPrerequisites,
      startupPrerequisiteBudget: _startupPrerequisiteBudget,
    );
    _armStartupDeadline();
    unawaited(_hydrateNativeTimingForTelemetry());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      AppStartupRuntime.instance.markFirstFramePainted();
    });
    if (widget.skipStartupWelcome) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        scheduleMicrotask(() {
          if (!mounted) return;
          _onWelcomeVisible();
          _completeStartupWelcome();
        });
      });
    } else if (widget.autoCompleteStartupWelcomeForTest) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        scheduleMicrotask(() {
          if (mounted) {
            _completeStartupWelcome();
          }
        });
      });
    }
  }

  @override
  void dispose() {
    if (!_disposeSignal.isCompleted) {
      _disposeSignal.complete();
    }
    _startupInitScheduler.dispose();
    _welcomeOverlayRemovalTimer?.cancel();
    _startupDeadlineTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    try {
      handleQuwoquanAppLifecycleState(
        state: state,
        refreshAppearance: () {
          try {
            ref.read(appearanceSettingsControllerProvider.notifier).refresh();
          } catch (error, stack) {
            logQuwoquanAppException(
              source: 'startup_lifecycle_appearance',
              exceptionText: error.toString(),
              stackText: stack.toString(),
            );
          }
        },
        onRealtimeForeground: () {
          try {
            ref
                .read(realtimeConnectionManagerProvider.notifier)
                .onAppForeground();
            unawaited(_refreshAuthSessionOnForegroundIfNeeded());
          } catch (error, stack) {
            logQuwoquanAppException(
              source: 'startup_lifecycle_realtime_foreground',
              exceptionText: error.toString(),
              stackText: stack.toString(),
            );
          }
        },
        onRealtimeBackground: () {
          try {
            ref
                .read(realtimeConnectionManagerProvider.notifier)
                .onAppBackground();
          } catch (error, stack) {
            logQuwoquanAppException(
              source: 'startup_lifecycle_realtime_background',
              exceptionText: error.toString(),
              stackText: stack.toString(),
            );
          }
        },
      );
    } catch (error, stack) {
      logQuwoquanAppException(
        source: 'startup_lifecycle',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
  }

  @override
  void didChangeLocales(List<Locale>? locales) {
    super.didChangeLocales(locales);
  }

  @override
  void didChangeMetrics() {
    super.didChangeMetrics();
    _syncWindowDerivedState();
  }

  @override
  void didHaveMemoryPressure() {
    super.didHaveMemoryPressure();
    AppImageCacheController.trimForMemoryPressure();
    final mediaDownloadCache = ref.read(mediaDownloadCacheProvider);
    mediaDownloadCache.cancelQueuedPrefetches();
    final clearedPostDetails = ref
        .read(postObjectCacheProvider)
        .clearRecentDetails();
    ref
        .read(feedPerformanceObservabilityProvider)
        .recordMediaDownloadQueue(
          profile: AppResourceCacheProfile.compact.name,
          activeDownloads: mediaDownloadCache.activeDownloadCount,
          queuedDownloads: mediaDownloadCache.queuedDownloadCount,
          inflightDownloads: mediaDownloadCache.inflightDownloadCount,
          cacheSizeBytes: mediaDownloadCache.currentCacheSizeBytes,
        );
    ref
        .read(cacheTelemetrySinkProvider)
        .record('resource.bytes_cleared', <String, Object?>{
          'reason': 'memory_pressure',
          'profile': AppResourceCacheProfile.compact.name,
          'postDetails': clearedPostDetails,
        });
  }

  @override
  void didChangeAccessibilityFeatures() {
    super.didChangeAccessibilityFeatures();
    final mediaQuery = MediaQuery.maybeOf(context);
    if (mediaQuery != null) {
      ref
          .read(accessibilityProvider.notifier)
          .updateFromMediaQueryData(mediaQuery);
    }
  }

  @override
  void didChangeTextScaleFactor() {
    super.didChangeTextScaleFactor();
    final mediaQuery = MediaQuery.maybeOf(context);
    if (mediaQuery != null) {
      ref
          .read(accessibilityProvider.notifier)
          .updateFromMediaQueryData(mediaQuery);
    }
  }

  @override
  void didChangePlatformBrightness() {
    super.didChangePlatformBrightness();
    ref
        .read(themeProvider.notifier)
        .updateSystemBrightness(
          WidgetsBinding.instance.platformDispatcher.platformBrightness,
        );
  }

  void _setStartupShellReady(bool ready) {
    if (_startupShellReady == ready) {
      return;
    }
    if (!mounted) {
      _startupShellReady = ready;
      return;
    }
    scheduleMicrotask(() {
      if (!mounted || _startupShellReady == ready) {
        return;
      }
      setState(() => _startupShellReady = ready);
    });
  }

  void _syncWindowDerivedState() {
    final view = View.maybeOf(context);
    if (view == null) {
      return;
    }
    final mediaQuery = MediaQueryData.fromView(view);
    ref.read(responsiveProvider.notifier).updateFromMediaQueryData(mediaQuery);
    ref
        .read(accessibilityProvider.notifier)
        .updateFromMediaQueryData(mediaQuery);
    AppImageCacheController.applyResourceProfile(
      ref.read(appResourceCacheProfileProvider),
    );
  }

  @override
  Widget build(BuildContext context) {
    ref.watch(accountClosureLocalCleanupLifecycleProvider);
    final startup = _startupStateMachine.snapshot;
    if (startup.phase == StartupRootPhase.welcome) {
      return _buildStartupWelcomeApp(startupWelcomeAppearanceSnapshot());
    }
    if (startup.phase == StartupRootPhase.routerLoading) {
      // Router loading (including an exhausted performance deadline) is not a
      // fatal recovery condition. Keep the completed welcome frame visible
      // until the real shell can paint; never mount StartupRecoveryPage as a
      // hidden underlay for a pure timeout.
      return _buildStartupWelcomeApp(
        startupWelcomeAppearanceSnapshot(),
        frozen: true,
      );
    }

    final snapshot = ref.watch(appearanceSnapshotProvider);
    if (startup.phase == StartupRootPhase.safeRecovery) {
      return _buildStartupFallbackApp(
        snapshot,
        failure: startup.failure == null
            ? BootstrapFailure.deadline()
            : BootstrapFailure.fromRuntimeFailure(startup.failure!),
      );
    }

    final shell = _buildMainShellApp(snapshot);
    if (!startup.welcomeOverlayVisible) {
      return shell;
    }
    return Stack(
      fit: StackFit.expand,
      textDirection: TextDirection.ltr,
      children: <Widget>[
        shell,
        IgnorePointer(
          child: AnimatedOpacity(
            duration: const Duration(milliseconds: 120),
            opacity: startup.welcomeOverlayOpacity,
            onEnd: () {
              if (_startupStateMachine.snapshot.welcomeOverlayOpacity == 0) {
                _removeWelcomeOverlay(trigger: 'fade_completed');
              }
            },
            child: _buildStartupWelcomeApp(
              startupWelcomeAppearanceSnapshot(),
              frozen: true,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildMainShellApp(AppearanceSnapshot snapshot) {
    final router = _watchRouterOrNull();
    if (router == null) {
      return _buildStartupFallbackApp(
        snapshot,
        failure: BootstrapFailure.router(
          appRouterLibraryLastLoadError ??
              StateError('router unavailable after startup transition'),
        ),
      );
    }
    return StartupScreenUtilScope(
      child: MaterialApp.router(
        title: '趣我圈',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.lightTheme,
        darkTheme: AppTheme.darkTheme,
        themeMode: snapshot.themeMode,
        routerConfig: router,
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
        locale: const Locale('zh', 'CN'),
        builder: (context, child) => AppPermissionLifecycleBinding(
          child: wrapWithQuwoquanAppAppearance(
            context: context,
            snapshot: snapshot,
            child: child ?? _buildRouterChildRecovery(),
          ),
        ),
      ),
    );
  }

  Widget _buildStartupWelcomeApp(
    AppearanceSnapshot snapshot, {
    bool frozen = false,
  }) {
    return MaterialApp(
      title: '趣我圈',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: snapshot.themeMode,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
      locale: const Locale('zh', 'CN'),
      builder: (context, child) => AppPermissionLifecycleBinding(
        child: wrapWithQuwoquanAppAppearance(
          context: context,
          snapshot: snapshot,
          child: child ?? const SizedBox.shrink(),
        ),
      ),
      home: WelcomeScreen(
        key: ValueKey(frozen ? 'startup-welcome-frozen' : 'startup-welcome'),
        flowMode: frozen ? WelcomeFlowMode.frozen : WelcomeFlowMode.startup,
        shellEntryReady: _startupShellReady,
        onWelcomeVisible: frozen ? null : _onWelcomeVisible,
        onSequenceEvent: frozen ? null : _onWelcomeSequenceEvent,
        onFinish: frozen ? () {} : _completeStartupWelcome,
      ),
    );
  }

  void _onWelcomeVisible() {
    try {
      _startupInitScheduler.onFirstFrame(
        syncWindow: _syncWindowDerivedState,
        syncTheme: () {
          ref
              .read(themeProvider.notifier)
              .updateSystemBrightness(
                WidgetsBinding.instance.platformDispatcher.platformBrightness,
              );
        },
      );
    } catch (error, stack) {
      logQuwoquanAppException(
        source: 'startup_first_frame_scheduler',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
    try {
      _startupInitScheduler.onWelcomeVisible(
        onShellReady: _setStartupShellReady,
      );
    } catch (error, stack) {
      logQuwoquanAppException(
        source: 'startup_welcome_visible',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
    unawaited(_preloadRouter());
  }

  void _armStartupDeadline() {
    _startupDeadlineTimer?.cancel();
    final remaining =
        StartupWelcomeTiming.production.hardEntryDeadline -
        AppStartupRuntime.instance.deadlineElapsedSinceProcessStart;
    _startupDeadlineTimer = Timer(
      remaining.isNegative ? const Duration(milliseconds: 1) : remaining,
      () {
        if (!mounted ||
            _routerShellFirstPainted ||
            _startupStateMachine.snapshot.phase ==
                StartupRootPhase.safeRecovery) {
          return;
        }
        logQuwoquanAppException(
          source: 'startup_absolute_deadline',
          exceptionText:
              'safe startup terminal was not reached before deadline',
          stackText: StackTrace.current.toString(),
        );
        _recordStartupPhase(
          phase: 'startup_deadline_observed',
          result: 'performance_only',
          deadlineOrigin: 'dart_process',
        );
      },
    );
  }

  Future<void> _hydrateNativeTimingForTelemetry() async {
    try {
      await AppStartupRuntime.instance.beginNativeStartupAttempt(
        cancellationSignal: _disposeSignal.future,
      );
      if (mounted && !_routerShellFirstPainted) {
        // Hydrated native process time may only consume more of the existing
        // budget. Refresh the timer immediately; never leave the longer
        // Dart-only deadline armed.
        _armStartupDeadline();
      }
    } catch (error, stack) {
      // Native timing bridge 是绝对时间校准的增强项；不可用时继续保留 Dart
      // fallback deadline，不能让 bridge 错误影响首帧或安全终态。
      logQuwoquanAppException(
        source: 'startup_root_deadline_clock',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
      return;
    }
  }

  Future<void> _preloadRouter() async {
    if (_routerPreload != null) {
      return _routerPreload!;
    }
    final preload = _runRouterPreload();
    _routerPreload = preload;
    await preload;
  }

  Future<void> _runRouterPreload() async {
    try {
      await ensureAppRouterLibraryLoaded();
      _recordStartupPhase(phase: 'router_preload_ready', result: 'ready');
    } catch (error, stack) {
      logQuwoquanAppException(
        source: 'startup_router_preload',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
      final failure = BootstrapFailure.router(error);
      _recordStartupPhase(
        phase: 'router_preload_failed',
        result: 'failed',
        failureCode: failure.runtimeFailure.code,
        failureSource: 'router',
      );
    }
  }

  void _onWelcomeSequenceEvent(WelcomeSequenceEvent event) {
    try {
      AppStartupRuntime.instance.recordStartupPhase(
        (provider) => ref.read(provider),
        phase: event.phase.name,
        eventName: 'startup_welcome_sequence',
        properties: <String, dynamic>{
          ...event.toProperties(),
          if (event.hintVisible) 'copyKey': 'startupStillStartingInline',
          'hintHeightPx': event.hintVisible ? AppSpacing.radiusTwentyFour : 0,
        },
      );
      assert(() {
        if (event.phase == WelcomeMotionPhase.finished) {
          debugPrint(
            'QWQStartup startup_probe phase=finished '
            'welcomeExitMs=${event.elapsedSinceProcessStart.inMilliseconds} '
            'exitReason=${event.exitReason?.wireName ?? ''} '
            'motionSpec=${WelcomeSequenceEvent.motionSpec} '
            'replayCount=${event.replayCount}',
          );
        }
        return true;
      }());
    } catch (error, stack) {
      logQuwoquanAppException(
        source: 'startup_welcome_sequence_observer',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
  }

  void _onWelcomeCompletedInit() {
    try {
      _startupInitScheduler.onWelcomeCompleted();
    } catch (error, stack) {
      logQuwoquanAppException(
        source: 'startup_welcome_completed',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
  }

  void _completeStartupWelcome() {
    if (!_startupStateMachine.requestWelcomeCompletion()) {
      return;
    }
    _onWelcomeCompletedInit();
    _startRouterLoad();
  }

  void _startRouterLoad() {
    if (!mounted ||
        _startupStateMachine.snapshot.phase == StartupRootPhase.routerShell) {
      return;
    }
    final attempt = _startupStateMachine.beginRouterLoad(
      showWelcomeOverlay: !widget.skipStartupWelcome,
    );
    setState(() {
      // 状态已经在 StartupStateMachine 中推进。
    });
    unawaited(_awaitRouterLoad(attempt: attempt));
  }

  Future<void> _awaitRouterLoad({required int attempt}) async {
    try {
      _recordStartupPhase(phase: 'router_loading', result: 'started');
      await ensureAppRouterLibraryLoaded();
      unawaited(_hydrateNativeStartupSegments());
      if (!mounted || !_startupStateMachine.markRouterReady(attempt)) {
        return;
      }
      try {
        ref.read(welcomeCompletedProvider.notifier).setCompleted(true);
      } catch (error, stack) {
        logQuwoquanAppException(
          source: 'startup_welcome_completed_state',
          exceptionText: error.toString(),
          stackText: stack.toString(),
        );
      }
      setState(() {
        // Router shell 已就绪，下一帧才能开始淡出 welcome overlay。
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _onRouterShellFirstPaint(attempt);
      });
    } catch (error, stack) {
      logQuwoquanAppException(
        source: 'startup_router_library',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
      final failure = BootstrapFailure.router(error);
      if (!mounted ||
          !_startupStateMachine.markRouterFailure(
            attempt,
            failure.runtimeFailure,
          )) {
        return;
      }
      _recordStartupPhase(
        phase: 'router_loading_failed',
        result: 'failed',
        failureCode: failure.runtimeFailure.code,
        failureSource: 'router',
      );
      unawaited(
        RecoveryFailureReporter.instance.record(
          errorSource: 'flutter',
          errorType: error.runtimeType.toString(),
          errorMessage: error.toString(),
          stackTrace: stack.toString(),
        ),
      );
      _showSafeRecovery(failure);
    }
  }

  Future<void> _hydrateNativeStartupSegments() async {
    try {
      await AppStartupRuntime.instance.beginNativeStartupAttempt(
        cancellationSignal: _disposeSignal.future,
      );
      if (mounted && !_routerShellFirstPainted) {
        _armStartupDeadline();
      }
    } catch (error, stack) {
      if (!mounted) {
        return;
      }
      logQuwoquanAppException(
        source: 'startup_native_timing_hydration',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
  }

  void _onRouterShellFirstPaint(int attempt) {
    if (!mounted ||
        attempt != _startupStateMachine.currentRouterAttempt ||
        _startupStateMachine.snapshot.phase != StartupRootPhase.routerShell) {
      return;
    }
    final degraded = !_startupShellReady;
    _routerShellFirstPainted = true;
    _startupDeadlineTimer?.cancel();
    _startupDeadlineTimer = null;
    AppStartupRuntime.instance.markShellFirstPainted();
    _startupInitScheduler.onSafeTerminal();
    RuntimeRecoveryCoordinator.instance.markSafeShellReady();
    _recordStartupPhase(
      phase: 'main_shell_first_paint',
      result: degraded ? 'degraded' : 'entered',
    );
    if (_startupStateMachine.beginOverlayFade()) {
      setState(() {
        // Welcome overlay 只会在真实 shell 首帧之后移除。
      });
    }
    _welcomeOverlayRemovalTimer?.cancel();
    _welcomeOverlayRemovalTimer = Timer(
      const Duration(milliseconds: 120),
      () => _removeWelcomeOverlay(trigger: 'shell_first_paint'),
    );
  }

  void _enterSafeRecovery(BootstrapFailure failure, {required String source}) {
    final phase = _startupStateMachine.snapshot.phase;
    if (phase == StartupRootPhase.routerShell ||
        phase == StartupRootPhase.safeRecovery) {
      return;
    }
    _startupStateMachine.forceSafeRecovery(failure.runtimeFailure);
    final failureSource = source.contains('deadline')
        ? 'startup_deadline'
        : 'router';
    _recordStartupPhase(
      phase: 'safe_recovery_shown',
      result: source,
      failureCode: failure.runtimeFailure.code,
      failureSource: failureSource,
    );
    _showSafeRecovery(failure);
  }

  void _showSafeRecovery(BootstrapFailure failure) {
    unawaited(
      AppRecoveryNativeBridge().recordFatalStartup(
        attemptId: AppStartupRuntime.instance.startupAttemptId,
        failureCode: failure.runtimeFailure.code,
      ),
    );
    _welcomeOverlayRemovalTimer?.cancel();
    _welcomeOverlayRemovalTimer = null;
    _startupDeadlineTimer?.cancel();
    _startupDeadlineTimer = null;
    if (mounted) {
      setState(() {
        // 安全恢复终态已由 StartupStateMachine 决定。
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted &&
            _startupStateMachine.snapshot.phase ==
                StartupRootPhase.safeRecovery) {
          AppStartupRuntime.instance.markSafeRecoverySurfacePainted();
        }
      });
    }
  }

  void _recordStartupPhase({
    required String phase,
    required String result,
    String failureCode = '',
    String failureSource = '',
    String deadlineOrigin = '',
  }) {
    try {
      AppStartupRuntime.instance.recordStartupPhase(
        (provider) => ref.read(provider),
        phase: phase,
        eventName: 'startup_welcome_sequence',
        properties: <String, dynamic>{
          'result': result,
          if (failureCode.isNotEmpty) 'failureCode': failureCode,
          if (failureSource.isNotEmpty) 'failureSource': failureSource,
          if (deadlineOrigin.isNotEmpty) 'deadlineOrigin': deadlineOrigin,
        },
      );
    } catch (error, stack) {
      logQuwoquanAppException(
        source: 'startup_phase_record',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
  }

  void _removeWelcomeOverlay({required String trigger}) {
    if (!mounted || !_startupStateMachine.removeWelcomeOverlay()) {
      return;
    }
    _welcomeOverlayRemovalTimer?.cancel();
    _welcomeOverlayRemovalTimer = null;
    _startupDeadlineTimer?.cancel();
    _startupDeadlineTimer = null;
    setState(() {
      // Overlay 已移除；Router shell 是唯一可见主界面。
    });
    final removedMs =
        AppStartupRuntime.instance.elapsedSinceProcessStart.inMilliseconds;
    AppStartupRuntime.instance.recordStartupPhase(
      (provider) => ref.read(provider),
      phase: 'welcome_overlay_removed',
      eventName: 'startup_welcome_sequence',
      properties: <String, dynamic>{
        'overlayRemovedMs': removedMs,
        'result': trigger,
      },
    );
    AppStartupRuntime.instance.markWelcomeOverlayRemoved();
  }

  Widget _buildRouterChildRecovery() {
    return const StartupRecoveryPage();
  }

  Widget _buildStartupFallbackApp(
    AppearanceSnapshot snapshot, {
    required BootstrapFailure failure,
  }) {
    return MaterialApp(
      title: '趣我圈',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: snapshot.themeMode,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
      locale: const Locale('zh', 'CN'),
      builder: (context, child) => AppPermissionLifecycleBinding(
        child: wrapWithQuwoquanAppAppearance(
          context: context,
          snapshot: snapshot,
          child: child ?? _buildRouterChildRecovery(),
        ),
      ),
      home: const StartupRecoveryPage(),
    );
  }

  GoRouter? _watchRouterOrNull() {
    if (!isAppRouterLibraryLoaded) {
      return null;
    }
    try {
      return ref.watch(deferredAppRouterProvider);
    } catch (error, stack) {
      logQuwoquanAppException(
        source: 'startup_router_build',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
      if (_startupStateMachine.snapshot.phase == StartupRootPhase.routerShell) {
        scheduleMicrotask(
          () => _enterSafeRecovery(
            BootstrapFailure.router(error),
            source: 'router_build_failed',
          ),
        );
      }
      return null;
    }
  }

  Future<void> _refreshAuthSessionOnForegroundIfNeeded() async {
    if (!mounted ||
        _startupStateMachine.snapshot.phase != StartupRootPhase.routerShell) {
      return;
    }
    try {
      final controller = ref.read(authSessionControllerProvider.notifier);
      final session = ref.read(authSessionControllerProvider);
      if (!session.isAuthenticated) {
        return;
      }
      final refreshed = await controller.refreshIfSessionLooksStale();
      if (!mounted) {
        return;
      }
      final currentSession = ref.read(authSessionControllerProvider);
      if (!currentSession.isAuthenticated) {
        ref.read(welcomeCompletedProvider.notifier).setCompleted(true);
        if (!isAppRouterLibraryLoaded) {
          return;
        }
        final router = ref.read(deferredAppRouterProvider);
        final currentLocation = router.routerDelegate.currentConfiguration.uri
            .toString();
        final requiresSafeHome =
            currentSession.promptReason == AuthPromptReason.accountSuspended ||
            currentSession.promptReason == AuthPromptReason.accountClosed;
        final safeLocation = requiresSafeHome
            ? AppRoutePaths.home
            : currentLocation;
        router.go(
          buildLoginRouteLocation(
            reasonName:
                (currentSession.promptReason ?? AuthPromptReason.sessionExpired)
                    .name,
            redirect: currentLocation,
            dismissFallback: safeLocation,
            dismissPolicy: LoginDismissPolicy.safeFallback,
          ),
        );
        return;
      }
      if (!refreshed) {
        await controller.markForegroundAuthCheck();
      }
    } catch (error, stack) {
      logQuwoquanAppException(
        source: 'startup_auth_foreground_refresh',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
  }
}
