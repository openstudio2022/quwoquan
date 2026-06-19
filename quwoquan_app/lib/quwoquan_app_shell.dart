// ignore_for_file: unnecessary_import, unnecessary_overrides

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/app/navigation/app_router.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/app/providers/welcome_state_provider.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_app_exception_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_page_route_exception_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_page_route_exception_summary.g.dart';
import 'package:quwoquan_app/components/navigation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/core/design_system/theme/app_theme.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show
        appDataSourceModeProvider,
        AppRemoteConfigState,
        appLogUploaderProvider,
        appRemoteConfigProvider,
        homeChannelsProvider,
        realtimeConnectionManagerProvider;
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
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

class _StartupEntryGateState {
  const _StartupEntryGateState({
    required this.readyToEnter,
    required this.canWarmHomeFeed,
    required this.homeChannelId,
    this.loadingState,
    this.homeFeedError,
  });

  final bool readyToEnter;
  final bool canWarmHomeFeed;
  final String homeChannelId;
  final WelcomeStartupLoadingState? loadingState;
  final Object? homeFeedError;
}

/// 根组件：冷启动先直出轻量欢迎页，首帧后再并行恢复会话、装配路由与预热首页。
class QuWoQuanAppRoot extends ConsumerStatefulWidget {
  const QuWoQuanAppRoot({super.key});

  @override
  ConsumerState<QuWoQuanAppRoot> createState() => _QuWoQuanAppRootState();
}

class _QuWoQuanAppRootState extends ConsumerState<QuWoQuanAppRoot>
    with WidgetsBindingObserver {
  static const Duration _startupSlowHintDelay = Duration(seconds: 3);

  bool _startupWarmupStarted = false;
  bool _routerEnabled = false;
  bool _welcomeSequenceCompleted = false;
  bool _startupCompletionQueued = false;
  bool _startupSlowHintVisible = false;
  bool _startupHomeWarmupRequested = false;
  String? _startupHomeChannelId;
  AuthPromptReason? _pendingStartupLoginReason;
  Timer? _startupSlowHintTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      AppStartupRuntime.instance.markFirstFramePainted();
      _initializeApp();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _startupSlowHintTimer?.cancel();
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
      onRealtimeBackground: () =>
          ref.read(realtimeConnectionManagerProvider.notifier).onAppBackground(),
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

  void _initializeApp() {
    try {
      _syncWindowDerivedState();
      ref
          .read(themeProvider.notifier)
          .updateSystemBrightness(
            WidgetsBinding.instance.platformDispatcher.platformBrightness,
          );
      // 串并行关系：
      // 1. 首帧只渲染轻量欢迎页，不创建 GoRouter，也不读取本地登录态。
      // 2. 首帧后并行启动 auth 恢复、外观设置、日志上传与云端连接。
      // 3. 欢迎动效期间完成首页真实频道预热，未就绪则继续停留在欢迎页。
      // 4. 只有首页进入 ready 后才装配完整路由，避免切入主壳时再出现首屏抖动。
      ref.read(authSessionControllerProvider);
      ref.read(appLogUploaderProvider);
      ref.read(realtimeConnectionManagerProvider.notifier).onAppForeground();
      unawaited(
        ref.read(appearanceSettingsControllerProvider.notifier).ensureLoaded(),
      );
      AppStartupRuntime.instance.schedulePostFirstFrameWarmup(
        (provider) => ref.read(provider),
      );
      if (mounted && !_startupWarmupStarted) {
        setState(() => _startupWarmupStarted = true);
      }
    } catch (e) {
      // 初始化错误由上层观测处理
    }
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
  }

  void _onWelcomeSequenceComplete() {
    if (_welcomeSequenceCompleted || !mounted) {
      return;
    }
    setState(() {
      _welcomeSequenceCompleted = true;
      _startupSlowHintVisible = false;
    });
    _startupSlowHintTimer?.cancel();
    _startupSlowHintTimer = Timer(_startupSlowHintDelay, () {
      if (!mounted || _routerEnabled) {
        return;
      }
      setState(() => _startupSlowHintVisible = true);
    });
  }

  String _resolveStartupHomeChannelId(List<HomeChannelConfig> channels) {
    if (channels.isEmpty) {
      return HomePrimaryTabStrip.recommendedChannelId;
    }
    for (final channel in channels) {
      if (channel.id == HomePrimaryTabStrip.recommendedChannelId) {
        return channel.id;
      }
    }
    return channels.first.id;
  }

  void _maybeRequestStartupHomeWarmup({
    required bool canWarmHomeFeed,
    required String channelId,
  }) {
    if (!canWarmHomeFeed) {
      return;
    }
    if (_startupHomeWarmupRequested && _startupHomeChannelId == channelId) {
      return;
    }
    _startupHomeWarmupRequested = true;
    _startupHomeChannelId = channelId;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _routerEnabled) {
        return;
      }
      unawaited(_warmStartupHomeFeed(channelId, force: true));
    });
  }

  Future<void> _warmStartupHomeFeed(
    String channelId, {
    required bool force,
  }) async {
    try {
      await ref.read(discoveryFeedMapProvider.notifier).load(
            channelId,
            force: force,
          );
      final warmed = ref.read(discoveryFeedMapProvider)[channelId]?.asData?.value;
      if (warmed != null && !warmed.isLoading && warmed.blockingError == null) {
        AppStartupRuntime.instance.markHomeFeedWarm();
      }
    } catch (_) {
      // 首页预热失败时继续留在欢迎页等待用户重试，不让首帧抖动回主壳。
    }
  }

  Future<void> _retryStartupPreparation(String channelId) async {
    if (!mounted) {
      return;
    }
    setState(() => _startupSlowHintVisible = false);
    _startupSlowHintTimer?.cancel();
    _startupSlowHintTimer = Timer(_startupSlowHintDelay, () {
      if (!mounted || _routerEnabled) {
        return;
      }
      setState(() => _startupSlowHintVisible = true);
    });
    unawaited(
      ref.read(appearanceSettingsControllerProvider.notifier).ensureLoaded(),
    );
    await ref.read(appRemoteConfigProvider.notifier).refresh();
    await _warmStartupHomeFeed(channelId, force: true);
  }

  _StartupEntryGateState _buildStartupEntryGate({
    required AuthSessionState auth,
    required AppearanceSettingsState appearance,
    required AppDataSourceMode dataSourceMode,
    required AppRemoteConfigState remoteConfig,
    required List<HomeChannelConfig> homeChannels,
    required Map<String, AsyncValue<DiscoveryFeedState>> feedMap,
    required WelcomeLoginPromptConfig? loginPrompt,
  }) {
    final authReady = auth.status != AuthSessionStatus.restoring;
    final cloudReady =
        appearance.hasLoaded &&
        (dataSourceMode != AppDataSourceMode.remote ||
            (!remoteConfig.isHydrating && !remoteConfig.isRefreshing));
    final homeChannelId = _resolveStartupHomeChannelId(homeChannels);
    final homeFeedState = feedMap[homeChannelId]?.asData?.value;
    final homeFeedError =
        _startupHomeWarmupRequested ? homeFeedState?.blockingError : null;
    final homeReady =
        _startupHomeWarmupRequested &&
        _startupHomeChannelId == homeChannelId &&
        homeFeedState != null &&
        !homeFeedState.isLoading &&
        homeFeedState.blockingError == null;
    final readyToEnter =
        authReady &&
        cloudReady &&
        homeReady &&
        loginPrompt == null &&
        _welcomeSequenceCompleted;

    final stages = <WelcomeStartupStageState>[
      WelcomeStartupStageState(
        label: UITextConstants.welcomeStartupStageAuth,
        status: authReady
            ? WelcomeStartupStageStatus.complete
            : WelcomeStartupStageStatus.running,
      ),
      WelcomeStartupStageState(
        label: UITextConstants.welcomeStartupStageCloud,
        status: cloudReady
            ? WelcomeStartupStageStatus.complete
            : WelcomeStartupStageStatus.running,
      ),
      WelcomeStartupStageState(
        label: UITextConstants.welcomeStartupStageHome,
        status: homeReady
            ? WelcomeStartupStageStatus.complete
            : homeFeedError != null
            ? WelcomeStartupStageStatus.failed
            : _startupHomeWarmupRequested
            ? WelcomeStartupStageStatus.running
            : WelcomeStartupStageStatus.pending,
      ),
    ];

    String subtitle = UITextConstants.welcomeStartupPreparingHome;
    if (!authReady) {
      subtitle = UITextConstants.welcomeStartupPreparingAuth;
    } else if (!cloudReady) {
      subtitle = UITextConstants.welcomeStartupPreparingCloud;
    }

    final loadingState = _welcomeSequenceCompleted
        ? WelcomeStartupLoadingState(
            title: UITextConstants.welcomeStartupLoadingTitle,
            subtitle: homeFeedError == null
                ? subtitle
                : UITextConstants.welcomeStartupPreparingHome,
            hint: homeFeedError != null
                ? UITextConstants.welcomeStartupRetryHint
                : _startupSlowHintVisible
                ? UITextConstants.welcomeStartupSlowHint
                : null,
            stages: stages,
            actionLabel: homeFeedError != null
                ? UITextConstants.welcomeStartupRetry
                : null,
            onAction: homeFeedError != null
                ? () => _retryStartupPreparation(homeChannelId)
                : null,
            isError: homeFeedError != null,
          )
        : null;

    return _StartupEntryGateState(
      readyToEnter: readyToEnter,
      canWarmHomeFeed: authReady && cloudReady,
      homeChannelId: homeChannelId,
      loadingState: loadingState,
      homeFeedError: homeFeedError,
    );
  }

  void _maybeCompleteStartupWelcome(_StartupEntryGateState startupGate) {
    if (_routerEnabled ||
        _startupCompletionQueued ||
        !startupGate.readyToEnter ||
        !_welcomeSequenceCompleted) {
      return;
    }
    _startupCompletionQueued = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _startupCompletionQueued = false;
      if (!mounted || _routerEnabled) {
        return;
      }
      _completeStartupWelcome();
    });
  }

  @override
  Widget build(BuildContext context) {
    final snapshot = ref.watch(appearanceSnapshotProvider);
    final platform = ref.watch(platformTargetProvider);
    WelcomeLoginPromptConfig? startupLoginPrompt;
    _StartupEntryGateState? startupGate;

    if (_startupWarmupStarted) {
      final dataSourceMode = ref.watch(appDataSourceModeProvider);
      final auth = ref.watch(authSessionControllerProvider);
      final appearance = ref.watch(appearanceSettingsControllerProvider);
      final remoteConfig = ref.watch(appRemoteConfigProvider);
      final homeChannels = ref.watch(homeChannelsProvider);
      final feedMap = ref.watch(discoveryFeedMapProvider);
      startupLoginPrompt = platform == AppPlatform.web
          ? null
          : _startupLoginPromptConfig(auth);
      startupGate = _buildStartupEntryGate(
        auth: auth,
        appearance: appearance,
        dataSourceMode: dataSourceMode,
        remoteConfig: remoteConfig,
        homeChannels: homeChannels,
        feedMap: feedMap,
        loginPrompt: startupLoginPrompt,
      );
      _maybeRequestStartupHomeWarmup(
        canWarmHomeFeed: startupGate.canWarmHomeFeed,
        channelId: startupGate.homeChannelId,
      );
      _maybeCompleteStartupWelcome(startupGate);
    }

    if (platform == AppPlatform.web) {
      return _buildWebStartupApp(snapshot);
    }

    if (!_routerEnabled) {
      return _buildStartupWelcomeApp(
        snapshot,
        loginPrompt: startupLoginPrompt,
        startupGate: startupGate,
      );
    }

    final router = ref.watch(appRouterProvider);

    return MaterialApp.router(
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
      builder: (context, child) => wrapWithQuwoquanAppAppearance(
        context: context,
        snapshot: snapshot,
        child: child ?? const SizedBox.shrink(),
      ),
    );
  }

  Widget _buildWebStartupApp(AppearanceSnapshot snapshot) {
    final router = ref.watch(appRouterProvider);
    return MaterialApp.router(
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
      builder: (context, child) => wrapWithQuwoquanAppAppearance(
        context: context,
        snapshot: snapshot,
        child: Stack(
          fit: StackFit.expand,
          children: [
            child ?? const SizedBox.shrink(),
            if (!_routerEnabled)
              WelcomeScreen(
                loginPrompt: null,
                deferSequenceStart: true,
                onFinish: _completeStartupWelcome,
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildStartupWelcomeApp(
    AppearanceSnapshot snapshot, {
    required WelcomeLoginPromptConfig? loginPrompt,
    required _StartupEntryGateState? startupGate,
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
      builder: (context, child) => wrapWithQuwoquanAppAppearance(
        context: context,
        snapshot: snapshot,
        child: child ?? const SizedBox.shrink(),
      ),
      home: WelcomeScreen(
        deferSequenceStart: true,
        loginPrompt: loginPrompt,
        onSequenceComplete: _onWelcomeSequenceComplete,
        startupLoading: startupGate?.loadingState,
        onFinish: _completeStartupWelcome,
      ),
    );
  }

  WelcomeLoginPromptConfig? _startupLoginPromptConfig(AuthSessionState auth) {
    final reason = auth.promptReason;
    if (auth.status != AuthSessionStatus.guest ||
        reason == null ||
        reason == AuthPromptReason.actionRequired) {
      return null;
    }
    return WelcomeLoginPromptConfig(
      title: reason == AuthPromptReason.sessionExpired
          ? UITextConstants.loginTitleReturn
          : UITextConstants.welcomeLoginPromptTitle,
      subtitle: reason == AuthPromptReason.sessionExpired
          ? UITextConstants.authSessionExpired
          : UITextConstants.welcomeLoginPromptSubtitle,
      onLogin: () {
        _completeStartupWelcome(loginReason: reason);
      },
      onContinueAsGuest: () async {
        await ref
            .read(authSessionControllerProvider.notifier)
            .continueAsGuest();
      },
    );
  }

  void _completeStartupWelcome({AuthPromptReason? loginReason}) {
    if (_routerEnabled) {
      return;
    }
    _startupSlowHintTimer?.cancel();
    _pendingStartupLoginReason = loginReason;
    ref.read(welcomeCompletedProvider.notifier).setCompleted(true);
    AppStartupRuntime.instance.scheduleHomeReadyReport(
      (provider) => ref.read(provider),
    );
    if (mounted) {
      setState(() {
        _routerEnabled = true;
        _startupSlowHintVisible = false;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final reason = _pendingStartupLoginReason;
        if (reason == null || !mounted) {
          return;
        }
        _pendingStartupLoginReason = null;
        // 启动态强入口：统一走 buildLoginRouteLocation（禁止 guest pop），
        // 关闭只安全回首页，避免裸拼 login 路由绕过防回环契约。
        ref.read(appRouterProvider).go(
          buildLoginRouteLocation(
            reasonName: reason.name,
            allowGuestDismissPop: false,
          ),
        );
      });
    }
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
      final router = ref.read(appRouterProvider);
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
