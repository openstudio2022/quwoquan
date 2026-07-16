import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/infrastructure/local/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/core/services/hive_runtime.dart';

void main() {
  Directory? tempDir;

  tearDown(() async {
    for (final baseName in <String>[
      'app_exception_queue_failure_test',
      'app_exception_queue_success_test',
    ]) {
      final boxName = _partition().boxName(baseName);
      if (Hive.isBoxOpen(boxName)) {
        await Hive.box<String>(boxName).close();
      }
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
      queuePartition: _partition(),
      queueBoxName: 'app_exception_queue_unavailable_test',
      queueStorage: _storage(),
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
      queuePartition: _partition(),
      queueBoxName: 'app_exception_queue_failure_test',
      queueStorage: _storage(),
    );

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'boom',
      stackText: 'stack',
    );
    await service.flushPending();

    final box = Hive.box<String>(
      _partition().boxName('app_exception_queue_failure_test'),
    );
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
      queuePartition: _partition(),
      queueBoxName: 'app_exception_queue_success_test',
      queueStorage: _storage(),
    );

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'boom',
      stackText: 'stack',
    );
    await service.flushPending();

    final box = Hive.box<String>(
      _partition().boxName('app_exception_queue_success_test'),
    );
    expect(box.length, 0);
    expect(repository.recorded, isNotEmpty);
    expect(service.lastFlushFailure, isNull);
  });
}

ActorQueueStorage _storage() =>
    ActorQueueStorage(keyStore: _MemoryActorQueueKeyStore());

final class _MemoryActorQueueKeyStore implements ActorQueueEncryptionKeyStore {
  final Map<String, String> _values = <String, String>{};

  @override
  Future<void> delete(String key) async {
    _values.remove(key);
  }

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String value) async {
    _values[key] = value;
  }
}

ActorQueuePartition _partition() {
  return ActorQueuePartition(
    environment: 'alpha',
    accountId: 'account-a',
    personaId: 'persona-a',
    deviceId: 'device-a',
  );
}

class _FailingOpsEventRepository extends MockOpsEventRepository {
  @override
  Future<OpsEventBatchAck> reportEventBatch({
    required List<OpsEventRecordInput> events,
  }) async {
    throw StateError('ops unavailable');
  }
}
