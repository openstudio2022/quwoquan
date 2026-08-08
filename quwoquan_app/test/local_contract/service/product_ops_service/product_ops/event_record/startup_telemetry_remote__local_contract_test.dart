// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
// readiness_case: event_record_report_startup_event_batch_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/observability/startup/startup_telemetry.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/adapters/startup_telemetry_remote.dart';
import 'package:quwoquan_app/runtime/transport/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart'
    as ops_contracts;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('启动遥测只走 generated operation，proof 只进入 canonical header', () async {
    final executor = _StartupTelemetryExecutor();
    final transport = RemoteStartupTelemetryTransport(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: ({required bool recoveryBatch}) =>
          CloudOperationInvocationContext(
            surfaceId: recoveryBatch
                ? ops_contracts
                      .StartupRecoverySurface
                      .pageAppStartupRecovery
                      .wireName
                : AppUiSurfaces.appShell.id,
            routeId: recoveryBatch ? null : AppUiSurfaces.appShell.routeId,
            clientPageId: OpsRequestPageIds.reportStartupEventBatch,
            actor: const CloudOperationActorContext(),
          ),
    );
    final ack = await transport.report([
      StartupTelemetryEvent(
        eventId: 'event_1234567890123456',
        attemptId: 'attempt_12345678901234',
        sequence: 1,
        phase: StartupTelemetryPhase.terminal,
        phaseDurationMs: 10,
        elapsedMs: 1000,
        outcome: 'success',
        occurredAt: DateTime.utc(2026, 7, 28),
        platform: 'android',
        runtimeEnv: 'gamma',
        appVersion: '1.0.0',
        networkClass: 'wifi',
        failureCode: '',
        failureSource: '',
        deadlineOrigin: 'android_process',
      ),
    ], proof: 'proof_123456789012345678901234');

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.opsEventRecordReportStartupEventBatch,
    );
    expect(executor.context?.surfaceId, AppUiSurfaces.appShell.id);
    expect(executor.context?.routeId, AppUiSurfaces.appShell.routeId);
    expect(
      executor.context?.clientPageId,
      OpsRequestPageIds.reportStartupEventBatch,
    );
    expect(executor.headers, <String, String>{
      'X-Qwq-Startup-Proof': 'proof_123456789012345678901234',
    });
    expect(executor.body, <String, Object?>{
      'events': <Object?>[
        <String, Object?>{
          'eventId': 'event_1234567890123456',
          'attemptId': 'attempt_12345678901234',
          'sequence': 1,
          'phase': 'terminal',
          'phaseDurationMs': 10,
          'elapsedMs': 1000,
          'outcome': 'success',
          'occurredAt': '2026-07-28T00:00:00.000Z',
          'platform': 'android',
          'runtimeEnv': 'gamma',
          'appVersion': '1.0.0',
          'networkClass': 'wifi',
          'deadlineOrigin': 'android_process',
        },
      ],
    });
    expect(executor.body, isNot(contains('proof')));
    expect(ack.acceptedCount, 0);
    expect(ack.duplicateCount, 1);
    expect(ack.acknowledges(1), isTrue);
  });

  test('恢复批次固定 recovery surface 且 routeId 为 null', () async {
    final executor = _StartupTelemetryExecutor();
    final transport = _recoveryAwareTransport(executor);

    await transport.report(<StartupTelemetryEvent>[
      _recoveryEvent(),
    ], proof: 'proof_123456789012345678901234');

    expect(
      executor.context?.surfaceId,
      ops_contracts.StartupRecoverySurface.pageAppStartupRecovery.wireName,
    );
    expect(executor.context?.routeId, isNull);
    final events = (executor.body as Map<String, Object?>)['events']! as List;
    expect(events.single, containsPair('recoveryLifecycle', 'enter'));
    expect(events.single, containsPair('recoveryMount', 'router_error'));
    expect(
      events.single,
      containsPair('recoverySurface', 'page.app.startup_recovery'),
    );
  });

  test('Remote adapter fail-closed 拒绝 startup/recovery 混批', () async {
    final executor = _StartupTelemetryExecutor();
    final transport = _recoveryAwareTransport(executor);

    await expectLater(
      transport.report(<StartupTelemetryEvent>[
        _startupEvent(),
        _recoveryEvent(),
      ], proof: 'proof_123456789012345678901234'),
      throwsStateError,
    );
    expect(executor.operation, isNull);
  });
}

RemoteStartupTelemetryTransport _recoveryAwareTransport(
  _StartupTelemetryExecutor executor,
) {
  return RemoteStartupTelemetryTransport(
    client: GeneratedCloudOperationClient(executor),
    invocationContext: ({required bool recoveryBatch}) =>
        CloudOperationInvocationContext(
          surfaceId: recoveryBatch
              ? ops_contracts
                    .StartupRecoverySurface
                    .pageAppStartupRecovery
                    .wireName
              : AppUiSurfaces.appShell.id,
          routeId: recoveryBatch ? null : AppUiSurfaces.appShell.routeId,
          clientPageId: OpsRequestPageIds.reportStartupEventBatch,
          actor: const CloudOperationActorContext(),
        ),
  );
}

StartupTelemetryEvent _startupEvent() => StartupTelemetryEvent(
  eventId: 'event_1234567890123456',
  attemptId: 'attempt_12345678901234',
  sequence: 1,
  phase: StartupTelemetryPhase.terminal,
  phaseDurationMs: 10,
  elapsedMs: 1000,
  outcome: 'success',
  occurredAt: DateTime.utc(2026, 7, 28),
  platform: 'android',
  runtimeEnv: 'gamma',
  appVersion: '1.0.0',
  networkClass: 'wifi',
  failureCode: '',
  failureSource: '',
  deadlineOrigin: 'android_process',
);

StartupTelemetryEvent _recoveryEvent() => StartupTelemetryEvent(
  eventId: 'event_1234567890123457',
  attemptId: 'attempt_12345678901234',
  sequence: 2,
  phase: StartupTelemetryPhase.recovery,
  phaseDurationMs: 1,
  elapsedMs: 1001,
  outcome: 'entered',
  occurredAt: DateTime.utc(2026, 7, 28),
  platform: 'android',
  runtimeEnv: 'gamma',
  appVersion: '1.0.0',
  networkClass: 'wifi',
  recoverySurface: ops_contracts.StartupRecoverySurface.pageAppStartupRecovery,
  recoveryLifecycle: ops_contracts.StartupRecoveryLifecycle.enter,
  recoveryMount: ops_contracts.StartupRecoveryMount.routerError,
  recoveryPhase: ops_contracts.StartupRecoveryPhase.startupChecking,
  recoveryAction: ops_contracts.StartupRecoveryAction.none,
  failureCode: '',
  failureSource: '',
  deadlineOrigin: 'android_process',
);

final class _StartupTelemetryExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String>? headers;
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    final request = requestEncoder();
    this.operation = operation;
    this.context = context;
    headers = request.headers;
    body = request.body;
    return responseDecoder(<String, Object?>{
      'acceptedCount': 1,
      'duplicateBatch': true,
    });
  }
}
