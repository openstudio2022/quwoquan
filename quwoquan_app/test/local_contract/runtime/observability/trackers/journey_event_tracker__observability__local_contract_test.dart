import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

void main() {
  test('登录漏斗空可选维度归一化为缺省，不产生空串脏值', () async {
    final recorder = RecordingAppTelemetryRecorder();
    final tracker = JourneyEventTracker(telemetryReporter: recorder);

    await tracker.trackLoginFunnel(
      action: 'login_step_changed',
      flowId: 'flow-1',
      step: 'otp_verify',
      result: 'success',
      pageName: 'login',
      entryMode: '  ',
      provider: '',
      durationMs: 800,
    );

    final recorded = recorder.recorded.single;
    expect(recorded.eventType, 'login_funnel');
    expect(recorded.extensions['action'], 'login_step_changed');
    expect(recorded.extensions['flowId'], 'flow-1');
    expect(recorded.extensions['step'], 'otp_verify');
    expect(recorded.extensions['result'], 'success');
    expect(recorded.extensions['durationMs'], 800);
    // 空白可选值必须整键缺省，禁止空串进入低基数维度。
    expect(recorded.extensions.keys, isNot(contains('entryMode')));
    expect(recorded.extensions.keys, isNot(contains('provider')));
  });

  test('登录操作显式失败维度优先于 error 派生维度', () async {
    final recorder = RecordingAppTelemetryRecorder();
    final tracker = JourneyEventTracker(telemetryReporter: recorder);
    const failure = RuntimeFailure(
      code: 'USER.AUTH.otp_mismatch',
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.validation,
      nature: RuntimeFailureNature.permanent,
      location: RuntimeFailureLocation(
        businessObject: 'user.account_session',
        functionModule: 'verify_login_otp',
      ),
      context: RuntimeFailureContext(),
      recovery: RuntimeRecoveryDirective(
        action: 'reenter',
        disruptionLevel: 'surface',
      ),
    );

    await tracker.trackLoginOperation(
      operationId: 'verify_login_otp',
      surfaceId: 'login_otp',
      result: 'failure',
      pageName: 'login',
      failReasonCode: 'USER.AUTH.otp_expired',
      error: CloudException(
        type: CloudErrorType.server,
        message: 'otp mismatch',
        code: 'USER.AUTH.otp_mismatch',
        runtimeFailure: failure,
        requestId: 'request-login-1',
        traceId: 'trace-login-1',
      ),
    );

    final recorded = recorder.recorded.single;
    expect(recorded.eventType, 'login_operation');
    // 调用方显式口径优先；error 只补缺失维度（recovery/request/trace）。
    expect(recorded.extensions['failReasonCode'], 'USER.AUTH.otp_expired');
    expect(recorded.extensions['recoveryAction'], 'reenter');
    expect(recorded.extensions['requestId'], 'request-login-1');
    expect(recorded.extensions['traceId'], 'trace-login-1');
  });

  test('surfaceId 缺省回退 pageName 且 recorder 抛错不外溢到业务调用方', () async {
    final recorder = RecordingAppTelemetryRecorder(
      recordError: StateError('outbox unavailable'),
    );
    final tracker = JourneyEventTracker(telemetryReporter: recorder);

    // recorder 抛错时 trackAction 必须吞掉异常（埋点失败不打断业务）。
    await expectLater(
      tracker.trackAction(
        journey: 'content_share',
        action: 'share_open',
        pageName: 'post_detail',
      ),
      completes,
    );

    final healthy = RecordingAppTelemetryRecorder();
    await JourneyEventTracker(telemetryReporter: healthy).trackAction(
      journey: 'content_share',
      action: 'share_open',
      pageName: 'post_detail',
    );
    expect(healthy.recorded.single.extensions['surfaceId'], 'post_detail');
  });

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
      targetType: 'homepage',
      targetKey: 'homepage_001',
      entityType: 'homepage',
      entityId: 'homepage_001',
      surfaceId: 'entity_homepage_detail',
      reasonId: 'reason_001',
      environment: 'gamma',
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
      'surfaceId': 'entity_homepage_detail',
      'objectType': 'homepage',
      'objectId': 'homepage_001',
      'reasonId': 'reason_001',
      'targetType': 'homepage',
      'targetId': 'homepage_001',
      'environment': 'gamma',
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
