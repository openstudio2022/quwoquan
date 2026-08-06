// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/startup/startup_telemetry.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart'
    as ops_contracts;
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    StartupTelemetryRuntime.instance.resetForTesting();
  });

  test('旧 recovery 自由字符串记录硬丢弃', () async {
    const attemptId = 'legacyrecoveryattempt000001';
    final store = _MemoryStore();
    await store.writeEvents(<String>[
      jsonEncode(<String, Object?>{
        'eventId': '${attemptId}_1',
        'attemptId': attemptId,
        'sequence': 1,
        'phase': 'recovery',
        'phaseDurationMs': 1,
        'elapsedMs': 1,
        'outcome': 'shown',
        'occurredAt': '2026-08-05T00:00:00.000Z',
        'platform': 'android',
        'runtimeEnv': 'alpha',
        'recoverySurface': 'safe_recovery',
      }),
    ]);

    expect(await StartupJournal(store).read(), isEmpty);
  });

  test('同一 journal 分开发送 startup 与 typed recovery 批次', () async {
    final store = _MemoryStore();
    final transport = _RecordingTransport();
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store),
      transport: transport,
      platform: 'android',
      runtimeEnv: 'alpha',
      appVersion: '1.0.0',
      initialAttemptId: 'canonicalattemptidentifier0001',
      isDetailedAttemptSampled: (_) => true,
    );
    await reporter.record(
      phase: StartupTelemetryPhase.dartBootstrap,
      elapsedMs: 1,
      outcome: 'started',
    );
    await reporter.record(
      phase: StartupTelemetryPhase.recovery,
      elapsedMs: 2,
      outcome: 'entered',
      recoverySurface:
          ops_contracts.StartupRecoverySurface.pageAppStartupRecovery,
      recoveryLifecycle: ops_contracts.StartupRecoveryLifecycle.enter,
      recoveryMount: ops_contracts.StartupRecoveryMount.safeShell,
      recoveryPhase: ops_contracts.StartupRecoveryPhase.startupChecking,
      recoveryAction: ops_contracts.StartupRecoveryAction.none,
    );

    await reporter.flush();

    expect(transport.batches, hasLength(2));
    expect(transport.batches.first.single.isRecoveryTelemetry, isFalse);
    expect(transport.batches.last.single.isRecoveryTelemetry, isTrue);
    expect(await store.readEvents(), isEmpty);
  });

  test('pre-config journal 保留事件并在 attach 后使用同一 reporter flush', () async {
    final store = _MemoryStore();
    final reporter = StartupTelemetryReporter(
      journal: StartupJournal(store),
      platform: 'ios',
      runtimeEnv: 'beta',
      appVersion: '1.0.0',
      initialAttemptId: 'preconfigattemptidentifier001',
    );
    final transport = _RecordingTransport();
    StartupTelemetryRuntime.instance.initialize(reporter);
    final session = RecoverySurfaceTelemetrySession(
      mount: ops_contracts.StartupRecoveryMount.routerError,
      initialPhase: ops_contracts.StartupRecoveryPhase.startupChecking,
      elapsedMs: () => 10,
    );
    session.externalAction(
      action: ops_contracts.StartupRecoveryAction.openWeb,
      outcome: 'started',
    );
    session.externalAction(
      action: ops_contracts.StartupRecoveryAction.openWeb,
      outcome: 'started',
    );
    session.exit(outcome: 'success');

    StartupTelemetryRuntime.instance.activateAfterFirstFrame();
    StartupTelemetryRuntime.instance.markSafeTerminal();
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(transport.batches, isEmpty);
    expect(await store.readEvents(), hasLength(3));

    StartupTelemetryRuntime.instance.attachTransport(transport);
    await Future<void>.delayed(const Duration(milliseconds: 30));

    expect(transport.batches, hasLength(1));
    expect(transport.batches.single, hasLength(3));
    expect(
      transport.batches.single.map((event) => event.recoveryLifecycle),
      <ops_contracts.StartupRecoveryLifecycle?>[
        ops_contracts.StartupRecoveryLifecycle.enter,
        ops_contracts.StartupRecoveryLifecycle.externalAction,
        ops_contracts.StartupRecoveryLifecycle.exit,
      ],
    );
  });

  test('safe terminal 后发生的 runtime recovery 会立即复用同一 transport', () async {
    final transport = _RecordingTransport();
    StartupTelemetryRuntime.instance.initialize(
      StartupTelemetryReporter(
        journal: StartupJournal(_MemoryStore()),
        transport: transport,
        platform: 'android',
        runtimeEnv: 'gamma',
        appVersion: '1.0.0',
        initialAttemptId: 'runtimeattemptidentifier00001',
      ),
    );
    StartupTelemetryRuntime.instance.activateAfterFirstFrame();
    StartupTelemetryRuntime.instance.markSafeTerminal();
    await Future<void>.delayed(const Duration(milliseconds: 20));

    RecoverySurfaceTelemetrySession(
      mount: ops_contracts.StartupRecoveryMount.runtimeBoundary,
      initialPhase: ops_contracts.StartupRecoveryPhase.runtimeUnavailable,
      elapsedMs: () => 20,
      failureSource: 'runtime_boundary',
    );
    await Future<void>.delayed(const Duration(milliseconds: 40));

    final events = transport.batches.expand((batch) => batch).toList();
    expect(events, hasLength(2));
    expect(
      events.map((event) => event.recoveryLifecycle),
      <ops_contracts.StartupRecoveryLifecycle?>[
        ops_contracts.StartupRecoveryLifecycle.enter,
        ops_contracts.StartupRecoveryLifecycle.failure,
      ],
    );
  });
}

final class _MemoryStore implements StartupJournalStore {
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

final class _RecordingTransport implements StartupTelemetryTransport {
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
