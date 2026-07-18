import 'dart:developer' as developer;

import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';

/// 无推荐反馈语义的关键产品动作统一投影到 `product_action` 目录事件。
class JourneyEventTracker {
  JourneyEventTracker({required this.telemetryReporter});

  final AppTelemetryRecorder telemetryReporter;

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
    final duration = payload['durationMs'];
    final result = (payload['result'] ?? '').toString().trim();
    final failReasonCode = (payload['failReasonCode'] ?? '').toString().trim();
    try {
      await telemetryReporter.record(
        AppTelemetryPayload.productAction(
          journey: journey,
          action: action,
          durationMs: duration is num ? duration.round() : null,
          result: result.isEmpty ? null : result,
          failReasonCode: failReasonCode.isEmpty ? null : failReasonCode,
        ),
        pageName: pageName,
      );
    } catch (error, stackTrace) {
      developer.log(
        'JourneyEventTracker.trackAction failed',
        name: 'JourneyEventTracker',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }
}
