import 'dart:ui' show AppLifecycleState;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/observability/runtime_diagnostics.dart';
import 'package:quwoquan_app/core/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/core/observability/runtime_log_record.dart';
import 'package:quwoquan_app/core/observability/runtime_logger.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/video_native_playback_signals.dart';
import 'package:quwoquan_app/core/telemetry/app_page_experience_tracker.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';

void main() {
  RuntimeLogger logger(InMemoryRuntimeLogBuffer buffer) => RuntimeLogger(
    resource: const RuntimeLogResource(
      sourceType: 'app',
      environment: 'alpha',
      service: 'quwoquan_app',
      appVersion: 'test',
    ),
    buffer: buffer,
    now: () => DateTime.utc(2026, 7, 19),
  );

  test('frame timing only upgrades actual jank batches', () async {
    final buffer = InMemoryRuntimeLogBuffer();
    final recorder = _CapturingTelemetryRecorder();
    final pageContext = AppPageContextStore.instance..setPageName('home');
    final experience = AppPageExperienceTracker(pageContextStore: pageContext)
      ..attachReporter(recorder);
    final diagnostics = AppRuntimeDiagnostics(
      logger(buffer),
      pageContextStore: pageContext,
      pageExperienceTracker: experience,
      frameBatchSize: 2,
      jankThreshold: const Duration(milliseconds: 50),
      severeFrameThreshold: const Duration(milliseconds: 200),
    );

    diagnostics.recordFrameDuration(const Duration(milliseconds: 16));
    diagnostics.recordFrameDuration(const Duration(milliseconds: 60));
    await _settle();

    final record = (await buffer.pending()).single;
    expect(record.signal, 'app.performance.frame');
    expect(record.severity, RuntimeLogSeverity.warn);
    expect(record.attributes.toWire(), <String, String>{
      'sampledFrames': '2',
      'jankyFrames': '1',
      'worstFrameMs': '60',
      'jankThresholdMs': '50',
    });
    final productRecord = recorder.records.single;
    expect(productRecord.eventType, 'app_frame_jank_outcome');
    expect(productRecord.extensions, <String, Object?>{
      'sampledFrames': 2,
      'jankyFrames': 1,
      'worstFrameMs': 60,
      'jankThresholdMs': 50,
      'result': 'degraded',
    });
  });

  test('anr watchdog reports only real event-loop stalls', () async {
    final buffer = InMemoryRuntimeLogBuffer();
    final diagnostics = AppRuntimeDiagnostics(
      logger(buffer),
      anrWatchdogPeriod: const Duration(seconds: 2),
      anrStallThreshold: const Duration(seconds: 5),
    );

    final base = DateTime.utc(2026, 7, 19, 10);
    // 正常心跳（gap == period）不得产生 ANR 事实。
    diagnostics.recordWatchdogHeartbeat(base);
    diagnostics.recordWatchdogHeartbeat(base.add(const Duration(seconds: 2)));
    await _settle();
    expect(await buffer.pending(), isEmpty);

    // 事件循环停顿：期望 2s 的 tick 在 9s 后才执行（stall = 7s ≥ 5s 阈值）。
    diagnostics.recordWatchdogHeartbeat(base.add(const Duration(seconds: 11)));
    await _settle();

    final record = (await buffer.pending()).single;
    expect(record.signal, 'app.performance.anr');
    expect(record.event, 'main_isolate_stall');
    expect(record.severity, RuntimeLogSeverity.error);
    expect(record.attributes.toWire()['stallMs'], '7000');
    expect(record.attributes.toWire()['anrThresholdMs'], '5000');
  });

  test('anr watchdog excludes background suspension from stall time', () async {
    final buffer = InMemoryRuntimeLogBuffer();
    var now = DateTime.utc(2026, 7, 19, 10);
    final diagnostics = AppRuntimeDiagnostics(
      logger(buffer),
      now: () => now,
      anrWatchdogPeriod: const Duration(seconds: 2),
      anrStallThreshold: const Duration(seconds: 5),
    );

    diagnostics.recordWatchdogHeartbeat(now);
    diagnostics.didChangeAppLifecycleState(AppLifecycleState.paused);
    now = now.add(const Duration(minutes: 30));
    diagnostics.recordWatchdogHeartbeat(now);
    diagnostics.didChangeAppLifecycleState(AppLifecycleState.resumed);
    diagnostics.recordWatchdogHeartbeat(now.add(const Duration(seconds: 2)));
    await _settle();

    expect(await buffer.pending(), isEmpty);
  });

  test(
    'native media warnings require player evidence, not raw logcat text',
    () async {
      final buffer = InMemoryRuntimeLogBuffer();
      final diagnostics = AppRuntimeDiagnostics(logger(buffer));

      await diagnostics.recordNativeMediaSignal(
        const VideoNativePlaybackSignal(
          kind: VideoNativePlaybackSignalKind.audioUnderrun,
          processedFrames: 12,
        ),
      );

      final record = (await buffer.pending()).single;
      expect(record.signal, 'app.performance.media');
      expect(record.event, 'native_audio_underrun');
      expect(record.result, 'degraded');
      expect(record.severity, RuntimeLogSeverity.warn);
    },
  );

  test('unhandled errors use stable code and a non-raw fingerprint', () async {
    final buffer = InMemoryRuntimeLogBuffer();
    final diagnostics = AppRuntimeDiagnostics(logger(buffer));

    await diagnostics.recordUnhandledException(
      fromPlatform: false,
      exception: StateError('secret token=do-not-log'),
      stack: StackTrace.fromString('/private/path.dart:12'),
    );

    final record = (await buffer.pending()).single;
    expect(record.signal, 'app.exception.flutter');
    expect(record.errorCode, 'APP.RUNTIME.uncaught_exception');
    expect(record.message, 'unhandled flutter_error exception');
    expect(record.fingerprint, isNot(contains('secret')));
    expect(record.attributes.toWire()['exceptionType'], 'StateError');
  });

  test(
    'previous native uncaught exception is acknowledged as a redacted platform fact',
    () async {
      final buffer = InMemoryRuntimeLogBuffer();
      final diagnostics = AppRuntimeDiagnostics(
        logger(buffer),
        nativeCrashMarkerBridge: _FixedNativeCrashMarkerBridge(
          const NativeCrashMarker(kind: 'IllegalStateException'),
        ),
      );

      await diagnostics.recordPreviousNativeCrash();

      final record = (await buffer.pending()).single;
      expect(record.signal, 'app.exception.platform');
      expect(record.errorCode, 'APP.RUNTIME.native_previous_crash');
      expect(
        record.message,
        'native uncaught exception observed on previous launch',
      );
      expect(record.attributes.toWire(), <String, String>{
        'source': 'native_previous_launch',
        'exceptionType': 'IllegalStateException',
      });
      expect(record.fingerprint, isNot(contains('IllegalStateException')));
    },
  );

  test(
    'previous native ANR is projected once to runtime and product tracks',
    () async {
      final buffer = InMemoryRuntimeLogBuffer();
      final recorder = _CapturingTelemetryRecorder();
      final pageContext = AppPageContextStore.instance..setPageName('home');
      final experience = AppPageExperienceTracker(pageContextStore: pageContext)
        ..attachReporter(recorder);
      final occurredAt = DateTime.utc(2026, 7, 20, 8);
      final marker = NativeAnrMarker(
        source: 'android_application_exit_info',
        occurredAt: occurredAt,
      );
      final bridge = _FixedNativeAnrMarkerBridge(marker);
      final diagnostics = AppRuntimeDiagnostics(
        logger(buffer),
        pageContextStore: pageContext,
        pageExperienceTracker: experience,
        nativeAnrMarkerBridge: bridge,
      );

      await diagnostics.recordPreviousNativeAnr();

      final runtimeRecord = (await buffer.pending()).single;
      expect(runtimeRecord.signal, 'app.performance.anr');
      expect(runtimeRecord.event, 'previous_launch_anr');
      expect(
        runtimeRecord.attributes.toWire()['source'],
        'android_application_exit_info',
      );
      final productRecord = recorder.records.single;
      expect(productRecord.eventType, 'app_anr_outcome');
      expect(productRecord.extensions, <String, Object?>{
        'detectionSource': 'android_application_exit_info',
        'result': 'detected',
      });
      expect(recorder.occurredAt, occurredAt);
      expect(bridge.acknowledgedMarker, same(marker));
    },
  );

  test(
    'previous native ANR remains pending until product outbox accepts it',
    () async {
      final buffer = InMemoryRuntimeLogBuffer();
      final recorder = _CapturingTelemetryRecorder(
        result: AppTelemetryRecordResult.rejected,
      );
      final pageContext = AppPageContextStore.instance..setPageName('home');
      final experience = AppPageExperienceTracker(pageContextStore: pageContext)
        ..attachReporter(recorder);
      final bridge = _FixedNativeAnrMarkerBridge(
        NativeAnrMarker(
          source: 'ios_metric_kit',
          occurredAt: DateTime.utc(2026, 7, 20, 8),
        ),
      );
      final diagnostics = AppRuntimeDiagnostics(
        logger(buffer),
        pageContextStore: pageContext,
        pageExperienceTracker: experience,
        nativeAnrMarkerBridge: bridge,
      );

      await diagnostics.recordPreviousNativeAnr();

      expect(bridge.acknowledgedMarker, isNull);
      expect((await buffer.pending()).single.event, 'previous_launch_anr');
    },
  );
}

Future<void> _settle() => Future<void>.delayed(Duration.zero);

final class _FixedNativeCrashMarkerBridge implements NativeCrashMarkerBridge {
  const _FixedNativeCrashMarkerBridge(this.marker);

  final NativeCrashMarker? marker;

  @override
  Future<NativeCrashMarker?> consumePreviousCrash() async => marker;
}

final class _FixedNativeAnrMarkerBridge implements NativeAnrMarkerBridge {
  _FixedNativeAnrMarkerBridge(this.marker);

  final NativeAnrMarker? marker;
  NativeAnrMarker? acknowledgedMarker;

  @override
  Future<NativeAnrMarker?> readPreviousAnr() async => marker;

  @override
  Future<bool> acknowledgePreviousAnr(NativeAnrMarker marker) async {
    acknowledgedMarker = marker;
    return true;
  }
}

final class _CapturingTelemetryRecorder implements AppTelemetryRecorder {
  _CapturingTelemetryRecorder({
    this.result = AppTelemetryRecordResult.accepted,
  });

  final AppTelemetryRecordResult result;
  final List<AppTelemetryPayload> records = <AppTelemetryPayload>[];
  DateTime? occurredAt;

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
    records.add(payload);
    this.occurredAt = occurredAt;
    return result;
  }
}
