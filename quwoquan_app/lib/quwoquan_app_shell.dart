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
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_app_exception_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_page_route_exception_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_page_route_exception_summary.g.dart';
import 'package:quwoquan_app/core/design_system/theme/app_theme.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show appLogUploaderProvider, realtimeConnectionManagerProvider;
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
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
  const QuWoQuanAppRoot({super.key});

  @override
  ConsumerState<QuWoQuanAppRoot> createState() => _QuWoQuanAppRootState();
}

class _QuWoQuanAppRootState extends ConsumerState<QuWoQuanAppRoot>
    with WidgetsBindingObserver {
  bool _startupWarmupStarted = false;
  bool _routerEnabled = false;
  AuthPromptReason? _pendingStartupLoginReason;

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
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    handleQuwoquanAppLifecycleState(
      state: state,
      refreshAppearance: () =>
          ref.read(appearanceSettingsControllerProvider.notifier).refresh(),
      onRealtimeForeground: () =>
          ref.read(realtimeConnectionManagerProvider.notifier).onAppForeground(),
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
      // 2. 首帧后并行启动 auth 恢复、外观设置、日志上传、首页 feed 预热。
      // 3. 欢迎结束后再装配完整路由，此时首页可直接消费已预热数据。
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

  @override
  Widget build(BuildContext context) {
    final snapshot = ref.watch(appearanceSnapshotProvider);
    final platform = ref.watch(platformTargetProvider);

    if (platform == AppPlatform.web) {
      return _buildWebStartupApp(snapshot);
    }

    if (!_routerEnabled) {
      return _buildStartupWelcomeApp(snapshot);
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

  Widget _buildStartupWelcomeApp(AppearanceSnapshot snapshot) {
    final loginPrompt = _startupWarmupStarted
        ? _startupLoginPromptConfig(ref.watch(authSessionControllerProvider))
        : null;
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
        loginPrompt: loginPrompt,
        onFinish: _completeStartupWelcome,
      ),
    );
  }

  WelcomeLoginPromptConfig? _startupLoginPromptConfig(AuthSessionState auth) {
    final reason = auth.promptReason;
    if (auth.status != AuthSessionStatus.guest ||
        reason == null ||
        reason == AuthPromptReason.actionRequired ||
        reason == AuthPromptReason.sessionExpired) {
      return null;
    }
    return WelcomeLoginPromptConfig(
      title: UITextConstants.welcomeLoginPromptTitle,
      subtitle: UITextConstants.welcomeLoginPromptSubtitle,
      onLogin: () {
        _completeStartupWelcome(loginReason: reason);
      },
      onContinueAsGuest: () async {
        await ref
            .read(authSessionControllerProvider.notifier)
            .continueAsGuest();
        if (!mounted) {
          return;
        }
        _completeStartupWelcome();
      },
    );
  }

  void _completeStartupWelcome({AuthPromptReason? loginReason}) {
    if (_routerEnabled) {
      return;
    }
    _pendingStartupLoginReason = loginReason;
    ref.read(welcomeCompletedProvider.notifier).setCompleted(true);
    AppStartupRuntime.instance.scheduleHomeReadyReport(
      (provider) => ref.read(provider),
    );
    if (mounted) {
      setState(() => _routerEnabled = true);
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
}
