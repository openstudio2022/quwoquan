import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_analytics_event_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_analytics_event_summary.g.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

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

class AnalyticsService {
  AnalyticsService({
    required AppDataSourceMode mode,
    required OpsEventRepository eventRepository,
    AppLogService? appLogService,
  }) : _mode = mode,
       _eventRepository = eventRepository,
       _appLogService = appLogService ?? AppLogService.instance;

  AnalyticsService.forTesting({
    AppDataSourceMode mode = AppDataSourceMode.mock,
    OpsEventRepository? eventRepository,
    AppLogService? appLogService,
  }) : _mode = mode,
       _eventRepository = eventRepository ?? MockOpsEventRepository(),
       _appLogService = appLogService ?? AppLogService.instance;

  final AppDataSourceMode _mode;
  final OpsEventRepository _eventRepository;
  final AppLogService _appLogService;

  bool _enabled = true;

  Future<void> initialize(AnalyticsConfig config) async {
    _enabled = config.enabled;
  }

  Future<void> trackEvent(AnalyticsEvent event) async {
    if (!_enabled) {
      return;
    }
    final trace = AppTraceContextStore.instance;
    await _appLogService.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        journeyId: trace.journeyId,
        pageVisitId: trace.newPageVisitId(),
        requestId: trace.newRequestId(),
        target: 'analytics_facade',
        action: event.eventName,
      ),
      payload: AppLogAnalyticsEventPayload(
        kind: 'analytics_event',
        eventType: event.eventType,
        eventName: event.eventName,
        properties: event.properties,
      ).toMap(),
      summaryPayload: AppLogAnalyticsEventSummaryPayload(
        kind: 'analytics_event',
        eventType: event.eventType,
        eventName: event.eventName,
      ).toMap(),
    );
    if (_mode != AppDataSourceMode.remote) {
      return;
    }
    try {
      final occurredAt = DateTime.now().toUtc();
      await _eventRepository.reportEventBatch(
        events: <OpsEventRecordInput>[
          OpsEventRecordInput(
            eventId: trace.newRequestId(),
            eventType: event.eventType,
            eventName: event.eventName,
            eventVersion: 'v1',
            priority: 'P1',
            producer: 'app.analytics_facade',
            source: 'analytics_facade',
            userIdHash: _hashUserId(_resolveUserId(event.properties)),
            sessionId: trace.sessionId,
            journeyId: trace.journeyId,
            pageVisitId: trace.newPageVisitId(),
            requestId: trace.newRequestId(),
            pageName: (event.properties['pageName'] ?? '').toString(),
            surfaceId: (event.properties['surfaceId'] ?? '').toString(),
            routeId: (event.properties['routeId'] ?? '').toString(),
            operationId: (event.properties['operationId'] ?? '').toString(),
            targetType: (event.properties['targetType'] ?? 'analytics')
                .toString(),
            targetKey: _targetKeyFor(event),
            entityType: (event.properties['entityType'] ?? '').toString(),
            entityId: (event.properties['entityId'] ?? '').toString(),
            experimentBucket: (event.properties['experimentBucket'] ?? '')
                .toString(),
            occurredAt: occurredAt.toIso8601String(),
            clientSentAt: occurredAt.toIso8601String(),
            payload: Map<String, dynamic>.from(event.properties),
            metrics: _extractMetrics(event.properties),
          ),
        ],
      );
    } catch (_) {
      // Best effort: analytics façade must not block product flows.
    }
  }

  String _resolveUserId(Map<String, dynamic> properties) {
    final raw = (properties['userId'] ?? properties['profileSubjectId'] ?? '')
        .toString()
        .trim();
    if (raw.isNotEmpty) {
      return raw;
    }
    return 'anonymous';
  }

  String _targetKeyFor(AnalyticsEvent event) {
    final rawTarget = (event.properties['targetKey'] ?? '').toString().trim();
    if (rawTarget.isNotEmpty) {
      return rawTarget;
    }
    return '${event.eventType}.${event.eventName}'.replaceAll(' ', '_');
  }

  Map<String, dynamic> _extractMetrics(Map<String, dynamic> properties) {
    final metrics = <String, dynamic>{};
    for (final entry in properties.entries) {
      if (entry.value is num) {
        metrics[entry.key] = entry.value;
      }
    }
    return metrics;
  }

  String _hashUserId(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty || trimmed == 'anonymous') {
      return '';
    }
    return sha256.convert(utf8.encode(trimmed)).toString().substring(0, 16);
  }
}

final analyticsConfigProvider = Provider<AnalyticsConfig>((ref) {
  return const AnalyticsConfig();
});

final analyticsProvider = Provider<AnalyticsService>((ref) {
  return AnalyticsService(
    mode: ref.watch(appDataSourceModeProvider),
    eventRepository: ref.watch(opsEventRepositoryProvider),
  );
});
