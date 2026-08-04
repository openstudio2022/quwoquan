import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/ops/event_record_batch_writer.dart';
import 'package:quwoquan_app/core/observability/runtime_api_latency_dispatcher.dart';
import 'package:quwoquan_app/core/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/core/observability/runtime_log_record.dart';
import 'package:quwoquan_app/core/observability/runtime_log_transport.dart';
import 'package:quwoquan_app/core/observability/runtime_logger.dart';
import 'package:quwoquan_app/core/observability/secure_runtime_log_buffer.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart' as ops;

void main() {
  RuntimeLogResource resource() => const RuntimeLogResource(
    sourceType: 'app',
    environment: 'gamma',
    service: 'quwoquan_app',
    appVersion: '1.2.3+4',
  );

  test(
    'typed logger emits one canonical nested envelope and drops versions',
    () async {
      final buffer = _MemoryBuffer();
      final logger = RuntimeLogger(
        resource: resource(),
        buffer: buffer,
        now: () => DateTime.utc(2026, 7, 19, 1),
      );

      await logger.access(
        signal: 'app.access.http',
        method: 'GET',
        route: '/content/posts/{postId}',
        status: '200',
        durationMs: 24,
        message: 'GET /content/posts/123?access_token=secret',
        correlation: const RuntimeLogCorrelation(
          requestId: 'APP.content.post.get.t1.r1',
          traceId: 'APP.sess.content.post.get.t1.r1',
        ),
        attributes: const <String, String>{
          'releaseId': 'must-not-appear',
          'protocolVersion': 'must-not-appear',
          'releaseVersion': 'must-not-appear',
          'sessionId': 'must-not-appear',
        },
      );

      final wire = buffer.records.single.toWire();
      expect(wire['schema'], 'observability.slim');
      expect(wire['resource'], <String, String>{
        'sourceType': 'app',
        'service': 'quwoquan_app',
        'environment': 'gamma',
        'appVersion': '1.2.3+4',
      });
      expect(wire['correlation'], <String, String>{
        'requestId': 'APP.content.post.get.t1.r1',
        'traceId': 'APP.sess.content.post.get.t1.r1',
      });
      expect(wire.containsKey('releaseId'), isFalse);
      expect(wire.containsKey('attributes'), isFalse);
      expect(wire['message'], contains('***'));
    },
  );

  test(
    'secure ring buffer restores canonical records and limits capacity',
    () async {
      final store = _MemoryStore();
      final first = SecureRuntimeLogBuffer(store: store, capacity: 2);
      await first.append(_event(resource(), 'r1'));
      await first.append(_event(resource(), 'r2'));
      await first.append(_event(resource(), 'r3'));

      final restored = SecureRuntimeLogBuffer(store: store, capacity: 2);
      expect(
        (await restored.pending()).map((record) => record.recordId),
        <String>['r2', 'r3'],
      );

      store.value = '{malformed';
      final corrupted = SecureRuntimeLogBuffer(store: store);
      expect(await corrupted.pending(), isEmpty);
      expect(store.value, isNull);
    },
  );

  test('priority ordering prevents warning and error starvation', () async {
    final buffer = InMemoryRuntimeLogBuffer(capacity: 128);
    for (var index = 0; index < 50; index++) {
      await buffer.append(_event(resource(), 'info-$index'));
    }
    final error = _event(
      resource(),
      'error-1',
      severity: RuntimeLogSeverity.error,
    );
    await buffer.append(error);

    final pending = await buffer.pending();
    expect(pending.first.recordId, 'error-1');
  });

  test(
    'capacity eviction protects error records and writes bounded DLQ',
    () async {
      final buffer = InMemoryRuntimeLogBuffer(capacity: 2);
      await buffer.append(_event(resource(), 'info-old'));
      await buffer.append(
        _event(
          resource(),
          'error-protected',
          severity: RuntimeLogSeverity.error,
        ),
      );
      await buffer.append(_event(resource(), 'info-new'));

      final pending = await buffer.pending();
      expect(
        pending.map((record) => record.recordId),
        containsAll(<String>['error-protected', 'info-new']),
      );
      expect(
        pending.map((record) => record.recordId),
        isNot(contains('info-old')),
      );
      final deadLetters = await buffer.deadLetters();
      expect(deadLetters.single.record.recordId, 'info-old');
      expect(deadLetters.single.reason, 'capacity_evicted');
    },
  );

  test('permanent 422 moves batch to DLQ and unblocks queue', () async {
    final buffer = InMemoryRuntimeLogBuffer();
    final logger = RuntimeLogger(
      resource: resource(),
      buffer: buffer,
      transport: const _FailingTransport(permanent: true, reason: 'http_422'),
      now: DateTime.now,
    );
    await logger.exception(
      signal: 'app.exception.flutter',
      errorCode: 'APP.RUNTIME.test_failure',
      fingerprint: 'fp-permanent',
      message: 'permanent payload failure',
    );

    expect(await logger.flush(), RuntimeLogFlushResult.deadLettered);
    expect(await buffer.pending(), isEmpty);
    final deadLetters = await buffer.deadLetters();
    expect(deadLetters.single.reason, 'http_422');
    logger.dispose();
  });

  test('transient failures persist exponential retry metadata', () async {
    final now = DateTime.now().toUtc();
    final buffer = InMemoryRuntimeLogBuffer();
    final logger = RuntimeLogger(
      resource: resource(),
      buffer: buffer,
      transport: const _FailingTransport(permanent: false, reason: 'network'),
      now: () => now,
    );
    await logger.exception(
      signal: 'app.exception.flutter',
      errorCode: 'APP.RUNTIME.test_failure',
      fingerprint: 'fp-transient',
      message: 'temporary transport failure',
      occurredAt: now,
    );

    expect(await logger.flush(), RuntimeLogFlushResult.deferred);
    expect(await buffer.pending(), isEmpty);
    final next = await buffer.nextDeliveryAt();
    expect(next, isNotNull);
    expect(next!.isAfter(now), isTrue);
    expect(await buffer.deadLetters(), isEmpty);
    logger.dispose();
  });

  test('expired records enter DLQ instead of retrying forever', () async {
    final buffer = InMemoryRuntimeLogBuffer(ttl: const Duration(hours: 72));
    final old = DateTime.now().toUtc().subtract(const Duration(days: 4));
    await buffer.append(_eventAt(resource(), 'expired', old));

    expect(await buffer.expire(now: DateTime.now().toUtc()), 1);
    expect(await buffer.pending(), isEmpty);
    final deadLetters = await buffer.deadLetters();
    expect(deadLetters.single.reason, 'ttl_expired');
  });

  test(
    'only warning and error records are uploaded and acknowledged',
    () async {
      final buffer = _MemoryBuffer();
      final transport = _RecordingTransport();
      final logger = RuntimeLogger(
        resource: resource(),
        buffer: buffer,
        transport: transport,
        now: () => DateTime.utc(2026, 7, 19, 2),
      );
      await logger.runtime(
        signal: 'app.runtime.lifecycle',
        event: 'resumed',
        result: 'ok',
        message: 'app resumed',
      );
      await logger.exception(
        signal: 'app.exception.flutter',
        errorCode: 'APP.RUNTIME.test_failure',
        fingerprint: 'fp-test',
        message: 'test failure',
      );

      await logger.flush();
      expect(transport.sent, hasLength(1));
      expect(transport.sent.single.kind, RuntimeLogKind.exception);
      expect(buffer.records.map((record) => record.kind), <RuntimeLogKind>[
        RuntimeLogKind.runtime,
      ]);
    },
  );

  test('wire parser rejects schema, protocol, and release branches', () {
    for (final field in <String>[
      'schemaVersion',
      'protocolVersion',
      'releaseVersion',
      'releaseId',
    ]) {
      final wire = _event(resource(), 'r1').toWire()..[field] = 'forbidden';
      expect(
        () => RuntimeLogRecord.fromWire(wire),
        throwsA(isA<ArgumentError>()),
        reason: '$field must be rejected',
      );
    }
  });

  test(
    'cloud transport uses the generated runtime diagnostic operation',
    () async {
      final writer = _RecordingEventRecordBatchWriter();
      final transport = CloudRuntimeLogTransport(writer: writer);

      final accepted = await transport.send(<RuntimeLogRecord>[
        _event(resource(), 'r-transport'),
      ]);

      expect(accepted, 1);
      expect(writer.runtimeLogRequest!.records, hasLength(1));
      expect(writer.runtimeLogIdempotencyKey, hasLength(64));
      expect(writer.runtimeLogRequest!.records.single.toWire(), isA<Map>());
    },
  );

  test(
    'cloud latency becomes canonical access telemetry with a templated route',
    () async {
      final buffer = _MemoryBuffer();
      final logger = RuntimeLogger(resource: resource(), buffer: buffer);
      final dispatcher = RuntimeApiLatencyDispatcher()..bind(logger);

      dispatcher.record(
        'GET',
        '/content/posts/1d64e1e9-6667-40b9-a8d0-a54c7d1d2a45?token=must-not-appear',
        24,
        200,
      );
      await Future<void>.delayed(Duration.zero);

      final record = buffer.records.single;
      expect(record.kind, RuntimeLogKind.access);
      expect(record.signal, 'app.access.http');
      expect(record.route, '/content/posts/:id');
      expect(record.message, 'cloud HTTP request completed');
    },
  );
}

final class _RecordingEventRecordBatchWriter
    implements OpsEventRecordBatchWriter {
  ops.RuntimeLogBatchRequest? runtimeLogRequest;
  String? runtimeLogIdempotencyKey;

  @override
  Future<ops.EventRecordBatchReceipt> reportEventBatch(
    ops.EventRecordBatchRequest request, {
    required String idempotencyKey,
  }) {
    throw UnimplementedError('event batch is outside this local contract');
  }

  @override
  Future<ops.EventRecordBatchReceipt> reportRuntimeLogBatch(
    ops.RuntimeLogBatchRequest request, {
    required String idempotencyKey,
  }) async {
    runtimeLogRequest = request;
    runtimeLogIdempotencyKey = idempotencyKey;
    return ops.EventRecordBatchReceipt(
      acceptedCount: request.records.length,
      duplicateBatch: false,
    );
  }
}

RuntimeLogRecord _event(
  RuntimeLogResource resource,
  String id, {
  RuntimeLogSeverity severity = RuntimeLogSeverity.info,
}) {
  final timestamp = DateTime.now().toUtc();
  return RuntimeLogRecord(
    recordId: id,
    occurredAt: timestamp,
    observedAt: timestamp,
    kind: RuntimeLogKind.event,
    severity: severity,
    signal: 'app.performance.frame',
    message: 'event',
    resource: resource,
    correlation: const RuntimeLogCorrelation(),
    event: 'boot',
    result: 'ok',
  );
}

RuntimeLogRecord _eventAt(
  RuntimeLogResource resource,
  String id,
  DateTime occurredAt,
) => RuntimeLogRecord(
  recordId: id,
  occurredAt: occurredAt,
  observedAt: occurredAt,
  kind: RuntimeLogKind.event,
  severity: RuntimeLogSeverity.warn,
  signal: 'app.performance.frame',
  message: 'event',
  resource: resource,
  correlation: const RuntimeLogCorrelation(),
  event: 'frame_jank',
  result: 'degraded',
);

final class _MemoryBuffer implements RuntimeLogBuffer {
  final List<RuntimeLogRecord> records = <RuntimeLogRecord>[];

  @override
  Future<void> append(RuntimeLogRecord record) async => records.add(record);

  @override
  Future<void> clear() async => records.clear();

  @override
  Future<List<RuntimeLogRecord>> pending({int limit = 50}) async =>
      records.take(limit).toList(growable: false);

  @override
  Future<void> remove(Iterable<String> recordIds) async {
    final ids = recordIds.toSet();
    records.removeWhere((record) => ids.contains(record.recordId));
  }
}

final class _MemoryStore implements RuntimeLogRecordStore {
  String? value;

  @override
  Future<void> clear() async => value = null;

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String next) async => value = next;
}

final class _RecordingTransport implements RuntimeLogTransport {
  final List<RuntimeLogRecord> sent = <RuntimeLogRecord>[];

  @override
  Future<int> send(List<RuntimeLogRecord> records) async {
    sent.addAll(records);
    return records.length;
  }
}

final class _FailingTransport implements RuntimeLogTransport {
  const _FailingTransport({required this.permanent, required this.reason});

  final bool permanent;
  final String reason;

  @override
  Future<int> send(List<RuntimeLogRecord> records) {
    throw RuntimeLogTransportException(permanent: permanent, reason: reason);
  }
}
