import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/ops/product_ops/event_record/application/startup_telemetry.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('Dart bootstrap 与持久化遥测复用同一初始 attemptId', () async {
    final transport = _RecordingTransport(
      const StartupTelemetryBatchAck(acceptedCount: 1, duplicateCount: 0),
    );
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(_MemoryStartupJournalStore()),
      transport: transport,
      platform: 'android',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
      initialAttemptId: 'bootstrap_attempt_1234567890',
      isDetailedAttemptSampled: (_) => true,
    );

    await reporter.record(
      phase: StartupTelemetryPhase.terminal,
      elapsedMs: 1000,
      outcome: 'success',
    );
    await reporter.flush();

    expect(
      transport.batches.expand((batch) => batch).single.attemptId,
      'bootstrap_attempt_1234567890',
    );
  });

  test('启动事件只有完整 ACK 后才从离线 journal 删除', () async {
    final store = _MemoryStartupJournalStore();
    final transport = _RecordingTransport(
      const StartupTelemetryBatchAck(acceptedCount: 0, duplicateCount: 0),
    );
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store),
      transport: transport,
      platform: 'android',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
      isDetailedAttemptSampled: (_) => true,
    );

    await reporter.record(
      phase: StartupTelemetryPhase.dartBootstrap,
      elapsedMs: 10,
      outcome: 'started',
    );
    await reporter.flush();

    expect(await store.readEvents(), hasLength(1));
    expect(transport.batches, hasLength(1));

    transport.ack = const StartupTelemetryBatchAck(
      acceptedCount: 1,
      duplicateCount: 0,
    );
    await reporter.flush();

    expect(await store.readEvents(), isEmpty);
  });

  test('canonical log sink 不可用时保留 journal 且不阻断安全终态', () async {
    final store = _MemoryStartupJournalStore();
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store),
      transport: _UnavailableStartupTelemetryTransport(),
      platform: 'ios',
      runtimeEnv: 'gamma',
      appVersion: '1.0.0',
      isDetailedAttemptSampled: (_) => true,
    );

    await reporter.record(
      phase: StartupTelemetryPhase.terminal,
      elapsedMs: 1200,
      outcome: 'success',
    );
    await expectLater(reporter.flush(), completes);

    expect(await store.readEvents(), hasLength(1));
  });

  test('原生 journal 使用同一 attempt 并在转存后清空来源', () async {
    const nativeAttemptId = 'nativeattemptidentifier000001';
    final nativeEvent = <String, Object?>{
      'eventId': '${nativeAttemptId}_1',
      'attemptId': nativeAttemptId,
      'sequence': 1,
      'phase': 'native_pre_flutter',
      'phaseDurationMs': 4,
      'elapsedMs': 4,
      'outcome': 'observed',
      'occurredAt': '2026-07-17T10:00:00.000Z',
      'platform': 'android',
      'runtimeEnv': 'unknown',
      'deadlineOrigin': 'android_process',
    };
    final nativeEventLater = <String, Object?>{
      ...nativeEvent,
      'eventId': '${nativeAttemptId}_2',
      'sequence': 2,
      'phase': 'flutter_first_frame',
      'phaseDurationMs': 8,
      'elapsedMs': 12,
      'outcome': 'painted',
    };
    SharedPreferences.setMockInitialValues(<String, Object>{
      'startup_telemetry_native_attempt': nativeAttemptId,
      'startup_telemetry_native_journal': <String>[
        jsonEncode(nativeEventLater),
        jsonEncode(nativeEvent),
      ],
    });
    final store = _MemoryStartupJournalStore();
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store),
      transport: _RecordingTransport(
        const StartupTelemetryBatchAck(acceptedCount: 0, duplicateCount: 0),
      ),
      platform: 'android',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
      isDetailedAttemptSampled: (_) => true,
    );

    await reporter.record(
      phase: StartupTelemetryPhase.dartBootstrap,
      elapsedMs: 12,
      outcome: 'started',
    );

    final events = await StartupJournal(store).read();
    expect(events, hasLength(3));
    expect(events.map((event) => event.sequence), <int>[1, 2, 3]);
    expect(events.every((event) => event.attemptId == nativeAttemptId), isTrue);
    final preferences = await SharedPreferences.getInstance();
    expect(
      preferences.getStringList('startup_telemetry_native_journal'),
      isNull,
    );
  });

  test('首帧前通过 startup bridge 转存原生 journal，不依赖延后插件', () async {
    const channel = MethodChannel('quwoquan/startup/timings');
    const nativeAttemptId = 'bridgeattemptidentifier000001';
    var cleared = false;
    final nativeEvent = <String, Object?>{
      'eventId': '${nativeAttemptId}_1',
      'attemptId': nativeAttemptId,
      'sequence': 1,
      'phase': 'native_pre_flutter',
      'phaseDurationMs': 3,
      'elapsedMs': 3,
      'outcome': 'observed',
      'occurredAt': '2026-07-17T10:00:00.000Z',
      'platform': 'ios',
      'runtimeEnv': 'unknown',
      'deadlineOrigin': 'ios_process',
      'networkClass': 'user@example.com',
      'appVersion': '1.0.0+user@example.com',
      'failureCode': 'token_like_diagnostic_must_not_escape',
    };
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          switch (call.method) {
            case 'readStartupJournal':
              return <String, Object?>{
                'attemptId': nativeAttemptId,
                'events': <String>[jsonEncode(nativeEvent)],
              };
            case 'clearStartupJournal':
              cleared = true;
              return null;
          }
          return null;
        });
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null),
    );
    final store = _MemoryStartupJournalStore();
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store),
      transport: _RecordingTransport(
        const StartupTelemetryBatchAck(acceptedCount: 0, duplicateCount: 0),
      ),
      platform: 'ios',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
    );

    await reporter.record(
      phase: StartupTelemetryPhase.dartBootstrap,
      elapsedMs: 10,
      outcome: 'started',
    );

    final events = await StartupJournal(store).read();
    expect(events.map((event) => event.sequence), <int>[1, 2]);
    expect(events.every((event) => event.attemptId == nativeAttemptId), isTrue);
    expect(events.first.networkClass, isEmpty);
    expect(events.first.appVersion, isEmpty);
    expect(events.first.failureCode, isEmpty);
    expect(cleared, isTrue);
  });

  test('可靠 journal 暂不可写时保留原生来源供下次补传', () async {
    const channel = MethodChannel('quwoquan/startup/timings');
    const nativeAttemptId = 'retrybridgeattemptidentifier01';
    var cleared = false;
    final nativeEvent = <String, Object?>{
      'eventId': '${nativeAttemptId}_1',
      'attemptId': nativeAttemptId,
      'sequence': 1,
      'phase': 'native_pre_flutter',
      'phaseDurationMs': 3,
      'elapsedMs': 3,
      'outcome': 'observed',
      'occurredAt': '2026-07-17T10:00:00.000Z',
      'platform': 'ios',
      'runtimeEnv': 'unknown',
      'deadlineOrigin': 'ios_process',
    };
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'readStartupJournal') {
            return <String, Object?>{
              'attemptId': nativeAttemptId,
              'events': <String>[jsonEncode(nativeEvent)],
            };
          }
          if (call.method == 'clearStartupJournal') {
            cleared = true;
          }
          return null;
        });
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null),
    );

    await StartupTelemetryReporter(
      journal: StartupJournal(_WriteFailingStartupJournalStore()),
      transport: _RecordingTransport(
        const StartupTelemetryBatchAck(acceptedCount: 0, duplicateCount: 0),
      ),
      platform: 'ios',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
    ).start();

    expect(cleared, isFalse);
  });

  test('原生导入首写失败后重试仍保留原始 sequence 和 attempt', () async {
    const channel = MethodChannel('quwoquan/startup/timings');
    const nativeAttemptId = 'retrysequenceattemptidentifier1';
    var cleared = false;
    final nativeEvent = <String, Object?>{
      'eventId': '${nativeAttemptId}_1',
      'attemptId': nativeAttemptId,
      'sequence': 1,
      'phase': 'native_pre_flutter',
      'phaseDurationMs': 3,
      'elapsedMs': 3,
      'outcome': 'observed',
      'occurredAt': '2026-07-17T10:00:00.000Z',
      'platform': 'ios',
      'runtimeEnv': 'unknown',
      'deadlineOrigin': 'ios_process',
    };
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'readStartupJournal') {
            return <String, Object?>{
              'attemptId': nativeAttemptId,
              'events': <String>[jsonEncode(nativeEvent)],
            };
          }
          if (call.method == 'clearStartupJournal') {
            cleared = true;
          }
          return null;
        });
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null),
    );
    final store = _FailOnceStartupJournalStore();
    final transport = _RecordingTransport(
      const StartupTelemetryBatchAck(acceptedCount: 0, duplicateCount: 0),
    );
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store),
      transport: transport,
      platform: 'ios',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
    );

    await reporter.record(
      phase: StartupTelemetryPhase.dartBootstrap,
      elapsedMs: 10,
      outcome: 'started',
    );
    await reporter.flush();

    final batch = transport.batches.single;
    expect(batch.map((event) => event.sequence), <int>[1, 2]);
    expect(batch.every((event) => event.attemptId == nativeAttemptId), isTrue);
    expect(cleared, isTrue);
  });

  test('容量淘汰会保留可上报的 journal_drop 终态', () async {
    final store = _MemoryStartupJournalStore();
    final transport = _RecordingTransport(
      const StartupTelemetryBatchAck(acceptedCount: 0, duplicateCount: 0),
    );
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store, maxEvents: 1),
      transport: transport,
      platform: 'android',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
    );

    await reporter.record(
      phase: StartupTelemetryPhase.dartBootstrap,
      elapsedMs: 1,
      outcome: 'started',
    );
    await reporter.record(
      phase: StartupTelemetryPhase.configurationValidation,
      elapsedMs: 2,
      outcome: 'validated',
    );
    await reporter.flush();

    expect(transport.batches, hasLength(1));
    expect(transport.batches.single.single.outcome, 'journal_drop');
  });

  test('未命中详细采样仍保留每次启动的 terminal 摘要', () async {
    final store = _MemoryStartupJournalStore();
    final transport = _RecordingTransport(
      const StartupTelemetryBatchAck(acceptedCount: 0, duplicateCount: 0),
    );
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store),
      transport: transport,
      platform: 'android',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
      isDetailedAttemptSampled: (_) => false,
    );

    await reporter.record(
      phase: StartupTelemetryPhase.dartBootstrap,
      elapsedMs: 1,
      outcome: 'started',
    );
    await reporter.record(
      phase: StartupTelemetryPhase.terminal,
      elapsedMs: 10,
      outcome: 'success',
    );
    await reporter.flush();

    expect(
      transport.batches.single.map((event) => event.phase),
      <StartupTelemetryPhase>[StartupTelemetryPhase.terminal],
    );
    expect(
      (await StartupJournal(store).read()).map((event) => event.phase).toList(),
      <StartupTelemetryPhase>[StartupTelemetryPhase.terminal],
    );
  });

  test('超过服务端上限时会拆成受限批次并在完整 ACK 后清空', () async {
    final store = _MemoryStartupJournalStore();
    final transport = _AcknowledgingTransport();
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store),
      transport: transport,
      platform: 'android',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
      isDetailedAttemptSampled: (_) => true,
    );

    for (var index = 1; index <= 33; index++) {
      await reporter.record(
        phase: StartupTelemetryPhase.dartBootstrap,
        elapsedMs: index,
        outcome: 'started',
      );
    }
    await reporter.flush();

    expect(transport.batches.map((batch) => batch.length), <int>[32, 1]);
    expect(await store.readEvents(), isEmpty);
  });

  test('本地 journal 在落盘前剔除未声明的诊断字段值', () async {
    final store = _MemoryStartupJournalStore();
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store),
      transport: _RecordingTransport(
        const StartupTelemetryBatchAck(acceptedCount: 0, duplicateCount: 0),
      ),
      platform: 'untrusted_platform',
      runtimeEnv: 'untrusted_env',
      appVersion: '1.0.0+user@example.com',
    );

    await reporter.record(
      phase: StartupTelemetryPhase.recovery,
      elapsedMs: 12,
      outcome: 'raw_exception_text',
      networkClass: 'user@example.com',
      recoverySurface: 'custom_recovery',
      failureCode: 'token_like_diagnostic_must_not_escape',
      failureSource: 'stack_trace',
      deadlineOrigin: 'caller_controlled_clock',
    );

    final event = (await StartupJournal(store).read()).single;
    expect(event.outcome, 'unknown');
    expect(event.platform, 'unknown');
    expect(event.runtimeEnv, 'unknown');
    expect(event.networkClass, isEmpty);
    expect(event.recoverySurface, isEmpty);
    expect(event.failureCode, isEmpty);
    expect(event.failureSource, isEmpty);
    expect(event.deadlineOrigin, isEmpty);
    expect(event.appVersion, isEmpty);
  });

  test('安全 Shell 首帧会独立收口 terminal，不伪造首页可用', () async {
    final transport = _RecordingTransport(
      const StartupTelemetryBatchAck(acceptedCount: 0, duplicateCount: 0),
    );
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(_MemoryStartupJournalStore()),
      transport: transport,
      platform: 'android',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
    );
    StartupTelemetryRuntime.instance.configure(reporter);
    final runtime = AppStartupRuntime.instance..resetForTesting();

    runtime.markBootstrapStarted();
    runtime.markFirstFramePainted();
    runtime.markShellFirstPainted();
    await Future<void>.delayed(const Duration(milliseconds: 50));
    await reporter.flush();

    final eventsById = <String, StartupTelemetryEvent>{
      for (final event in transport.batches.expand((batch) => batch))
        event.eventId: event,
    };
    final events = eventsById.values.toList(growable: false);
    expect(
      events.where((event) => event.phase == StartupTelemetryPhase.terminal),
      hasLength(1),
    );
    expect(
      events
          .where((event) => event.phase == StartupTelemetryPhase.terminal)
          .single
          .outcome,
      'success',
    );
    expect(
      events.where(
        (event) => event.phase == StartupTelemetryPhase.homeFeedFirstUsable,
      ),
      isEmpty,
    );
  });

  test('首帧前仅缓冲启动遥测，不触发 durable journal 或远端 transport', () async {
    final store = _CountingStartupJournalStore();
    final transport = _RecordingTransport(
      const StartupTelemetryBatchAck(acceptedCount: 0, duplicateCount: 0),
    );
    StartupTelemetryRuntime.instance.configure(
      StartupTelemetryReporter(
        journal: StartupJournal(store),
        transport: transport,
        platform: 'android',
        runtimeEnv: 'alpha',
        appVersion: '1.0.0',
      ),
    );

    StartupTelemetryRuntime.instance.record(
      phase: StartupTelemetryPhase.dartBootstrap,
      elapsedMs: 1,
      outcome: 'started',
    );
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(store.readCount, 0);
    expect(store.writeCount, 0);
    expect(transport.batches, isEmpty);

    StartupTelemetryRuntime.instance.activateAfterFirstFrame();
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(store.readCount, greaterThan(0));
    expect(store.writeCount, greaterThan(0));
    expect(transport.batches, isEmpty);
  });
}

final class _MemoryStartupJournalStore implements StartupJournalStore {
  final List<String> _events = <String>[];
  String? _proof;

  @override
  Future<List<String>> readEvents() async => List<String>.from(_events);

  @override
  Future<String?> readProof() async => _proof;

  @override
  Future<void> writeEvents(List<String> encodedEvents) async {
    _events
      ..clear()
      ..addAll(encodedEvents);
  }

  @override
  Future<void> writeProof(String proof) async {
    _proof = proof;
  }
}

final class _CountingStartupJournalStore implements StartupJournalStore {
  int readCount = 0;
  int writeCount = 0;
  final List<String> _events = <String>[];
  String? _proof;

  @override
  Future<List<String>> readEvents() async {
    readCount++;
    return List<String>.from(_events);
  }

  @override
  Future<void> writeEvents(List<String> encodedEvents) async {
    writeCount++;
    _events
      ..clear()
      ..addAll(encodedEvents);
  }

  @override
  Future<String?> readProof() async {
    readCount++;
    return _proof;
  }

  @override
  Future<void> writeProof(String proof) async {
    writeCount++;
    _proof = proof;
  }
}

final class _RecordingTransport implements StartupTelemetryTransport {
  _RecordingTransport(this.ack);

  StartupTelemetryBatchAck ack;
  final List<List<StartupTelemetryEvent>> batches =
      <List<StartupTelemetryEvent>>[];

  @override
  Future<StartupTelemetryBatchAck> report(
    List<StartupTelemetryEvent> events, {
    required String proof,
  }) async {
    batches.add(List<StartupTelemetryEvent>.from(events));
    return ack;
  }
}

final class _UnavailableStartupTelemetryTransport
    implements StartupTelemetryTransport {
  @override
  Future<StartupTelemetryBatchAck> report(
    List<StartupTelemetryEvent> events, {
    required String proof,
  }) {
    throw StateError('product-ops unavailable');
  }
}

final class _AcknowledgingTransport implements StartupTelemetryTransport {
  final List<List<StartupTelemetryEvent>> batches =
      <List<StartupTelemetryEvent>>[];

  @override
  Future<StartupTelemetryBatchAck> report(
    List<StartupTelemetryEvent> events, {
    required String proof,
  }) async {
    batches.add(List<StartupTelemetryEvent>.from(events));
    return StartupTelemetryBatchAck(
      acceptedCount: events.length,
      duplicateCount: 0,
    );
  }
}

final class _WriteFailingStartupJournalStore implements StartupJournalStore {
  @override
  Future<List<String>> readEvents() async => const <String>[];

  @override
  Future<String?> readProof() async => null;

  @override
  Future<void> writeEvents(List<String> encodedEvents) {
    throw StateError('storage is not ready');
  }

  @override
  Future<void> writeProof(String proof) async {}
}

final class _FailOnceStartupJournalStore implements StartupJournalStore {
  final List<String> _events = <String>[];
  var _writeCount = 0;
  String? _proof;

  @override
  Future<List<String>> readEvents() async => List<String>.from(_events);

  @override
  Future<String?> readProof() async => _proof;

  @override
  Future<void> writeEvents(List<String> encodedEvents) async {
    _writeCount += 1;
    if (_writeCount == 1) {
      throw StateError('storage is not ready');
    }
    _events
      ..clear()
      ..addAll(encodedEvents);
  }

  @override
  Future<void> writeProof(String proof) async {
    _proof = proof;
  }
}
