// ignore_for_file: unnecessary_import, unnecessary_overrides

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/app/navigation/app_router_module.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/app/providers/welcome_state_provider.dart';
import 'package:quwoquan_app/app/startup_init_scheduler.dart';
import 'package:quwoquan_app/app/startup_screen_util_scope.dart';
import 'package:quwoquan_app/app/startup_welcome_appearance.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_app_exception_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_page_route_exception_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_page_route_exception_summary.g.dart';
import 'package:quwoquan_app/core/design_system/theme/app_theme.dart';
import 'package:quwoquan_app/core/services/app_permission_lifecycle_binding.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show
        appResourceCacheProfileProvider,
        cacheTelemetrySinkProvider,
        appLogUploaderProvider,
        mediaDownloadCacheProvider,
        postObjectCacheProvider,
        realtimeConnectionManagerProvider;
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/feed_performance_observability.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/welcome/pages/welcome_screen.dart';

void handleQuwoquanAppLifecycleState({
  required AppLifecycleState state,
  required VoidCallback refreshAppearance,
  required VoidCallback onRealtimeForeground,
  required VoidCallback onRealtimeBackground,
}) {
  switch (state) {
    case AppLifecycleState.resumed:
      refreshAppearance();
      onRealtimeForeground();
      break;
    case AppLifecycleState.paused:
    case AppLifecycleState.detached:
    case AppLifecycleState.hidden:
      onRealtimeBackground();
      break;
    case AppLifecycleState.inactive:
      break;
  }
}

void logQuwoquanAppException({
  required String source,
  required String exceptionText,
  required String stackText,
}) {
  final traceStore = AppTraceContextStore.instance;
  final context = AppLogContext(
    sessionId: traceStore.sessionId,
    pageVisitId: traceStore.newPageVisitId(),
  );
  unawaited(
    AppLogService.instance.writeEvent(
      logType: AppLogType.error,
      level: AppLogLevel.error,
      context: context,
      payload: AppLogAppExceptionPayload(
        kind: 'app_exception',
        source: source,
        exception: exceptionText,
        stack: stackText,
      ).toMap(),
      hasError: true,
    ),
  );
  unawaited(
    AppExceptionTelemetryService.instance.recordGlobalException(
      source: source,
      exceptionText: exceptionText,
      stackText: stackText,
    ),
  );
  unawaited(
    AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.error,
      context: context,
      payload: AppLogPageRouteExceptionPayload(
        event: 'exception',
        route: 'app',
        pageName: 'app',
        source: source,
        exception: exceptionText,
      ).toMap(),
      summaryPayload: AppLogPageRouteExceptionSummaryPayload(
        event: 'exception',
        route: 'app',
        source: source,
      ).toMap(),
      hasError: true,
    ),
  );
}

Widget wrapWithQuwoquanAppAppearance({
  required BuildContext context,
  required AppearanceSnapshot snapshot,
  required Widget child,
}) {
  return AnnotatedRegion<SystemUiOverlayStyle>(
    value: AppTheme.systemUiOverlayStyleFor(snapshot.effectiveBrightness),
    child: MediaQuery(
      data: MediaQuery.of(context).copyWith(
        textScaler: TextScaler.linear(snapshot.textScaleFactor),
        boldText: false,
        highContrast: false,
      ),
      child: child,
    ),
  );
}

/// 根组件：冷启动先直出轻量欢迎页，首帧后再并行恢复会话、装配路由与预热首页。
class QuWoQuanAppRoot extends ConsumerStatefulWidget {
  const QuWoQuanAppRoot({super.key, this.startupPrerequisites});

  /// Runtime prerequisites that must start before media clients but must not
  /// block the Flutter welcome first frame.
  final Future<void>? startupPrerequisites;

  @override
  ConsumerState<QuWoQuanAppRoot> createState() => _QuWoQuanAppRootState();
}

class _QuWoQuanAppRootState extends ConsumerState<QuWoQuanAppRoot>
    with WidgetsBindingObserver {
  static const int _maxStartupWelcomeReplayCount = 2;
  static const Duration _startupPrerequisiteBudget = Duration(
    milliseconds: 2500,
  );

  bool _routerEnabled = false;
  bool _startupShellReady = false;
  int _startupWelcomeReplayIndex = 0;
  late final StartupInitScheduler _startupInitScheduler;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _startupInitScheduler = StartupInitScheduler(
      ref: ref,
      logException: logQuwoquanAppException,
      startupPrerequisites: widget.startupPrerequisites,
      startupPrerequisiteBudget: _startupPrerequisiteBudget,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      AppStartupRuntime.instance.markFirstFramePainted();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    handleQuwoquanAppLifecycleState(
      state: state,
      refreshAppearance: () =>
          ref.read(appearanceSettingsControllerProvider.notifier).refresh(),
      onRealtimeForeground: () {
        ref.read(realtimeConnectionManagerProvider.notifier).onAppForeground();
        unawaited(_refreshAuthSessionOnForegroundIfNeeded());
      },
      onRealtimeBackground: () => ref
          .read(realtimeConnectionManagerProvider.notifier)
          .onAppBackground(),
    );
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
    final platform = ref.watch(platformTargetProvider);

    if (platform == AppPlatform.web) {
      if (!_routerEnabled) {
        return _buildStartupWelcomeApp(startupWelcomeAppearanceSnapshot());
      }
      final snapshot = ref.watch(appearanceSnapshotProvider);
      return _buildMainShellApp(snapshot);
    }

    if (!_routerEnabled) {
      return _buildStartupWelcomeApp(startupWelcomeAppearanceSnapshot());
    }

    final snapshot = ref.watch(appearanceSnapshotProvider);
    final router = _watchRouterOrNull();
    if (router == null) {
      return _buildStartupFallbackApp(snapshot);
    }

    return _buildMainShellApp(snapshot);
  }

  Widget _buildMainShellApp(AppearanceSnapshot snapshot) {
    final router = _watchRouterOrNull();
    if (router == null) {
      return _buildStartupFallbackApp(snapshot);
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
            child: child ?? const SizedBox.shrink(),
          ),
        ),
      ),
    );
  }

  Widget _buildStartupWelcomeApp(AppearanceSnapshot snapshot) {
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
        key: ValueKey('startup-welcome-$_startupWelcomeReplayIndex'),
        deferSequenceStart: true,
        onWelcomeVisible: _onWelcomeVisible,
        startupLoading: _startupWelcomeReplayIndex > 0
            ? const WelcomeStartupLoadingState(
                title: '',
                subtitle: '',
                hint: UITextConstants.startupStillStartingInline,
              )
            : null,
        onSequenceComplete: _handleStartupWelcomeSequenceComplete,
        onFinish: _completeStartupWelcome,
      ),
    );
  }

  void _onWelcomeVisible() {
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
    _startupInitScheduler.onWelcomeVisible(onShellReady: _setStartupShellReady);
  }

  void _onWelcomeCompletedInit() {
    _startupInitScheduler.onWelcomeCompleted();
  }

  void _handleStartupWelcomeSequenceComplete() {
    if (_startupShellReady ||
        _startupWelcomeReplayIndex >= _maxStartupWelcomeReplayCount) {
      _completeStartupWelcome(degraded: !_startupShellReady);
      return;
    }

    final nextReplayIndex = _startupWelcomeReplayIndex + 1;
    AppStartupRuntime.instance.recordStartupPhase(
      (provider) => ref.read(provider),
      phase: 'welcome_replay',
      eventName: 'startup_welcome_sequence',
      properties: <String, dynamic>{
        'replayIndex': nextReplayIndex,
        'replayCount': nextReplayIndex,
        'hintVisible': true,
        'copyKey': 'startupStillStartingInline',
        'hintHeightPx': AppSpacing.radiusTwentyFour,
        'result': 'replay',
      },
    );

    if (mounted) {
      setState(() => _startupWelcomeReplayIndex = nextReplayIndex);
    } else {
      _startupWelcomeReplayIndex = nextReplayIndex;
    }
  }

  void _completeStartupWelcome({bool degraded = false}) {
    if (_routerEnabled) {
      return;
    }
    _onWelcomeCompletedInit();
    unawaited(_enableRouterAfterWelcome(degraded: degraded));
  }

  Future<void> _enableRouterAfterWelcome({required bool degraded}) async {
    if (!mounted || _routerEnabled) {
      return;
    }
    ref.read(welcomeCompletedProvider.notifier).setCompleted(true);
    AppStartupRuntime.instance.recordStartupPhase(
      (provider) => ref.read(provider),
      phase: 'welcome_completed',
      eventName: 'startup_welcome_sequence',
      properties: <String, dynamic>{
        'replayIndex': _startupWelcomeReplayIndex,
        'replayCount': _startupWelcomeReplayIndex,
        'hintVisible': _startupWelcomeReplayIndex > 0,
        'copyKey': 'startupStillStartingInline',
        'hintHeightPx': _startupWelcomeReplayIndex > 0
            ? AppSpacing.radiusTwentyFour
            : 0,
        'result': degraded ? 'degraded' : 'entered',
      },
    );
    setState(() => _routerEnabled = true);
    try {
      await ensureAppRouterLibraryLoaded();
      await AppStartupRuntime.instance.hydrateNativeProcessSegments();
    } catch (e, stack) {
      logQuwoquanAppException(
        source: 'startup_router_library',
        exceptionText: e.toString(),
        stackText: stack.toString(),
      );
    }
    if (!mounted) {
      return;
    }
    setState(() {});
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      AppStartupRuntime.instance.recordStartupPhase(
        (provider) => ref.read(provider),
        phase: 'main_shell_first_paint',
      );
    });
  }

  GoRouter? _watchRouterOrNull() {
    if (!isAppRouterLibraryLoaded) {
      return null;
    }
    try {
      return ref.watch(deferredAppRouterProvider);
    } catch (e, stack) {
      logQuwoquanAppException(
        source: 'startup_router_build',
        exceptionText: e.toString(),
        stackText: stack.toString(),
      );
      return null;
    }
  }

  Widget _buildStartupFallbackApp(AppearanceSnapshot snapshot) {
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
      home: AppScaffold(
        body: AppPageErrorState(
          semantic: UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: UITextConstants.pageLoadFailedTitle,
            message: UITextConstants.pageLoadFailedMessage,
            copyKey: 'pageLoadFailedTitle',
            presentation: UiErrorPresentation.emptyPage,
            tone: UiErrorTone.caution,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: UITextConstants.tryAgain,
            ),
          ),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry && mounted) {
              setState(() {});
            }
          },
        ),
      ),
    );
  }

  Future<void> _refreshAuthSessionOnForegroundIfNeeded() async {
    final controller = ref.read(authSessionControllerProvider.notifier);
    final session = ref.read(authSessionControllerProvider);
    if (!session.isAuthenticated) {
      return;
    }
    final refreshed = await controller.refreshIfSessionLooksStale();
    if (!mounted) {
      return;
    }
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      ref.read(welcomeCompletedProvider.notifier).setCompleted(true);
      if (!isAppRouterLibraryLoaded) {
        return;
      }
      final router = ref.read(deferredAppRouterProvider);
      final currentLocation = router.routerDelegate.currentConfiguration.uri
          .toString();
      router.go(
        buildLoginRouteLocation(
          reasonName: AuthPromptReason.sessionExpired.name,
          redirect: currentLocation,
          dismissFallback: currentLocation,
          allowGuestDismissPop: false,
        ),
      );
      return;
    }
    if (!refreshed) {
      await controller.markForegroundAuthCheck();
    }
  }
}
