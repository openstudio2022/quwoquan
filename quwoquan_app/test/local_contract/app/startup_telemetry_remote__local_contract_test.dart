// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/ops/product_ops/event_record/application/startup_telemetry.dart';
import 'package:quwoquan_app/ops/product_ops/event_record/adapters/startup_telemetry_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('启动遥测只走 generated operation，proof 只进入 canonical header', () async {
    final executor = _StartupTelemetryExecutor();
    final transport = RemoteStartupTelemetryTransport(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: () => CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.appShell.id,
        routeId: AppUiSurfaces.appShell.routeId,
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
        recoverySurface: '',
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
}

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
