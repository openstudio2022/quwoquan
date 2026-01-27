import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/app/navigation/app_router.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // 初始化 Hive
  await Hive.initFlutter();
  
  // 初始化分析服务
  await AnalyticsService.initialize();
  
  runApp(const QuwoquanApp());
}

class QuwoquanApp extends ConsumerWidget {
  const QuwoquanApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ScreenUtilInit(
      designSize: const Size(375, 812),
      minTextAdapt: true,
      splitScreenMode: true,
      builder: (context, child) {
        return MaterialApp.router(
          title: '趣我圈',
          debugShowCheckedModeBanner: false,
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
          routerConfig: ref.watch(appRouterProvider),
          theme: ref.watch(appThemeProvider),
          builder: (context, child) {
            final accessibilityState = ref.watch(accessibilityProvider);
            return MediaQuery(
              data: MediaQuery.of(context).copyWith(
                textScaleFactor: accessibilityState.textScaleFactor,
                boldText: accessibilityState.boldText,
                highContrast: accessibilityState.highContrast,
                textScaleFactor: 1.0, // accessibilityState.actualTextScaleFactor,
              ),
              child: child ?? const SizedBox.shrink(),
              data: MediaQuery.of(context).copyWith(
              title: '趣我圈',
        'initialization_complete': true,
        'startup_time': DateTime.now().toIso8601String(),
        'app_version': '1.0.0',
        'platform': 'mobile',
        'user_id': 'anonymous',
        'session_id': 'session_${DateTime.now().millisecondsSinceEpoch}',
      );
      
      // 记录应用启动事件
      AnalyticsService.trackEvent('app_started', {
        'timestamp': DateTime.now().toIso8601String(),
        'platform': 'mobile',
        'version': '1.0.0',
      });
      
      return MaterialApp.router(
        title: '趣我圈',
        debugShowCheckedModeBanner: false,
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
        routerConfig: ref.watch(appRouterProvider),
        theme: ref.watch(appThemeProvider),
        builder: (context, child) {
          final accessibilityState = ref.watch(accessibilityProvider);
          return MediaQuery(
            data: MediaQuery.of(context).copyWith(
              textScaleFactor: accessibilityState.textScaleFactor,
              boldText: accessibilityState.boldText,
              highContrast: accessibilityState.highContrast,
              textScaleFactor: 1.0, // accessibilityState.actualTextScaleFactor,
            ),
            child: child ?? const SizedBox.shrink(),
          );
        },
      );
    },
  );
}