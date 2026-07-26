import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/core/telemetry/app_page_experience_tracker.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';

/// 页面访问同时写入脱敏本地诊断与统一产品遥测。两者没有上传继承关系：本地
/// AppLog 永不自动转发，云端只接收 codegen 目录允许的强类型事件。
Future<void> writeAppPageAccessOpen({
  required String location,
  required String pageVisitId,
  DateTime? navigationStartedAt,
  String? pageNameOverride,
  VisitRecorderService? visitRecorder,
  AppTelemetryRecorder? telemetryReporter,
}) {
  final trace = AppTraceContextStore.instance;
  final pageName = pageNameOverride ?? pageNameFromRouteLocation(location);
  if (pageName.isEmpty) return Future<void>.value();
  final openedAt = navigationStartedAt ?? DateTime.now();
  AppPageContextStore.instance.setPageName(pageName);
  AppPageExperienceTracker.instance.beginPageVisit(
    pageName: pageName,
    pageVisitId: pageVisitId,
    openedAt: openedAt,
    reporter: telemetryReporter,
  );
  unawaited(
    visitRecorder?.recordVisit(VisitTarget.page(pageName)) ??
        Future<void>.value(),
  );
  unawaited(
    AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        pageVisitId: pageVisitId,
      ),
      payload: <String, Object?>{
        'event': 'open',
        'route': location,
        'pageName': pageName,
      },
      summaryPayload: <String, Object?>{'event': 'open', 'route': location},
    ),
  );
  if (telemetryReporter == null) return Future<void>.value();
  // readyMs 只表示路由进入到页面首帧渲染完成；业务可用 TTI 由
  // AppPageExperienceTracker 的 page_first_usable 终态单独结算。
  // 无渲染管线（纯 Dart 测试）时退化为立即上报且不带 readyMs。
  final binding = WidgetsBinding.instance;
  if (binding.firstFrameRasterized || binding.hasScheduledFrame) {
    binding.addPostFrameCallback((_) {
      final readyMs = DateTime.now().difference(openedAt).inMilliseconds;
      unawaited(
        telemetryReporter.record(
          AppTelemetryPayload.pageOpen(readyMs: readyMs),
          pageName: pageName,
        ),
      );
    });
  } else {
    unawaited(
      telemetryReporter.record(
        AppTelemetryPayload.pageOpen(),
        pageName: pageName,
      ),
    );
  }
  return Future<void>.value();
}

Future<void> writeAppPageAccessReturn({
  required String location,
  required String pageVisitId,
  required DateTime enterAt,
  String? pageNameOverride,
  AppTelemetryRecorder? telemetryReporter,
}) {
  final trace = AppTraceContextStore.instance;
  final durationMs = DateTime.now().difference(enterAt).inMilliseconds;
  final pageName = pageNameOverride ?? pageNameFromRouteLocation(location);
  if (pageName.isEmpty) return Future<void>.value();
  AppPageExperienceTracker.instance.endPageVisit(pageVisitId);
  unawaited(
    AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        pageVisitId: pageVisitId,
      ),
      payload: <String, Object?>{
        'event': 'return',
        'route': location,
        'pageName': pageName,
        'durationMs': durationMs,
      },
      summaryPayload: <String, Object?>{
        'event': 'return',
        'route': location,
        'durationMs': durationMs,
      },
    ),
  );
  unawaited(
    telemetryReporter?.record(
          AppTelemetryPayload.pageReturn(durationMs: durationMs),
          pageName: pageName,
        ) ??
        Future<AppTelemetryRecordResult>.value(
          AppTelemetryRecordResult.rejected,
        ),
  );
  return Future<void>.value();
}

String pageNameFromRouteLocation(String location) =>
    AppPages.pageNameFromLocation(location) ?? '';

/// 主壳 Tab 路由由 [MainAppShell] 单独埋点；Observer 跳过以免重复。
bool isShellTabLocation(String? routeName) {
  if (routeName == null || routeName.isEmpty) return false;
  var normalized = routeName;
  if (normalized != '/' && normalized.endsWith('/')) {
    normalized = normalized.substring(0, normalized.length - 1);
  }
  return normalized == AppRoutePaths.home ||
      normalized == AppRoutePaths.circles ||
      normalized == AppRoutePaths.chat ||
      normalized == AppRoutePaths.profile ||
      normalized == AppRoutePaths.assistant;
}

String? routeLocationFromSettings(Route<dynamic> route) {
  final name = route.settings.name;
  if (name != null && name.isNotEmpty) return name;
  return null;
}
