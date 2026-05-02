import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';

void main() {
  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp(
      'app_exception_queue_test_',
    );
    Hive.init(tempDir.path);
  });

  tearDown(() async {
    await Hive.close();
    await tempDir.delete(recursive: true);
  });

  test('keeps latest 100 exceptions when upload is not accepted', () async {
    final service = AppExceptionTelemetryService(
      eventRepository: _AckingOpsRepository(accepted: 0),
      queueBoxName: 'app_exception_queue_limit_test',
    );

    for (var i = 0; i < 105; i++) {
      await service.recordGlobalException(
        source: 'test',
        exceptionText: 'boom-$i',
        stackText: 'stack-$i',
      );
    }

    final box = Hive.box<String>('app_exception_queue_limit_test');
    expect(box.length, 100);
  });

  test('clears exception queue after accepted upload', () async {
    final repo = _AckingOpsRepository(accepted: 1);
    final service = AppExceptionTelemetryService(
      eventRepository: repo,
      queueBoxName: 'app_exception_queue_success_test',
    );

    await service.recordGlobalException(
      source: 'test',
      exceptionText: 'boom',
      stackText: 'stack',
    );

    final box = Hive.box<String>('app_exception_queue_success_test');
    expect(box.length, 0);
    expect(repo.events.single.errorCode, 'APP.RUNTIME.uncaught_exception');
    expect(repo.events.single.requestId, isNotEmpty);
    expect(repo.events.single.sessionId, isNotEmpty);
  });
}

class _AckingOpsRepository implements OpsEventRepository {
  _AckingOpsRepository({required this.accepted});

  final int accepted;
  final List<OpsEventRecordInput> events = <OpsEventRecordInput>[];

  @override
  Future<void> flushPending() async {}

  @override
  Future<OpsEventDrilldown> getEventDrilldown({
    String eventType = '',
    String eventName = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String targetType = '',
    String targetKey = '',
    String entityType = '',
    String entityId = '',
    String experimentBucket = '',
    String source = '',
    int limit = 20,
  }) async {
    return const OpsEventDrilldown(
      totalCount: 0,
      items: <OpsEventDrilldownItem>[],
    );
  }

  @override
  Future<OpsEventSummary> getEventSummary({
    String eventType = '',
    String eventName = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String targetType = '',
    String targetKey = '',
    String entityType = '',
    String entityId = '',
    String experimentBucket = '',
    String source = '',
  }) async {
    return const OpsEventSummary(
      totalCount: 0,
      dimensions: <String, Map<String, int>>{},
    );
  }

  @override
  Future<OpsEventBatchAck> reportEventBatch({
    required List<OpsEventRecordInput> events,
  }) async {
    this.events.addAll(events);
    return OpsEventBatchAck(acceptedCount: accepted, duplicateCount: 0);
  }
}
