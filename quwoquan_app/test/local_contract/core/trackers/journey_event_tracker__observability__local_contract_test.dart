import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  test('产品动作失败保留恢复动作与端云关联标识', () async {
    final recorder = _CapturingTelemetryRecorder();
    final tracker = JourneyEventTracker(telemetryReporter: recorder);
    const failure = RuntimeFailure(
      code: 'CONTENT.SYSTEM.interaction_read_model_unavailable',
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.unavailable,
      nature: RuntimeFailureNature.transient,
      location: RuntimeFailureLocation(
        businessObject: 'content.profile_interaction_read_fact',
        functionModule: 'append_read_fact',
      ),
      context: RuntimeFailureContext(),
      recovery: RuntimeRecoveryDirective(
        action: 'retry',
        disruptionLevel: 'surface',
      ),
    );

    await tracker.trackAction(
      journey: 'profile_interaction',
      action: 'mark_seen',
      pageName: 'profile_interaction_tab',
      error: CloudException(
        type: CloudErrorType.server,
        message: 'read model unavailable',
        code: 'CONTENT.SYSTEM.interaction_read_model_unavailable',
        runtimeFailure: failure,
        requestId: 'request-interaction-1',
        traceId: 'trace-interaction-1',
      ),
      payload: const <String, Object?>{'result': 'failure', 'durationMs': 240},
    );

    expect(recorder.pageName, 'profile_interaction_tab');
    expect(recorder.payload.eventType, 'product_action');
    expect(recorder.payload.extensions, <String, Object?>{
      'journey': 'profile_interaction',
      'action': 'mark_seen',
      'durationMs': 240,
      'result': 'failure',
      'failReasonCode': 'CONTENT.SYSTEM.interaction_read_model_unavailable',
      'recoveryAction': 'retry',
      'requestId': 'request-interaction-1',
      'traceId': 'trace-interaction-1',
    });
  });
}

final class _CapturingTelemetryRecorder implements AppTelemetryRecorder {
  AppTelemetryPayload? _payload;
  String? pageName;

  AppTelemetryPayload get payload => _payload!;

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  void onNetworkAvailable() {}

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    _payload = payload;
    this.pageName = pageName;
    return AppTelemetryRecordResult.accepted;
  }
}
