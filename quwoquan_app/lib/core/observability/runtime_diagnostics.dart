import 'dart:async';
import 'dart:convert';
import 'dart:ui';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/observability/generated/runtime_log_catalog.g.dart';
import 'package:quwoquan_app/core/observability/runtime_log_record.dart';
import 'package:quwoquan_app/core/observability/runtime_logger.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/video_native_playback_signals.dart';
import 'package:quwoquan_app/core/telemetry/app_page_experience_tracker.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';

/// 将 Flutter、原生媒体和帧时序转成受控的运行诊断事实。
///
/// 不读取、不过滤也不上传完整 Logcat；系统媒体行只通过播放器实际状态、帧耗时和
/// 稳定 fingerprint 进入统一日志，避免把模拟器 CCodec/EGL 噪声误判成应用故障。
final class AppRuntimeDiagnostics with WidgetsBindingObserver {
  AppRuntimeDiagnostics(
    this._logger, {
    AppPageContextStore? pageContextStore,
    DateTime Function()? now,
    NativeCrashMarkerBridge? nativeCrashMarkerBridge,
    NativeAnrMarkerBridge? nativeAnrMarkerBridge,
    AppPageExperienceTracker? pageExperienceTracker,
    this.jankThreshold = const Duration(milliseconds: 50),
    this.severeFrameThreshold = const Duration(milliseconds: 200),
    this.frameBatchSize = 120,
    this.anrWatchdogPeriod = const Duration(seconds: 2),
    this.anrStallThreshold = const Duration(seconds: 5),
  }) : _pageContextStore = pageContextStore ?? AppPageContextStore.instance,
       _now = now ?? DateTime.now,
       _nativeCrashMarkerBridge =
           nativeCrashMarkerBridge ??
           const MethodChannelNativeCrashMarkerBridge(),
       _nativeAnrMarkerBridge =
           nativeAnrMarkerBridge ?? const MethodChannelNativeAnrMarkerBridge(),
       _pageExperienceTracker =
           pageExperienceTracker ?? AppPageExperienceTracker.instance;

  final RuntimeLogger _logger;
  final AppPageContextStore _pageContextStore;
  final DateTime Function() _now;
  final NativeCrashMarkerBridge _nativeCrashMarkerBridge;
  final NativeAnrMarkerBridge _nativeAnrMarkerBridge;
  final AppPageExperienceTracker _pageExperienceTracker;
  final Duration jankThreshold;
  final Duration severeFrameThreshold;
  final int frameBatchSize;

  /// ANR watchdog 周期与判定阈值：事件循环在 period+threshold 内未执行到
  /// 定时器回调即判定一次主 isolate 停顿（恢复后上报真实 stall 时长）。
  final Duration anrWatchdogPeriod;
  final Duration anrStallThreshold;

  FlutterExceptionHandler? _previousFlutterErrorHandler;
  bool Function(Object, StackTrace)? _previousPlatformErrorHandler;
  late final FlutterExceptionHandler _flutterErrorHandler = _onFlutterError;
  late final bool Function(Object, StackTrace) _platformErrorHandler =
      _onPlatformError;
  bool _installed = false;
  int _sampledFrames = 0;
  int _jankyFrames = 0;
  int _worstFrameMs = 0;
  Timer? _anrWatchdog;
  DateTime? _lastWatchdogTick;
  bool _watchdogEligible = true;

  void install() {
    if (_installed) return;
    _installed = true;
    _previousFlutterErrorHandler = FlutterError.onError;
    FlutterError.onError = _flutterErrorHandler;
    _previousPlatformErrorHandler = PlatformDispatcher.instance.onError;
    PlatformDispatcher.instance.onError = _platformErrorHandler;
    SchedulerBinding.instance.addTimingsCallback(_onFrameTimings);
    WidgetsBinding.instance.addObserver(this);
    _watchdogEligible =
        WidgetsBinding.instance.lifecycleState == null ||
        WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed;
    _lastWatchdogTick = _watchdogEligible ? _now() : null;
    _anrWatchdog = Timer.periodic(anrWatchdogPeriod, (_) => _onWatchdogTick());
    unawaited(recordPreviousNativeCrash());
    unawaited(recordPreviousNativeAnr());
  }

  void dispose() {
    if (!_installed) return;
    _installed = false;
    _anrWatchdog?.cancel();
    _anrWatchdog = null;
    WidgetsBinding.instance.removeObserver(this);
    SchedulerBinding.instance.removeTimingsCallback(_onFrameTimings);
    if (identical(FlutterError.onError, _flutterErrorHandler)) {
      FlutterError.onError = _previousFlutterErrorHandler;
    }
    if (identical(PlatformDispatcher.instance.onError, _platformErrorHandler)) {
      PlatformDispatcher.instance.onError = _previousPlatformErrorHandler;
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _watchdogEligible = true;
      // 后台挂起期间 Timer 不会被调度；恢复时重置基线，禁止把挂起时长误报为 ANR。
      _lastWatchdogTick = _now();
      return;
    }
    _watchdogEligible = false;
    _lastWatchdogTick = null;
  }

  void _onWatchdogTick() {
    recordWatchdogHeartbeat(_now());
  }

  /// ANR 检测的同一心跳入口（Flutter 定时器与 local_contract 共用）：
  /// 事件循环被阻塞时定时器无法按期执行，恢复后测得的真实 gap 超过
  /// period+threshold 即上报一次主 isolate 停顿事实。
  void recordWatchdogHeartbeat(DateTime tickAt) {
    if (!_watchdogEligible) {
      return;
    }
    final previous = _lastWatchdogTick;
    _lastWatchdogTick = tickAt;
    if (previous == null) return;
    final gap = tickAt.difference(previous);
    final stall = gap - anrWatchdogPeriod;
    if (stall < anrStallThreshold) return;
    unawaited(
      _logger.event(
        signal: 'app.performance.anr',
        event: 'main_isolate_stall',
        result: 'stalled',
        message: 'main isolate event loop stalled beyond ANR threshold',
        severity: RuntimeLogSeverity.error,
        correlation: _correlation(operationId: 'app.runtime.anr_watchdog'),
        attributes: <String, String>{
          'source': 'anr_watchdog',
          'stallMs': '${stall.inMilliseconds}',
          'anrThresholdMs': '${anrStallThreshold.inMilliseconds}',
        },
        occurredAt: tickAt,
      ),
    );
    unawaited(
      _pageExperienceTracker.recordAnrOutcome(
        detectionSource: 'dart_event_loop_watchdog',
        result: 'detected',
        durationMs: stall.inMilliseconds,
        occurredAt: tickAt,
      ),
    );
  }

  Future<void> recordNativeMediaSignal(VideoNativePlaybackSignal signal) {
    final event = switch (signal.kind) {
      VideoNativePlaybackSignalKind.playbackDiagnostics =>
        'native_playback_diagnostics',
      VideoNativePlaybackSignalKind.renderedFirstFrame =>
        'native_rendered_first_frame',
      VideoNativePlaybackSignalKind.seekSettled => 'native_seek_settled',
      VideoNativePlaybackSignalKind.droppedVideoFrames =>
        'native_dropped_video_frames',
      VideoNativePlaybackSignalKind.audioUnderrun => 'native_audio_underrun',
      VideoNativePlaybackSignalKind.videoFrameProcessing =>
        'native_video_frame_processing',
    };
    final isFailure =
        signal.kind == VideoNativePlaybackSignalKind.audioUnderrun ||
        (signal.droppedFrames ?? 0) > 0;
    return _logger.event(
      signal: 'app.performance.media',
      event: event,
      result: isFailure ? 'degraded' : 'ok',
      message: 'native media diagnostic',
      severity: isFailure ? RuntimeLogSeverity.warn : RuntimeLogSeverity.info,
      correlation: _correlation(operationId: 'app.media.playback_diagnostics'),
      attributes: <String, String>{
        if (signal.ttffMs != null) 'ttffMs': '${signal.ttffMs}',
        if (signal.targetPositionMs != null)
          'targetPositionMs': '${signal.targetPositionMs}',
        if (signal.settledPositionMs != null)
          'settledPositionMs': '${signal.settledPositionMs}',
        if (signal.settleMs != null) 'settleMs': '${signal.settleMs}',
        if (signal.droppedFrames != null)
          'droppedFrames': '${signal.droppedFrames}',
        if (signal.processedFrames != null)
          'processedFrames': '${signal.processedFrames}',
        if (signal.rendererMode != null) 'rendererMode': signal.rendererMode!,
        if (signal.decoderQueueMode != null)
          'decoderQueueMode': signal.decoderQueueMode!,
        if (signal.decoderFallbackEnabled != null)
          'decoderFallbackEnabled': '${signal.decoderFallbackEnabled}',
      },
      occurredAt: _now(),
    );
  }

  /// 平台边界可显式提交已脱敏的未处理异常；全局 handler 也复用此入口。
  Future<void> recordUnhandledException({
    required bool fromPlatform,
    required Object exception,
    StackTrace? stack,
  }) => _recordException(
    signal: fromPlatform ? 'app.exception.platform' : 'app.exception.flutter',
    source: fromPlatform ? 'platform_dispatcher' : 'flutter_error',
    exception: exception,
    stack: stack,
  );

  /// On the first safe Dart frame after startup, converts a persisted native
  /// uncaught-exception marker from the previous process into a redacted
  /// runtime fact.
  Future<void> recordPreviousNativeCrash() async {
    final marker = await _nativeCrashMarkerBridge.consumePreviousCrash();
    if (marker == null) {
      return;
    }
    final fingerprint = sha256
        .convert(utf8.encode('native_previous_launch\n${marker.kind}'))
        .toString();
    await _logger.exception(
      signal: 'app.exception.platform',
      errorCode: RuntimeLogCatalog.failureCodes['app_native_previous_crash']!,
      fingerprint: fingerprint,
      message: 'native uncaught exception observed on previous launch',
      correlation: _correlation(
        operationId: 'app.runtime.capture_native_crash',
      ),
      attributes: <String, String>{
        'source': 'native_previous_launch',
        'exceptionType': marker.kind,
      },
      occurredAt: _now(),
    );
  }

  /// Android ApplicationExitInfo 与 iOS MetricKit 都是上一进程的延迟事实；
  /// 先读后可靠入队，只有 accepted 后才确认原生标记，避免启动窗口故障造成事实丢失。
  Future<void> recordPreviousNativeAnr() async {
    final marker = await _nativeAnrMarkerBridge.readPreviousAnr();
    if (marker == null) {
      return;
    }
    await _logger.event(
      signal: 'app.performance.anr',
      event: 'previous_launch_anr',
      result: 'detected',
      message: 'platform reported an ANR on the previous launch',
      severity: RuntimeLogSeverity.error,
      correlation: _correlation(operationId: 'app.runtime.capture_native_anr'),
      attributes: <String, String>{
        'source': marker.source,
        if (marker.durationMs != null)
          'durationMs': marker.durationMs!.toString(),
      },
      occurredAt: marker.occurredAt,
    );
    final outcome = await _pageExperienceTracker.recordAnrOutcome(
      detectionSource: marker.source,
      result: 'detected',
      durationMs: marker.durationMs,
      occurredAt: marker.occurredAt,
    );
    if (outcome == AppTelemetryRecordResult.accepted) {
      await _nativeAnrMarkerBridge.acknowledgePreviousAnr(marker);
    }
  }

  void _onFlutterError(FlutterErrorDetails details) {
    final previous = _previousFlutterErrorHandler;
    try {
      previous?.call(details);
    } catch (error, stackTrace) {
      // 既有展示/调试 handler 失效也必须可观测，且不能阻止当前异常落库。
      unawaited(
        _recordException(
          signal: 'app.exception.flutter',
          source: 'previous_flutter_error_handler',
          exception: error,
          stack: stackTrace,
        ),
      );
    }
    unawaited(
      recordUnhandledException(
        fromPlatform: false,
        exception: details.exception,
        stack: details.stack,
      ),
    );
  }

  bool _onPlatformError(Object error, StackTrace stack) {
    unawaited(
      recordUnhandledException(
        fromPlatform: true,
        exception: error,
        stack: stack,
      ),
    );
    final previous = _previousPlatformErrorHandler;
    return previous?.call(error, stack) ?? false;
  }

  void _onFrameTimings(List<FrameTiming> timings) {
    for (final timing in timings) {
      recordFrameDuration(timing.totalSpan);
    }
  }

  /// 用于 Flutter timing callback 与 local_contract 的同一帧耗时入口。
  void recordFrameDuration(Duration total) {
    final milliseconds = total.inMilliseconds;
    _sampledFrames += 1;
    _worstFrameMs = milliseconds > _worstFrameMs ? milliseconds : _worstFrameMs;
    if (total >= jankThreshold) {
      _jankyFrames += 1;
    }
    if (_sampledFrames < frameBatchSize) return;
    final sampled = _sampledFrames;
    final janky = _jankyFrames;
    final worst = _worstFrameMs;
    _sampledFrames = 0;
    _jankyFrames = 0;
    _worstFrameMs = 0;
    if (janky == 0) return;
    final severity = worst >= severeFrameThreshold.inMilliseconds
        ? RuntimeLogSeverity.error
        : RuntimeLogSeverity.warn;
    final observedAt = _now();
    unawaited(
      _logger.event(
        signal: 'app.performance.frame',
        event: 'frame_jank',
        result: severity == RuntimeLogSeverity.error ? 'severe' : 'degraded',
        message: 'frame timing threshold exceeded',
        severity: severity,
        correlation: _correlation(operationId: 'app.runtime.frame_timing'),
        attributes: <String, String>{
          'sampledFrames': '$sampled',
          'jankyFrames': '$janky',
          'worstFrameMs': '$worst',
          'jankThresholdMs': '${jankThreshold.inMilliseconds}',
        },
        occurredAt: observedAt,
      ),
    );
    unawaited(
      _pageExperienceTracker.recordFrameJankOutcome(
        sampledFrames: sampled,
        jankyFrames: janky,
        worstFrameMs: worst,
        jankThresholdMs: jankThreshold.inMilliseconds,
        result: severity == RuntimeLogSeverity.error ? 'severe' : 'degraded',
        occurredAt: observedAt,
      ),
    );
  }

  Future<void> _recordException({
    required String signal,
    required String source,
    required Object exception,
    required StackTrace? stack,
  }) {
    final type = exception.runtimeType.toString();
    final fingerprint = sha256
        .convert(
          utf8.encode(
            '$source\n$type\n${_stackIdentity(stack?.toString() ?? '')}',
          ),
        )
        .toString();
    return _logger.exception(
      signal: signal,
      errorCode: signal == 'app.exception.flutter'
          ? RuntimeLogCatalog.failureCodes['app_uncaught_flutter']!
          : RuntimeLogCatalog.failureCodes['app_uncaught_platform']!,
      fingerprint: fingerprint,
      message: 'unhandled $source exception',
      correlation: _correlation(operationId: 'app.runtime.capture_exception'),
      attributes: <String, String>{'source': source, 'exceptionType': type},
      occurredAt: _now(),
    );
  }

  RuntimeLogCorrelation _correlation({required String operationId}) =>
      RuntimeLogCorrelation(
        operationId: operationId,
        pageName: _pageContextStore.pageName,
      );

  String _stackIdentity(String value) {
    return value
        .split('\n')
        .take(8)
        .map((line) => line.replaceAll(RegExp(r'[/\\][^\s:()]+'), '<path>'))
        .join('\n');
  }
}
