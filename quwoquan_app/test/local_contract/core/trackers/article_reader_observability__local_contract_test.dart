// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-013

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/trackers/article_reader_observability.dart';

void main() {
  test(
    'reader lifecycle emits catalogued product-ops facts with canonical recovery context',
    () async {
      final recorder = _CapturingRecorder();
      final tracker = ArticleReaderObservability(
        AnalyticsService.forTesting(),
        recorder,
      );

      tracker.trackReaderOpen(
        postId: 'post-1',
        durationMs: 42,
        source: 'feed',
        template: 'standard',
        fontPreset: 'default',
        pageCount: 3,
        bookReaderEnabled: true,
      );
      tracker.trackReaderDwell(postId: 'post-1', durationMs: 2000);
      tracker.trackReaderExit(postId: 'post-1', durationMs: 2100);
      tracker.trackReaderError(
        postId: 'post-1',
        errorCode: 'CONTENT.SYSTEM.required_dependency_unavailable',
        recoveryAction: 'retry',
        durationMs: 100,
      );
      tracker.trackReaderRecovery(
        postId: 'post-1',
        recoveryAction: 'retry',
        result: 'success',
        durationMs: 50,
        errorCode: 'CONTENT.SYSTEM.required_dependency_unavailable',
      );

      await Future<void>.delayed(Duration.zero);

      expect(recorder.payloads.map((payload) => payload.eventType), <String>[
        'article_reader_enter',
        'article_reader_dwell',
        'article_reader_exit',
        'article_reader_error',
        'article_reader_recovery',
      ]);
      expect(
        recorder.payloads.every(
          (payload) => AppTelemetryCatalog.validate(payload) == null,
        ),
        isTrue,
      );
      expect(
        recorder.payloads[3].extensions['errorCode'],
        'CONTENT.SYSTEM.required_dependency_unavailable',
      );
      expect(recorder.payloads[4].extensions['recoveryAction'], 'retry');
    },
  );

  test('reader fallback 去重按 30 分钟 TTL 与 LRU 容量保持有界', () async {
    var now = DateTime.utc(2026, 7, 28, 10);
    final recorder = _CapturingRecorder();
    final tracker = ArticleReaderObservability(
      AnalyticsService.forTesting(telemetryReporter: recorder),
      recorder,
      fallbackDedupCapacity: 2,
      fallbackDedupTtl: const Duration(minutes: 30),
      now: () => now,
    );

    tracker.trackReaderFallback(
      postId: 'post-1',
      reason: 'long_document',
      bookReaderEnabled: true,
    );
    tracker.trackReaderFallback(
      postId: 'post-2',
      reason: 'long_document',
      bookReaderEnabled: true,
    );
    tracker.trackReaderFallback(
      postId: 'post-3',
      reason: 'long_document',
      bookReaderEnabled: true,
    );
    await Future<void>.delayed(Duration.zero);
    expect(tracker.debugFallbackDedupEntryCount, 2);
    expect(recorder.payloads, hasLength(3));

    tracker.trackReaderFallback(
      postId: 'post-1',
      reason: 'long_document',
      bookReaderEnabled: true,
    );
    tracker.trackReaderFallback(
      postId: 'post-1',
      reason: 'long_document',
      bookReaderEnabled: true,
    );
    await Future<void>.delayed(Duration.zero);
    expect(recorder.payloads, hasLength(4));

    now = now.add(const Duration(minutes: 31));
    tracker.trackReaderFallback(
      postId: 'post-1',
      reason: 'long_document',
      bookReaderEnabled: true,
    );
    await Future<void>.delayed(Duration.zero);
    expect(recorder.payloads, hasLength(5));
    expect(tracker.debugFallbackDedupEntryCount, 1);
  });
}

final class _CapturingRecorder implements AppTelemetryRecorder {
  final List<AppTelemetryPayload> payloads = <AppTelemetryPayload>[];

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
    payloads.add(payload);
    return AppTelemetryRecordResult.accepted;
  }
}
