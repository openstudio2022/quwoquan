import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_transport.dart';
import 'package:quwoquan_app/infrastructure/local/actor_queue/actor_queue_storage.dart';

const _environment = 'gamma';
const _primaryAccountId = 'account-a';
const _secondaryAccountId = 'account-b';
const _personaId = 'persona-a';
const _deviceId = 'install-a';
final _testNow = DateTime.utc(2026, 7, 18, 8);

void main() {
  late Directory tempDirectory;
  late ActorQueuePartition partition;
  late ActorQueueStorage storage;
  late List<ActorQueueSignal> actorSignals;

  setUp(() async {
    tempDirectory = await Directory.systemTemp.createTemp('telemetry_outbox_');
    Hive.init(tempDirectory.path);
    partition = ActorQueuePartition(
      environment: _environment,
      accountId: _primaryAccountId,
      personaId: _personaId,
      deviceId: _deviceId,
    );
    actorSignals = <ActorQueueSignal>[];
    storage = ActorQueueStorage(
      keyStore: _MemoryKeyStore(),
      signalObserver: actorSignals.add,
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  test('超时后重试复用完全相同的密封 body 与摘要并在 ACK 后删除', () async {
    final transport = _RecordingTransport()..failAfterAcceptOnce = true;
    final outbox = AppTelemetryOutbox(
      partition: partition,
      storage: storage,
      transport: transport,
      now: () => _testNow,
    );
    await outbox.enqueue(_record(1));
    await outbox.enqueue(_record(2));

    expect(await outbox.flush(), AppTelemetryFlushResult.deferred);
    expect(await outbox.pendingCount(), 2);
    expect(await outbox.flush(), AppTelemetryFlushResult.delivered);
    expect(await outbox.pendingCount(), 0);
    expect(transport.bodies, hasLength(2));
    expect(transport.bodies.toSet(), hasLength(1));
    expect(transport.keys.toSet(), hasLength(1));
  });

  test('product-ops 不可达时保留主体隔离的批次且不阻断调用方', () async {
    final unavailable = _RecordingTransport()..failAfterAcceptOnce = true;
    final outbox = AppTelemetryOutbox(
      partition: partition,
      storage: storage,
      transport: unavailable,
      now: () => _testNow,
    );
    await outbox.enqueue(_record(1));

    expect(await outbox.flush(), AppTelemetryFlushResult.deferred);
    expect(await outbox.pendingCount(), 1);

    final otherActor = AppTelemetryOutbox(
      partition: ActorQueuePartition(
        environment: _environment,
        accountId: _secondaryAccountId,
        personaId: _personaId,
        deviceId: _deviceId,
      ),
      storage: storage,
      transport: unavailable,
    );
    expect(await otherActor.pendingCount(), 0);
  });

  test('单条 422 进入加密 DLQ，401 保留密封批次等待主体变化', () async {
    final invalidTransport = _RecordingTransport()..statusCode = 422;
    final invalid = AppTelemetryOutbox(
      partition: partition,
      storage: storage,
      transport: invalidTransport,
      now: () => _testNow,
    );
    await invalid.enqueue(_record(1));
    expect(await invalid.flush(), AppTelemetryFlushResult.deadLettered);
    expect(await invalid.pendingCount(), 0);
    final dlq = await storage.open(partition, '${kAppTelemetryOutboxName}_dlq');
    expect(dlq, isNotNull);
    expect(dlq!.length, 1);
    await invalid.purge();

    final blockedTransport = _RecordingTransport()..statusCode = 401;
    final blocked = AppTelemetryOutbox(
      partition: partition,
      storage: storage,
      transport: blockedTransport,
      now: () => _testNow,
    );
    await blocked.enqueue(_record(2));
    expect(await blocked.flush(), AppTelemetryFlushResult.identityBlocked);
    expect(await blocked.pendingCount(), 1);
  });

  test('单条无效事件不会使同批有效事件进入 DLQ', () async {
    final transport = _SelectiveInvalidEventTransport();
    final outbox = AppTelemetryOutbox(
      partition: partition,
      storage: storage,
      transport: transport,
      now: () => _testNow,
    );
    await outbox.enqueue(_record(1));
    await outbox.enqueue(_record(2, eventType: 'undeclared_event'));

    expect(await outbox.flush(), AppTelemetryFlushResult.deadLettered);
    expect(await outbox.pendingCount(), 0);
    final dlq = await storage.open(partition, '${kAppTelemetryOutboxName}_dlq');
    expect(dlq, isNotNull);
    expect(dlq!.length, 1);
    expect(
      transport.acceptedEventTypes,
      contains('page_open'),
      reason: '合法事件必须在隔离发送后得到确认',
    );
    expect(transport.bodies, hasLength(3), reason: '先尝试原批次，再按原顺序逐条隔离');
  });

  test('容量不足将普通事件移入 DLQ 并保留 critical 事实', () async {
    final signals = <AppTelemetryDeliveryDegradation>[];
    final outbox = AppTelemetryOutbox(
      partition: partition,
      storage: storage,
      transport: _RecordingTransport(),
      maxRecords: 1,
      maxBytes: 1024 * 1024,
      deliveryObserver: (kind, _) => signals.add(kind),
    );
    expect(
      await outbox.enqueue(_record(1, droppable: true)),
      AppTelemetryEnqueueResult.persisted,
    );
    expect(
      await outbox.enqueue(_record(2, logType: 'error', critical: true)),
      AppTelemetryEnqueueResult.persisted,
    );
    expect(await outbox.pendingCount(), 1);
    expect(signals, contains(AppTelemetryDeliveryDegradation.deadLettered));
    expect(
      actorSignals.map((signal) => signal.kind),
      contains(ActorQueueSignalKind.overflowMoved),
    );
    final dlq = await storage.open(partition, '${kAppTelemetryOutboxName}_dlq');
    expect(dlq, isNotNull);
    expect(dlq!.length, 1);

    expect(
      await outbox.enqueue(_record(3, logType: 'error', critical: true)),
      AppTelemetryEnqueueResult.persisted,
    );
    expect(await outbox.pendingCount(), 2);
    expect(signals, contains(AppTelemetryDeliveryDegradation.retrying));
  });
}

AppTelemetryQueuedRecord _record(
  int index, {
  String logType = 'event',
  String? eventType,
  bool droppable = false,
  bool critical = false,
}) {
  final now = DateTime.utc(2026, 7, 18, 8, 0, index);
  final resolvedEventType =
      eventType ?? (logType == 'error' ? 'runtime_exception' : 'page_open');
  return AppTelemetryQueuedRecord(
    wire: <String, Object?>{
      'logType': logType,
      'eventType': resolvedEventType,
      'sessionId': 's.Z3Vlc3Q.1',
      'pageName': 'home',
      'occurredAt': now.toIso8601String(),
      'deviceManufacturer': 'Apple',
      'deviceModel': 'iPhone',
      'appVersion': '1.0.0+1',
      'networkClass': 'wifi',
      if (logType == 'error') 'errorCode': 'APP.RUNTIME.test',
    },
    logType: logType,
    eventType: resolvedEventType,
    enqueuedAt: now,
    expiresAt: now.add(const Duration(hours: 24)),
    droppable: droppable,
    critical: critical,
  );
}

final class _RecordingTransport implements AppTelemetryTransport {
  final List<String> bodies = <String>[];
  final List<String> keys = <String>[];
  bool failAfterAcceptOnce = false;
  int statusCode = 0;

  @override
  Future<AppTelemetryBatchAck> sendSealedBatch({
    required String canonicalBody,
    required String idempotencyKey,
  }) async {
    bodies.add(canonicalBody);
    keys.add(idempotencyKey);
    if (statusCode != 0) {
      throw CloudErrorMapper.fromStatusCode(statusCode);
    }
    if (failAfterAcceptOnce) {
      failAfterAcceptOnce = false;
      throw StateError('write committed but ACK timed out');
    }
    final decoded = jsonDecode(canonicalBody) as Map<String, Object?>;
    return AppTelemetryBatchAck(
      acceptedCount: (decoded['events']! as List<Object?>).length,
      duplicateBatch: bodies.length > 1,
    );
  }
}

final class _SelectiveInvalidEventTransport implements AppTelemetryTransport {
  final List<String> bodies = <String>[];
  final List<String> acceptedEventTypes = <String>[];

  @override
  Future<AppTelemetryBatchAck> sendSealedBatch({
    required String canonicalBody,
    required String idempotencyKey,
  }) async {
    bodies.add(canonicalBody);
    final decoded = jsonDecode(canonicalBody) as Map<String, Object?>;
    final events = decoded['events']! as List<Object?>;
    if (events.length > 1) {
      throw CloudErrorMapper.fromStatusCode(422);
    }
    final event = events.single as Map<String, Object?>;
    final eventType = event['eventType']! as String;
    if (eventType == 'undeclared_event') {
      throw CloudErrorMapper.fromStatusCode(422);
    }
    acceptedEventTypes.add(eventType);
    return const AppTelemetryBatchAck(acceptedCount: 1, duplicateBatch: false);
  }
}

final class _MemoryKeyStore implements ActorQueueEncryptionKeyStore {
  final Map<String, String> values = <String, String>{};

  @override
  Future<void> delete(String key) async => values.remove(key);

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async => values[key] = value;
}
