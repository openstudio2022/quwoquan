import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_event_record_errors.g.dart';
import 'package:quwoquan_app/core/telemetry/app_page_experience_tracker.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';

void main() {
  test(
    'first usable records exactly one explicit terminal for a visit',
    () async {
      var now = DateTime.utc(2026, 7, 20, 10);
      final context = AppPageContextStore.instance..setPageName('home');
      final recorder = _CapturingRecorder();
      final tracker = AppPageExperienceTracker(
        pageContextStore: context,
        now: () => now,
      )..attachReporter(recorder);
      tracker.beginPageVisit(
        pageName: 'home',
        pageVisitId: 'visit-1',
        openedAt: now,
      );

      now = now.add(const Duration(milliseconds: 1250));
      expect(
        await tracker.recordFirstUsable(
          terminal: AppPageUsableTerminal.empty,
          surfaceId: 'home_feed',
        ),
        AppTelemetryRecordResult.accepted,
      );
      expect(
        await tracker.recordFirstUsable(
          terminal: AppPageUsableTerminal.content,
        ),
        AppTelemetryRecordResult.rejected,
      );

      expect(recorder.records, hasLength(1));
      expect(recorder.records.single.payload.eventType, 'page_first_usable');
      expect(recorder.records.single.pageName, 'home');
      expect(recorder.records.single.payload.extensions, <String, Object?>{
        'durationMs': 1250,
        'terminalState': 'empty',
        'surfaceId': 'home_feed',
      });
    },
  );

  test(
    'lifecycle terminal vocabulary maps only explicit usable states',
    () async {
      const expected = <String, String>{
        'onlineSuccess': 'content',
        'contentReady': 'content',
        'cacheFallback': 'content',
        'partial': 'content',
        'emptyState': 'empty',
        'emptySuccess': 'empty',
        'blockingFailure': 'error',
      };
      final context = AppPageContextStore.instance..setPageName('home');

      for (final entry in expected.entries) {
        final recorder = _CapturingRecorder();
        final tracker = AppPageExperienceTracker(pageContextStore: context)
          ..attachReporter(recorder)
          ..beginPageVisit(
            pageName: 'home',
            pageVisitId: 'visit-${entry.key}',
            openedAt: DateTime.now(),
          );

        expect(
          await tracker.recordLifecycleTerminal(
            pageName: 'home',
            phase: entry.key,
          ),
          AppTelemetryRecordResult.accepted,
        );
        expect(
          recorder.records.single.payload.extensions['terminalState'],
          entry.value,
        );
      }

      final recorder = _CapturingRecorder();
      final tracker = AppPageExperienceTracker(pageContextStore: context)
        ..attachReporter(recorder)
        ..beginPageVisit(
          pageName: 'home',
          pageVisitId: 'visit-loading',
          openedAt: DateTime.now(),
        );
      expect(
        await tracker.recordLifecycleTerminal(
          pageName: 'home',
          phase: 'onlineLoading',
        ),
        AppTelemetryRecordResult.rejected,
      );
      expect(recorder.records, isEmpty);
    },
  );

  test('page error outcome always has canonical fallback semantics', () async {
    final context = AppPageContextStore.instance..setPageName('chat');
    final recorder = _CapturingRecorder();
    final tracker = AppPageExperienceTracker(pageContextStore: context)
      ..attachReporter(recorder);

    await tracker.recordPageErrorOutcome(result: 'shown');

    final payload = recorder.records.single.payload;
    expect(payload.eventType, 'page_error_outcome');
    expect(payload.extensions['surfaceId'], 'chat');
    expect(
      payload.extensions['errorCode'],
      OpsEventRecordErrorCode.unclassifiedPageFailure.code,
    );
    expect(payload.extensions['recoveryAction'], 'absorb');
    expect(payload.extensions['result'], 'shown');
  });

  test(
    'ANR outcomes dedupe the same source inside the frozen window',
    () async {
      var now = DateTime.utc(2026, 7, 20, 10);
      final context = AppPageContextStore.instance..setPageName('home');
      final recorder = _CapturingRecorder();
      final tracker = AppPageExperienceTracker(
        pageContextStore: context,
        now: () => now,
      )..attachReporter(recorder);

      expect(
        await tracker.recordAnrOutcome(
          detectionSource: 'dart_event_loop_watchdog',
          result: 'detected',
          durationMs: 7000,
        ),
        AppTelemetryRecordResult.accepted,
      );
      now = now.add(const Duration(seconds: 5));
      expect(
        await tracker.recordAnrOutcome(
          detectionSource: 'dart_event_loop_watchdog',
          result: 'detected',
          durationMs: 6000,
        ),
        AppTelemetryRecordResult.rejected,
      );
      now = now.add(const Duration(seconds: 6));
      expect(
        await tracker.recordAnrOutcome(
          detectionSource: 'dart_event_loop_watchdog',
          result: 'detected',
          durationMs: 6000,
        ),
        AppTelemetryRecordResult.accepted,
      );

      expect(recorder.records, hasLength(2));
      expect(recorder.records.first.payload.eventType, 'app_anr_outcome');
      expect(recorder.records.first.payload.extensions, <String, Object?>{
        'detectionSource': 'dart_event_loop_watchdog',
        'result': 'detected',
        'durationMs': 7000,
      });
    },
  );

  test(
    'telemetry persistence failures never escape into product flows',
    () async {
      final context = AppPageContextStore.instance..setPageName('home');
      final tracker = AppPageExperienceTracker(pageContextStore: context)
        ..attachReporter(_ThrowingRecorder())
        ..beginPageVisit(
          pageName: 'home',
          pageVisitId: 'visit-failing-recorder',
          openedAt: DateTime.now(),
        );

      expect(
        await tracker.recordFirstUsable(
          terminal: AppPageUsableTerminal.content,
        ),
        AppTelemetryRecordResult.rejected,
      );
      expect(
        await tracker.recordPageErrorOutcome(result: 'shown'),
        AppTelemetryRecordResult.rejected,
      );
      expect(
        await tracker.recordAnrOutcome(
          detectionSource: 'dart_event_loop_watchdog',
          result: 'detected',
        ),
        AppTelemetryRecordResult.rejected,
      );
    },
  );
}

final class _CapturedRecord {
  const _CapturedRecord(this.payload, this.pageName);

  final AppTelemetryPayload payload;
  final String? pageName;
}

final class _CapturingRecorder implements AppTelemetryRecorder {
  final List<_CapturedRecord> records = <_CapturedRecord>[];

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  void onNetworkAvailable() {}

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    records.add(_CapturedRecord(payload, pageName));
    return AppTelemetryRecordResult.accepted;
  }
}

final class _ThrowingRecorder implements AppTelemetryRecorder {
  @override
  Future<void> clearPendingForLogout() async {}

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  void onNetworkAvailable() {}

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) {
    throw StateError('simulated telemetry persistence failure');
  }
}
