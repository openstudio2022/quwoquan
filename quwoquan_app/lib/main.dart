// ignore_for_file: unnecessary_import, unnecessary_overrides

import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'package:quwoquan_app/core/emoji/emoji_analytics.dart';
import 'package:quwoquan_app/core/emoji/emoji_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_engine_provider.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_trace_context_store.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_app/app/navigation/app_router.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/app/providers/welcome_state_provider.dart';
import 'package:quwoquan_app/ui/welcome/pages/welcome_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  FlutterError.onError = (FlutterErrorDetails details) {
    FlutterError.presentError(details);
    _logAppException(
      source: 'flutter_error',
      exceptionText: details.exceptionAsString(),
      stackText: details.stack?.toString() ?? '',
    );
  };
  PlatformDispatcher.instance.onError = (Object error, StackTrace stack) {
    _logAppException(
      source: 'platform_dispatcher',
      exceptionText: error.toString(),
      stackText: stack.toString(),
    );
    return false;
  };

  // 设置系统UI样式
  SystemChrome.setSystemUIOverlayStyle(
    AppTheme.systemUiOverlayStyleFor(Brightness.light),
  );

  // 设置屏幕方向
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
  ]);

  // 初始化Hive
  await Hive.initFlutter();
  await Hive.openBox<String>(kVisitRecordsBoxName);

  // 预先初始化AnalyticsService
  await _preInitializeAnalytics();

  runApp(
    ScreenUtilInit(
      designSize: const Size(375, 812), // iPhone X 设计尺寸
      minTextAdapt: true,
      splitScreenMode: true,
      child: const ProviderScope(child: QuWoQuanAppRoot()),
    ),
  );
}

void _logAppException({
  required String source,
  required String exceptionText,
  required String stackText,
}) {
  final traceStore = AppTraceContextStore.instance;
  final context = AppLogContext(
    sessionId: traceStore.sessionId,
    journeyId: traceStore.journeyId,
    pageVisitId: traceStore.newPageVisitId(),
  );
  AppLogService.instance.writeEvent(
    logType: AppLogType.error,
    level: AppLogLevel.error,
    context: context,
    payload: <String, dynamic>{
      'kind': 'app_exception',
      'source': source,
      'exception': exceptionText,
      'stack': stackText,
    },
    hasError: true,
  );
  AppLogService.instance.writeEvent(
    logType: AppLogType.pageAccess,
    level: AppLogLevel.error,
    context: context,
    payload: <String, dynamic>{
      'event': 'exception',
      'route': 'app',
      'pageName': 'app',
      'source': source,
      'exception': exceptionText,
    },
    summaryPayload: <String, dynamic>{
      'event': 'exception',
      'route': 'app',
      'source': source,
    },
    hasError: true,
  );
}

/// 预先初始化AnalyticsService
Future<void> _preInitializeAnalytics() async {
  try {
    // 创建临时的Provider容器来初始化AnalyticsService
    final container = ProviderContainer();
    final analyticsService = container.read(analyticsProvider);
    final analyticsConfig = container.read(analyticsConfigProvider);

    await analyticsService.initialize(analyticsConfig);

    // 记录应用启动事件
    await analyticsService.trackEvent(
      AnalyticsEvent(
        eventType: 'app_start',
        eventName: '应用启动',
        properties: {
          'startup_time': DateTime.now().toIso8601String(),
          'initialization_complete': true,
        },
      ),
    );

    // 每日 emoji 使用量埋点：当天首次启动后上报自上次以来的增量
    try {
      final prefs = await SharedPreferences.getInstance();
      final emojiRepo = EmojiRepository(prefs);
      await EmojiAnalytics.tryReportDaily(emojiRepo, analyticsService);
    } catch (e) {
      debugPrint('Emoji daily report failed: $e');
    }

    container.dispose();
  } catch (e) {
    debugPrint('Failed to pre-initialize analytics: $e');
  }
}

Widget _wrapWithAppAppearance({
  required BuildContext context,
  required AppearanceSnapshot snapshot,
  required Widget child,
}) {
  return AnnotatedRegion<SystemUiOverlayStyle>(
    value: AppTheme.systemUiOverlayStyleFor(snapshot.effectiveBrightness),
    child: MediaQuery(
      data: MediaQuery.of(context).copyWith(
        textScaler: TextScaler.linear(snapshot.textScaleFactor),
        boldText: snapshot.boldText,
        highContrast: snapshot.highContrast,
      ),
      child: child,
    ),
  );
}

/// 根组件：欢迎页完成后展示主应用
class QuWoQuanAppRoot extends ConsumerWidget {
  const QuWoQuanAppRoot({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final welcomeCompleted = ref.watch(welcomeCompletedProvider);
    final snapshot = ref.watch(appearanceSnapshotProvider);

    if (!welcomeCompleted) {
      return MaterialApp(
        title: '趣我圈',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.lightTheme,
        darkTheme: AppTheme.darkTheme,
        themeMode: snapshot.themeMode,
        builder: (context, child) => _wrapWithAppAppearance(
          context: context,
          snapshot: snapshot,
          child: child ?? const SizedBox.shrink(),
        ),
        home: WelcomeScreen(
          onFinish: () {
            ref.read(welcomeCompletedProvider.notifier).setCompleted(true);
          },
        ),
      );
    }

    return const QuWoQuanApp();
  }
}

class QuWoQuanApp extends ConsumerStatefulWidget {
  const QuWoQuanApp({super.key});

  @override
  ConsumerState<QuWoQuanApp> createState() => _QuWoQuanAppState();
}

class _QuWoQuanAppState extends ConsumerState<QuWoQuanApp>
    with WidgetsBindingObserver {
  bool _assistentApiStarted = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    // 初始化应用
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _initializeApp();
    });
  }

  @override
  void dispose() {
    if (_assistentApiStarted) {
      ref.read(assistentApiGatewayProvider).stop();
    }
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);

    switch (state) {
      case AppLifecycleState.resumed:
        ref.read(appearanceSettingsControllerProvider.notifier).refresh();
        break;
      case AppLifecycleState.paused:
        // 应用暂停时保存状态
        break;
      case AppLifecycleState.inactive:
        break;
      case AppLifecycleState.detached:
        break;
      case AppLifecycleState.hidden:
        break;
    }
  }

  @override
  void didChangeLocales(List<Locale>? locales) {
    super.didChangeLocales(locales);
    // 处理语言变化
  }

  @override
  void didChangeAccessibilityFeatures() {
    super.didChangeAccessibilityFeatures();
    final mediaQuery = MediaQuery.maybeOf(context);
    if (mediaQuery != null) {
      ref.read(accessibilityProvider.notifier).updateFromMediaQueryData(
            mediaQuery,
          );
    }
  }

  @override
  void didChangeTextScaleFactor() {
    super.didChangeTextScaleFactor();
    final mediaQuery = MediaQuery.maybeOf(context);
    if (mediaQuery != null) {
      ref.read(accessibilityProvider.notifier).updateFromMediaQueryData(
            mediaQuery,
          );
    }
  }

  @override
  void didChangePlatformBrightness() {
    super.didChangePlatformBrightness();
    ref.read(themeProvider.notifier).updateSystemBrightness(
          WidgetsBinding.instance.platformDispatcher.platformBrightness,
        );
  }

  Future<void> _initializeApp() async {
    try {
      await ref.read(assistantRuntimeProvider).ensureRemoteConfigLoaded();
      final enableAssistentApi =
          (const String.fromEnvironment(
            'PERSONAL_ASSISTENT_ENABLE_API',
          )).toLowerCase() ==
          'true';
      if (enableAssistentApi) {
        await ref.read(assistentApiGatewayProvider).start();
        _assistentApiStarted = true;
      }
      await ref.read(appearanceSettingsControllerProvider.notifier).ensureLoaded();
      ref.read(themeProvider.notifier).updateSystemBrightness(
            WidgetsBinding.instance.platformDispatcher.platformBrightness,
          );
    } catch (e) {
      // 处理初始化错误
      // ref.read(appStateProvider.notifier).setError('应用初始化失败: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer(
      builder: (context, ref, child) {
        final router = ref.watch(appRouterProvider);
        final snapshot = ref.watch(appearanceSnapshotProvider);

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
          builder: (context, child) {
            final mediaQuery = MediaQuery.of(context);
            WidgetsBinding.instance.addPostFrameCallback((_) {
              ref.read(responsiveProvider.notifier).updateFromMediaQueryData(
                    mediaQuery,
                  );
              ref.read(accessibilityProvider.notifier).updateFromMediaQueryData(
                    mediaQuery,
                  );
              ref.read(themeProvider.notifier).updateSystemBrightness(
                    WidgetsBinding.instance.platformDispatcher.platformBrightness,
                  );
            });
            return _wrapWithAppAppearance(
              context: context,
              snapshot: snapshot,
              child: child ?? const SizedBox.shrink(),
            );
          },
        );
      },
    );
  }
}
