import 'dart:developer' as developer;

import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/trackers/runtime_failure_telemetry_dimensions.dart';

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
    Object? error,
  }) async {
    final duration = payload['durationMs'];
    final result = (payload['result'] ?? '').toString().trim();
    final dimensions = RuntimeFailureTelemetryDimensions.from(error);
    final explicitFailReason = (payload['failReasonCode'] ?? '')
        .toString()
        .trim();
    final explicitRecoveryAction = (payload['recoveryAction'] ?? '')
        .toString()
        .trim();
    final explicitRequestId = (payload['requestId'] ?? '').toString().trim();
    final explicitTraceId = (payload['traceId'] ?? '').toString().trim();
    final failReasonCode = explicitFailReason.isNotEmpty
        ? explicitFailReason
        : dimensions.sourceCode;
    final recoveryAction = explicitRecoveryAction.isNotEmpty
        ? explicitRecoveryAction
        : dimensions.recoveryAction;
    final requestId = explicitRequestId.isNotEmpty
        ? explicitRequestId
        : dimensions.requestId;
    final traceId = explicitTraceId.isNotEmpty
        ? explicitTraceId
        : dimensions.traceId;
    try {
      await telemetryReporter.record(
        AppTelemetryPayload.productAction(
          journey: journey,
          action: action,
          durationMs: duration is num ? duration.round() : null,
          result: result.isEmpty ? null : result,
          failReasonCode: failReasonCode.isEmpty ? null : failReasonCode,
          recoveryAction: recoveryAction.isEmpty ? null : recoveryAction,
          requestId: requestId.isEmpty ? null : requestId,
          traceId: traceId.isEmpty ? null : traceId,
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
