// ignore_for_file: unnecessary_import, unnecessary_overrides

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/app_router.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_app_exception_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_page_route_exception_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_page_route_exception_summary.g.dart';
import 'package:quwoquan_app/core/design_system/theme/app_theme.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/l10n/l10n.dart';

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
  );
  unawaited(
    AppExceptionTelemetryService.instance.recordGlobalException(
      source: source,
      exceptionText: exceptionText,
      stackText: stackText,
    ),
  );
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

/// 根组件：单一 [MaterialApp.router]（含 /welcome 与主壳），与 [AppPageAccessNavigatorObserver] 同源埋点。
class QuWoQuanAppRoot extends ConsumerStatefulWidget {
  const QuWoQuanAppRoot({super.key});

  @override
  ConsumerState<QuWoQuanAppRoot> createState() => _QuWoQuanAppRootState();
}

class _QuWoQuanAppRootState extends ConsumerState<QuWoQuanAppRoot>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

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
        ref.read(appearanceSettingsControllerProvider.notifier).refresh();
        break;
      case AppLifecycleState.paused:
      case AppLifecycleState.inactive:
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
        break;
    }
  }

  @override
  void didChangeLocales(List<Locale>? locales) {
    super.didChangeLocales(locales);
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

  Future<void> _initializeApp() async {
    try {
      await ref
          .read(appearanceSettingsControllerProvider.notifier)
          .ensureLoaded();
      ref
          .read(themeProvider.notifier)
          .updateSystemBrightness(
            WidgetsBinding.instance.platformDispatcher.platformBrightness,
          );
    } catch (e) {
      // 初始化错误由上层观测处理
    }
  }

  @override
  Widget build(BuildContext context) {
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
          ref
              .read(responsiveProvider.notifier)
              .updateFromMediaQueryData(mediaQuery);
          ref
              .read(accessibilityProvider.notifier)
              .updateFromMediaQueryData(mediaQuery);
          ref
              .read(themeProvider.notifier)
              .updateSystemBrightness(
                WidgetsBinding.instance.platformDispatcher.platformBrightness,
              );
        });
        return wrapWithQuwoquanAppAppearance(
          context: context,
          snapshot: snapshot,
          child: child ?? const SizedBox.shrink(),
        );
      },
    );
  }
}
