// ignore_for_file: prefer_initializing_formals

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/observability/app_log_models.dart';
import 'package:quwoquan_app/runtime/observability/app_log_service.dart';
import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';

class AnalyticsEvent {
  final String eventType;
  final String eventName;
  final Map<String, dynamic> properties;

  const AnalyticsEvent({
    required this.eventType,
    required this.eventName,
    this.properties = const {},
  });
}

class AnalyticsConfig {
  final bool enabled;

  const AnalyticsConfig({this.enabled = true});
}

/// 存量 Analytics 调用的收口适配器。动态 properties 只写本地诊断；云端只能
/// 投影到目录登记的强类型字段，禁止透传自由 Map。
class AnalyticsService {
  AnalyticsService({
    required AppTelemetryRecorder telemetryReporter,
    AppLogService? appLogService,
  }) : _telemetryReporter = telemetryReporter,
       _appLogService = appLogService ?? AppLogService.instance;

  AnalyticsService.forTesting({
    AppTelemetryRecorder? telemetryReporter,
    AppLogService? appLogService,
  }) : _telemetryReporter = telemetryReporter,
       _appLogService = appLogService ?? AppLogService.instance;

  final AppTelemetryRecorder? _telemetryReporter;
  final AppLogService _appLogService;
  bool _enabled = true;

  Future<void> initialize(AnalyticsConfig config) async {
    _enabled = config.enabled;
  }

  Future<void> trackEvent(AnalyticsEvent event) async {
    if (!_enabled) return;
    _writeLocalEvent(event);
    final reporter = _telemetryReporter;
    if (reporter == null) return;
    if (_localOnlyEventNames.contains(event.eventName)) return;
    final pageName = (event.properties['pageName'] ?? '').toString().trim();
    final durationMs = _firstInt(event.properties, const <String>[
      'durationMs',
      'latencyMs',
      'elapsedMs',
    ]);
    final result = (event.properties['result'] ?? '').toString().trim();
    final failReasonCode =
        (event.properties['failReasonCode'] ??
                event.properties['reason'] ??
                event.properties['mediaFailureKind'] ??
                '')
            .toString()
            .trim();
    final isPerformance =
        event.eventType == 'qoe' ||
        event.eventType == 'performance' ||
        durationMs != null;
    final payload = isPerformance && durationMs != null
        ? AppTelemetryPayload.performanceSample(
            operationId: event.eventName,
            durationMs: durationMs,
            result: result.isEmpty ? null : result,
            failReasonCode: failReasonCode.isEmpty ? null : failReasonCode,
          )
        : AppTelemetryPayload.productAction(
            journey: event.eventType,
            action: event.eventName,
            result: result.isEmpty ? null : result,
            failReasonCode: failReasonCode.isEmpty ? null : failReasonCode,
          );
    unawaited(
      reporter.record(
        payload,
        pageName: pageName.isEmpty
            ? AppPageContextStore.instance.pageName
            : pageName,
      ),
    );
  }

  /// 已进入 metadata 目录的 command/query 终态。该入口保留 operation、页面、
  /// cache fallback 与 canonical error/recovery 上下文，不经过动态 Map 投影。
  Future<void> trackOperationResult({
    required String operationId,
    required String result,
    required String surfaceId,
    required bool hasCache,
    String? failReasonCode,
    String? recoveryAction,
    String? requestId,
    String? traceId,
  }) async {
    if (!_enabled) return;
    final event = AnalyticsEvent(
      eventType: 'operation_result',
      eventName: operationId,
      properties: <String, Object?>{
        'result': result,
        'surfaceId': surfaceId,
        'hasCache': hasCache,
        if ((failReasonCode ?? '').trim().isNotEmpty)
          'failReasonCode': failReasonCode,
        if ((recoveryAction ?? '').trim().isNotEmpty)
          'recoveryAction': recoveryAction,
        if ((requestId ?? '').trim().isNotEmpty) 'requestId': requestId,
        if ((traceId ?? '').trim().isNotEmpty) 'traceId': traceId,
      },
    );
    _writeLocalEvent(event);
    final reporter = _telemetryReporter;
    if (reporter == null) return;
    await reporter.record(
      AppTelemetryPayload.operationResult(
        operationId: operationId,
        result: result,
        surfaceId: surfaceId,
        hasCache: hasCache,
        failReasonCode: failReasonCode,
        recoveryAction: recoveryAction,
        requestId: requestId,
        traceId: traceId,
      ),
      pageName: AppPageContextStore.instance.pageName,
    );
  }

  void _writeLocalEvent(AnalyticsEvent event) {
    final trace = AppTraceContextStore.instance;
    unawaited(
      _appLogService.writeEvent(
        logType: AppLogType.pageAccess,
        level: AppLogLevel.info,
        context: AppLogContext(
          sessionId: trace.sessionId,
          pageVisitId: trace.newPageVisitId(),
          requestId: trace.newRequestId(),
          target: 'analytics_facade',
          action: event.eventName,
        ),
        payload: <String, Object?>{
          'kind': 'analytics_event',
          'eventType': event.eventType,
          'eventName': event.eventName,
          'properties': event.properties,
        },
        summaryPayload: <String, Object?>{
          'kind': 'analytics_event',
          'eventType': event.eventType,
          'eventName': event.eventName,
        },
      ),
    );
  }

  static const Set<String> _localOnlyEventNames = <String>{
    'media_load_state',
    'home_feed_frame_jank_ratio',
    'home_feed_image_cache_bytes',
    'home_feed_active_video_controller_count',
    'home_feed_media_download_queue',
    'home_feed_post_cache_hit_source',
  };

  int? _firstInt(Map<String, dynamic> values, Iterable<String> keys) {
    for (final key in keys) {
      final value = values[key];
      if (value is int) return value;
      if (value is num) return value.round();
    }
    return null;
  }
}

final analyticsConfigProvider = Provider<AnalyticsConfig>((ref) {
  return const AnalyticsConfig();
});

final analyticsProvider = Provider<AnalyticsService>((ref) {
  return AnalyticsService(
    telemetryReporter: ref.watch(appTelemetryReporterProvider),
  );
});
