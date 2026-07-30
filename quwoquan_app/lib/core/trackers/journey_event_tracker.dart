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
    String surfaceId = '',
    String reasonId = '',
    String environment = '',
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
          surfaceId: surfaceId.isEmpty ? pageName : surfaceId,
          objectType: entityType.isEmpty ? null : entityType,
          objectId: entityId.isEmpty ? null : entityId,
          reasonId: reasonId.isEmpty ? null : reasonId,
          targetType: targetType.isEmpty ? null : targetType,
          targetId: targetKey.isEmpty ? null : targetKey,
          environment: environment.isEmpty ? null : environment,
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

  Future<void> trackLoginFunnel({
    required String action,
    required String flowId,
    required String step,
    required String result,
    required String pageName,
    String? entryMode,
    String? fromStep,
    String? toStep,
    String? provider,
    String? otpPurpose,
    String? consentState,
    int? durationMs,
    int? attemptIndex,
    String? countdownBucket,
    bool? motionReduced,
    String? dismissPolicy,
  }) async {
    try {
      await telemetryReporter.record(
        AppTelemetryPayload.loginFunnel(
          action: action,
          flowId: flowId,
          step: step,
          result: result,
          entryMode: _nonEmpty(entryMode),
          fromStep: _nonEmpty(fromStep),
          toStep: _nonEmpty(toStep),
          provider: _nonEmpty(provider),
          otpPurpose: _nonEmpty(otpPurpose),
          consentState: _nonEmpty(consentState),
          durationMs: durationMs,
          attemptIndex: attemptIndex,
          countdownBucket: _nonEmpty(countdownBucket),
          motionReduced: motionReduced,
          dismissPolicy: _nonEmpty(dismissPolicy),
        ),
        pageName: pageName,
      );
    } catch (error, stackTrace) {
      developer.log(
        'JourneyEventTracker.trackLoginFunnel failed',
        name: 'JourneyEventTracker',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  Future<void> trackLoginOperation({
    required String operationId,
    required String surfaceId,
    required String result,
    required String pageName,
    String? flowId,
    String? step,
    String? provider,
    String? otpPurpose,
    String? failReasonCode,
    String? failureKind,
    String? recoveryAction,
    String? copyKey,
    String? feedbackSurface,
    int? durationMs,
    int? attemptIndex,
    String? requestId,
    String? traceId,
    Object? error,
  }) async {
    final dimensions = RuntimeFailureTelemetryDimensions.from(error);
    try {
      await telemetryReporter.record(
        AppTelemetryPayload.loginOperation(
          operationId: operationId,
          surfaceId: surfaceId,
          result: result,
          flowId: _nonEmpty(flowId),
          step: _nonEmpty(step),
          provider: _nonEmpty(provider),
          otpPurpose: _nonEmpty(otpPurpose),
          failReasonCode: _firstNonEmpty(failReasonCode, dimensions.sourceCode),
          failureKind: _firstNonEmpty(failureKind, dimensions.failureKind),
          recoveryAction: _firstNonEmpty(
            recoveryAction,
            dimensions.recoveryAction,
          ),
          copyKey: _nonEmpty(copyKey),
          feedbackSurface: _nonEmpty(feedbackSurface),
          durationMs: durationMs,
          attemptIndex: attemptIndex,
          requestId: _firstNonEmpty(requestId, dimensions.requestId),
          traceId: _firstNonEmpty(traceId, dimensions.traceId),
        ),
        pageName: pageName,
      );
    } catch (recordError, stackTrace) {
      developer.log(
        'JourneyEventTracker.trackLoginOperation failed',
        name: 'JourneyEventTracker',
        error: recordError,
        stackTrace: stackTrace,
      );
    }
  }
}

String? _nonEmpty(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

String? _firstNonEmpty(String? preferred, String fallback) =>
    _nonEmpty(preferred) ?? _nonEmpty(fallback);
