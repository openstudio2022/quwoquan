// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/event-schema-governance/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/services/ops/event_record_batch_writer.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart' as ops;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('EventRecord 两类批次只经 generated operation client 提交', () async {
    final executor = _RecordingExecutor();
    final writer = RemoteOpsEventRecordBatchWriter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId, {required idempotencyKey}) =>
          CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.appShell.id,
            routeId: AppUiSurfaces.appShell.routeId,
            clientPageId: clientPageId,
            idempotencyKey: idempotencyKey,
            actor: const CloudOperationActorContext(accountId: 'account-1'),
          ),
    );

    await writer.reportEventBatch(
      ops.EventRecordBatchRequest(events: <ops.EventRecord>[_eventRecord()]),
      idempotencyKey: 'event-batch-1',
    );
    await writer.reportRuntimeLogBatch(
      ops.RuntimeLogBatchRequest(
        records: <ops.RuntimeLogRecordWire>[_runtimeLogRecord()],
      ),
      idempotencyKey: 'runtime-log-batch-1',
    );

    expect(executor.operations, <String>[
      AppCloudOperationIds.opsEventRecordReportEventBatch,
      AppCloudOperationIds.opsEventRecordReportRuntimeLogBatch,
    ]);
    expect(executor.idempotencyKeys, <String>[
      'event-batch-1',
      'runtime-log-batch-1',
    ]);
    expect(executor.bodies[0], contains('events'));
    expect(executor.bodies[1], contains('records'));
  });
}

ops.EventRecord _eventRecord() => ops.EventRecord(
  logType: 'error',
  eventType: 'runtime_exception',
  sessionId: 'session-1',
  pageName: 'app_shell',
  occurredAt: DateTime.utc(2026, 8, 4),
  deviceManufacturer: 'test',
  deviceModel: 'test',
  appVersion: '1.0.0',
  networkClass: 'wifi',
  errorCode: 'APP.RUNTIME.test_failure',
);

ops.RuntimeLogRecordWire _runtimeLogRecord() =>
    ops.RuntimeLogRecordWire.fromWire(<String, Object?>{
      'schema': 'observability.slim',
      'recordId': 'record-1',
      'occurredAt': '2026-08-04T00:00:00Z',
      'observedAt': '2026-08-04T00:00:00Z',
      'logKind': 'event',
      'severity': 'WARN',
      'signal': 'app.performance.frame',
      'message': 'frame jank',
      // logKind=event 的 canonical 必需字段（generated 校验 requiredKindFields）。
      'event': 'frame_jank_observed',
      'result': 'observed',
      'resource': <String, Object?>{
        'sourceType': 'app',
        'service': 'quwoquan_app',
        'environment': 'gamma',
        'appVersion': '1.0.0',
      },
    });

final class _RecordingExecutor implements CloudOperationExecutor {
  final List<String> operations = <String>[];
  final List<String?> idempotencyKeys = <String?>[];
  final List<Object?> bodies = <Object?>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operations.add(operation.canonicalOperationId);
    idempotencyKeys.add(context.idempotencyKey);
    bodies.add(requestEncoder().body);
    return responseDecoder(<String, Object?>{
      'acceptedCount': 1,
      'duplicateBatch': false,
    });
  }
}
