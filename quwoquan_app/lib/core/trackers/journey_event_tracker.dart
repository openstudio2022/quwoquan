import 'dart:developer' as developer;

import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';

/// Lightweight journey event tracker for pages without full behavior tracking.
///
/// Emits OpsEvent records for key user actions to enable L1/L2 funnel analysis.
///
/// [AppTraceContextStore] does not expose a stable "current page visit" id; callers
/// that have a visit id from navigation (e.g. route settings) should pass it via
/// [payload] until a shared visit context is wired here.
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
    Map<String, dynamic> payload = const {},
  }) async {
    final trace = AppTraceContextStore.instance;
    final now = DateTime.now().toUtc().toIso8601String();
    final eventId = trace.newRequestId();
    final requestId = trace.newRequestId();
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
            pageVisitId: '',
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
