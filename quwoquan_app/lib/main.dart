// ignore_for_file: unnecessary_import, unnecessary_overrides

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'package:quwoquan_app/core/emoji/emoji_analytics.dart';
import 'package:quwoquan_app/core/emoji/emoji_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_app/app/navigation/app_router.dart';
import 'package:quwoquan_app/app/providers/welcome_state_provider.dart';
import 'package:quwoquan_app/features/welcome/pages/welcome_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // 设置系统UI样式
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.dark,
      systemNavigationBarColor: Colors.transparent,
      systemNavigationBarIconBrightness: Brightness.dark,
    ),
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

/// 预先初始化AnalyticsService
Future<void> _preInitializeAnalytics() async {
  try {
    // 创建临时的Provider容器来初始化AnalyticsService
    final container = ProviderContainer();
    final analyticsService = container.read(analyticsProvider);
    final analyticsConfig = container.read(analyticsConfigProvider);
    
    await analyticsService.initialize(analyticsConfig);
    
    // 记录应用启动事件
    await analyticsService.trackEvent(AnalyticsEvent(
      eventType: 'app_start',
      eventName: '应用启动',
      properties: {
        'startup_time': DateTime.now().toIso8601String(),
        'initialization_complete': true,
      },
    ));

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

/// 根组件：欢迎页完成后展示主应用
class QuWoQuanAppRoot extends ConsumerWidget {
  const QuWoQuanAppRoot({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final welcomeCompleted = ref.watch(welcomeCompletedProvider);

    if (!welcomeCompleted) {
      return MaterialApp(
        title: '趣我圈',
        debugShowCheckedModeBanner: false,
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

class _QuWoQuanAppState extends ConsumerState<QuWoQuanApp> with WidgetsBindingObserver {
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
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    
    switch (state) {
      case AppLifecycleState.resumed:
        // 应用恢复时更新最后活跃时间
        // ref.read(appStateProvider.notifier).updateLastActiveTime();
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
    // 更新无障碍设置
    // ref.read(accessibilityProvider.notifier).updateFromSystemSettings(context);
  }

  @override
  void didChangeTextScaleFactor() {
    super.didChangeTextScaleFactor();
    // 更新文本缩放因子
    // final mediaQuery = MediaQuery.of(context);
    // ref.read(accessibilityProvider.notifier).setTextScaleFactor(mediaQuery.textScaleFactor);
  }

  @override
  void didChangePlatformBrightness() {
    super.didChangePlatformBrightness();
    // 更新主题
    // ref.read(themeProvider.notifier).updateSystemTheme();
  }

  Future<void> _initializeApp() async {
    try {
      // 初始化应用状态
      // await ref.read(appStateProvider.notifier).initialize();
      
      // 更新响应式状态
      // ref.read(responsiveProvider.notifier).updateState(context);
      
      // 更新无障碍设置
      // ref.read(accessibilityProvider.notifier).updateFromSystemSettings(context);
      
      // 更新主题
      // ref.read(themeProvider.notifier).updateSystemTheme();
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
        final themeState = ref.watch(themeProvider);
        final accessibilityState = ref.watch(accessibilityProvider);
        
        // 创建主题数据
        final themeData = themeState.isDark ? AppTheme.darkTheme : AppTheme.lightTheme;

    return MaterialApp.router(
          title: '趣我圈',
      debugShowCheckedModeBanner: false,
      theme: themeData,
      darkTheme: themeData,
      themeMode: themeState.isDark ? ThemeMode.dark : ThemeMode.light,
      routerConfig: router,
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [
        Locale('zh', 'CN'),
        Locale('en', 'US'),
      ],
      locale: const Locale('zh', 'CN'),
      builder: (context, child) {
        // 监听MediaQuery变化，更新响应式状态
        WidgetsBinding.instance.addPostFrameCallback((_) {
              // ref.read(responsiveProvider.notifier).updateState(context);
        });
        
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(
            textScaler: const TextScaler.linear(1.0), // accessibilityState.actualTextScaleFactor,
            boldText: accessibilityState.boldText,
            highContrast: accessibilityState.highContrast,
          ),
          child: child ?? const SizedBox.shrink(),
        );
      },
    );
      },
    );
  }
}