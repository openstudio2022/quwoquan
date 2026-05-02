import 'dart:async';
import 'dart:isolate';
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/quwoquan_app_shell.dart';
import 'package:shared_preferences/shared_preferences.dart';

RawReceivePort? _rootIsolateErrorPort;

/// 共享启动：默认入口 [main] 与 [main_prod] 均经此函数，后者可注入 [providerScopeOverrides]。
Future<void> runQuwoquanApp({
  List<Override> providerScopeOverrides = const [],
}) async {
  WidgetsFlutterBinding.ensureInitialized();
  assert(() {
    debugPaintSizeEnabled = false;
    debugPaintBaselinesEnabled = false;
    debugPaintPointersEnabled = false;
    debugPaintLayerBordersEnabled = false;
    debugRepaintRainbowEnabled = false;
    return true;
  }());
  final previousFlutterErrorHandler = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    // Flutter 框架已知 bug：semantics tree 在 layout 未完成时被访问。
    // 仅在 debug 模式触发，release 不受影响。
    // 参考：https://github.com/flutter/flutter/issues/153692
    //       https://github.com/flutter/flutter/issues/81182
    final message = details.exceptionAsString();
    if (message.contains('_needsLayout') &&
        message.contains('childSemantics.renderObject')) {
      return;
    }
    if (previousFlutterErrorHandler != null) {
      previousFlutterErrorHandler(details);
    } else {
      FlutterError.presentError(details);
    }
    logQuwoquanAppException(
      source: 'flutter_error',
      exceptionText: details.exceptionAsString(),
      stackText: details.stack?.toString() ?? '',
    );
  };
  final previousPlatformDispatcherHandler = PlatformDispatcher.instance.onError;
  PlatformDispatcher.instance.onError = (Object error, StackTrace stack) {
    logQuwoquanAppException(
      source: 'platform_dispatcher',
      exceptionText: error.toString(),
      stackText: stack.toString(),
    );
    if (previousPlatformDispatcherHandler != null) {
      return previousPlatformDispatcherHandler(error, stack);
    }
    return false;
  };
  _installRootIsolateErrorListener();

  SystemChrome.setSystemUIOverlayStyle(
    AppTheme.systemUiOverlayStyleFor(Brightness.light),
  );

  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
  ]);

  await Hive.initFlutter();
  await Hive.openBox<String>(kVisitRecordsBoxName);
  unawaited(AppExceptionTelemetryService.instance.flushPending());

  await preInitializeQuwoquanAnalytics();

  WidgetsBinding.instance.addObserver(_AppExceptionLifecycleObserver());
  runZonedGuarded(
    () {
      runApp(
        ScreenUtilInit(
          designSize: const Size(375, 812),
          minTextAdapt: true,
          splitScreenMode: true,
          child: ProviderScope(
            overrides: providerScopeOverrides,
            child: const QuWoQuanAppRoot(),
          ),
        ),
      );
    },
    (Object error, StackTrace stack) {
      logQuwoquanAppException(
        source: 'zone_guarded',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    },
  );
}

void _installRootIsolateErrorListener() {
  if (_rootIsolateErrorPort != null) {
    return;
  }
  final port = RawReceivePort((Object? message) {
    if (message is List<Object?> && message.isNotEmpty) {
      final error = message.first;
      final Object? stack = message.length > 1 ? message[1] : '';
      logQuwoquanAppException(
        source: 'root_isolate',
        exceptionText: error.toString(),
        stackText: stack.toString(),
      );
    }
  });
  _rootIsolateErrorPort = port;
  Isolate.current.addErrorListener(port.sendPort);
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

/// 预先初始化 Analytics（与 Hive 后、首帧前执行）。
Future<void> preInitializeQuwoquanAnalytics() async {
  try {
    final container = ProviderContainer();
    final analyticsService = container.read(analyticsProvider);
    final analyticsConfig = container.read(analyticsConfigProvider);

    await analyticsService.initialize(analyticsConfig);

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
