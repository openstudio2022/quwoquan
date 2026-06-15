import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/core/services/hive_runtime.dart';

void main() {
  Directory? tempDir;

  tearDown(() async {
    if (Hive.isBoxOpen('app_exception_queue_failure_test')) {
      await Hive.box<String>('app_exception_queue_failure_test').close();
    }
    if (Hive.isBoxOpen('app_exception_queue_success_test')) {
      await Hive.box<String>('app_exception_queue_success_test').close();
    }
    await Hive.deleteFromDisk();
    if (tempDir != null && await tempDir!.exists()) {
      await tempDir!.delete(recursive: true);
    }
    HiveRuntime.resetForTest();
  });

  test('Hive 未就绪时异常遥测降级跳过本地队列，不再抛异常', () async {
    HiveRuntime.debugEnsureInitializedHook = () async => false;
    final service = AppExceptionTelemetryService(
      eventRepository: MockOpsEventRepository(),
      queueBoxName: 'app_exception_queue_unavailable_test',
    );

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'Hive unavailable during bootstrap',
      stackText: 'stack',
    );

    await service.flushPending();
  });

  test('远端上报失败时保留队列并记录结构化失败状态', () async {
    tempDir = await Directory.systemTemp.createTemp('app_exception_telemetry_');
    Hive.init(tempDir!.path);
    final repository = _FailingOpsEventRepository();
    final service = AppExceptionTelemetryService(
      eventRepository: repository,
      queueBoxName: 'app_exception_queue_failure_test',
    );

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'boom',
      stackText: 'stack',
    );
    await service.flushPending();

    final box = Hive.box<String>('app_exception_queue_failure_test');
    expect(box.length, 1);
    expect(service.lastFlushFailure, isNotNull);
    expect(service.lastFlushFailure?.errorType, 'StateError');
    expect(service.lastFlushFailure?.queueDepth, 1);
  });

  test('flush 成功后清理本地队列', () async {
    tempDir = await Directory.systemTemp.createTemp('app_exception_telemetry_');
    Hive.init(tempDir!.path);
    final repository = MockOpsEventRepository();
    final service = AppExceptionTelemetryService(
      eventRepository: repository,
      queueBoxName: 'app_exception_queue_success_test',
    );

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'boom',
      stackText: 'stack',
    );
    await service.flushPending();

    final box = Hive.box<String>('app_exception_queue_success_test');
    expect(box.length, 0);
    expect(repository.recorded, isNotEmpty);
    expect(service.lastFlushFailure, isNull);
  });
}

class _FailingOpsEventRepository extends MockOpsEventRepository {
  @override
  Future<OpsEventBatchAck> reportEventBatch({
    required List<OpsEventRecordInput> events,
  }) async {
    throw StateError('ops unavailable');
  }
}
