import 'dart:developer' as developer;

import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';

/// Lightweight journey event tracker for pages without full behavior tracking.
///
/// Emits OpsEvent records for key user actions to enable L1/L2 funnel analysis.
///
/// 页级归因优先使用 [AppTraceContextStore.currentPageVisitId]（由导航在打开页面时铸造）；
/// 调用方若持有更精确的 visit id（如来自 route settings），可通过 [pageVisitId] 显式覆盖。
class JourneyEventTracker {
  JourneyEventTracker({required this.eventRepository});

  final OpsEventRepository eventRepository;

  Future<void> trackAction({
    required String journey,
    required String action,
    required String pageName,
    String targetType = '',
    String targetKey = '',
    String entityType = '',
    String entityId = '',
    String? pageVisitId,
    Map<String, dynamic> payload = const {},
  }) async {
    final trace = AppTraceContextStore.instance;
    final now = DateTime.now().toUtc().toIso8601String();
    final eventId = trace.newRequestId();
    final requestId = trace.newRequestId();
    final resolvedPageVisitId =
        pageVisitId ?? trace.currentPageVisitId ?? '';
    try {
      await eventRepository.reportEventBatch(
        events: <OpsEventRecordInput>[
          OpsEventRecordInput(
            eventId: eventId,
            eventType: 'journey',
            eventName: '$journey.$action',
            occurredAt: now,
            clientSentAt: now,
            sessionId: trace.sessionId,
            pageVisitId: resolvedPageVisitId,
            requestId: requestId,
            producer: 'app.journey_tracker',
            source: journey,
            pageName: pageName,
            targetType: targetType,
            targetKey: targetKey,
            entityType: entityType,
            entityId: entityId,
            payload: payload,
          ),
        ],
      );
    } catch (e, st) {
      developer.log(
        'JourneyEventTracker.trackAction failed: $e',
        name: 'JourneyEventTracker',
        error: e,
        stackTrace: st,
      );
    }
  }
}
