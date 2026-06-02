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
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/quwoquan_app_shell.dart';

RawReceivePort? _rootIsolateErrorPort;

/// 共享启动：默认入口 [main] 与 [main_prod] 均经此函数，后者可注入 [providerScopeOverrides]。
///
/// [WidgetsFlutterBinding.ensureInitialized] 与 [runApp] 必须在同一 Zone 内调用，
/// 否则 debug 下会触发 `Zone mismatch`（见 [BindingBase.debugCheckZone]）。
Future<void> runQuwoquanApp({
  List<Override> providerScopeOverrides = const [],
}) async {
  await runZonedGuarded(
    () async {
      WidgetsFlutterBinding.ensureInitialized();
      AppStartupRuntime.instance.markBootstrapStarted();
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
      final previousPlatformDispatcherHandler =
          PlatformDispatcher.instance.onError;
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

      unawaited(
        SystemChrome.setPreferredOrientations([
          DeviceOrientation.portraitUp,
          DeviceOrientation.portraitDown,
          DeviceOrientation.landscapeLeft,
          DeviceOrientation.landscapeRight,
        ]),
      );

      WidgetsBinding.instance.addObserver(_AppExceptionLifecycleObserver());
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
  if (kIsWeb) {
    return;
  }
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
