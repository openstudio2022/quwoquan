// ignore_for_file: prefer_initializing_formals

import 'dart:async';

import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/media/app_video_runtime_budget.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';

/// 首页性能 operationId；wire eventType 由 product-ops codegen 拥有。
class FeedPerformanceMetricNames {
  static const String firstScreenTtiMs = 'home_feed_first_screen_tti_ms';
  static const String videoAutoplayStartupMs =
      'home_feed_video_autoplay_startup_ms';
  static const String videoAutoplayFailed = 'home_feed_video_autoplay_failed';
  static const String videoPlaybackStartupMs =
      'home_feed_video_playback_startup_ms';
  static const String videoPlaybackFailed = 'home_feed_video_playback_failed';

  const FeedPerformanceMetricNames._();
}

/// 首页首屏、媒体和资源预算的 typed 产品观测。
///
/// 调用方只能提交 codegen 生成的 payload，不再经过 dynamic analytics
/// 和 local-only denylist。全局帧分母由 `AppRuntimeDiagnostics` 唯一生产，
/// 本类不建立第二条 jank 采样轨。
class FeedPerformanceObservability {
  FeedPerformanceObservability({required AppTelemetryRecorder telemetry})
    : _telemetry = telemetry;

  final AppTelemetryRecorder _telemetry;
  final Map<String, Stopwatch> _firstScreenTimers = <String, Stopwatch>{};
  final Set<String> _firstScreenReported = <String>{};
  final Set<String> _loadFailureReported = <String>{};

  void markFeedRequested(String channelId) {
    final id = channelId.trim();
    if (id.isEmpty || _firstScreenReported.contains(id)) return;
    _firstScreenTimers.putIfAbsent(id, () => Stopwatch()..start());
  }

  void markFirstContentReady(String channelId, {required int itemCount}) {
    final id = channelId.trim();
    if (id.isEmpty || itemCount < 0 || _firstScreenReported.contains(id)) {
      return;
    }
    final timer = _firstScreenTimers.remove(id);
    if (timer == null) return;
    timer.stop();
    _firstScreenReported.add(id);
    _loadFailureReported.removeWhere((key) => key.startsWith('$id::'));
    _record(
      AppTelemetryPayload.performanceSample(
        operationId: FeedPerformanceMetricNames.firstScreenTtiMs,
        durationMs: timer.elapsedMilliseconds,
        result: 'ok',
      ),
    );
  }

  void resetChannel(String channelId) {
    final id = channelId.trim();
    if (id.isEmpty) return;
    _firstScreenTimers.remove(id);
    _firstScreenReported.remove(id);
    _loadFailureReported.removeWhere((key) => key.startsWith('$id::'));
  }

  void recordFeedLoadFailed({
    required String channelId,
    required String errorCode,
    required String operation,
    required String surface,
    required bool hasCache,
    String? recovery,
    String? requestId,
    String? traceId,
  }) {
    final id = channelId.trim();
    final normalizedCode = errorCode.trim().isEmpty
        ? 'APP.SYSTEM.unknown_error'
        : errorCode.trim();
    if (id.isEmpty || !_loadFailureReported.add('$id::$normalizedCode')) {
      return;
    }
    _record(
      AppTelemetryPayload.operationResult(
        operationId: operation,
        result: 'failed',
        surfaceId: surface,
        hasCache: hasCache,
        failReasonCode: normalizedCode,
        recoveryAction: recovery,
        requestId: requestId,
        traceId: traceId,
      ),
    );
  }

  void recordVideoPlaybackStarted({
    required String contentId,
    required int startupMs,
    required int candidateIndex,
    required bool autoPlay,
  }) {
    if (contentId.trim().isEmpty || candidateIndex < 0) return;
    _record(
      AppTelemetryPayload.performanceSample(
        operationId: autoPlay
            ? FeedPerformanceMetricNames.videoAutoplayStartupMs
            : FeedPerformanceMetricNames.videoPlaybackStartupMs,
        durationMs: startupMs < 0 ? 0 : startupMs,
        result: 'ok',
      ),
    );
  }

  void recordVideoPlaybackFailed({
    required String contentId,
    required int candidatesTried,
    required String failureKind,
    required String userScene,
    required bool retryable,
    required bool autoPlay,
  }) {
    if (contentId.trim().isEmpty || candidatesTried < 0) return;
    _record(
      AppTelemetryPayload.operationResult(
        operationId: autoPlay
            ? FeedPerformanceMetricNames.videoAutoplayFailed
            : FeedPerformanceMetricNames.videoPlaybackFailed,
        result: 'failed',
        surfaceId: _nonEmpty(userScene),
        failReasonCode: _nonEmpty(failureKind) ?? 'unknown',
        recoveryAction: retryable ? 'retry' : 'absorb',
      ),
    );
  }

  void recordImageCacheBudget({
    required String profile,
    required int currentSizeBytes,
    required int maxSizeBytes,
  }) {
    final current = _nonNegative(currentSizeBytes);
    final limit = _nonNegative(maxSizeBytes);
    _record(
      AppTelemetryPayload.homeFeedResourceSnapshot(
        resourceKind: AppTelemetryValueResourceKind.imageCacheBytes,
        currentValue: current,
        result: current <= limit ? 'within_budget' : 'over_budget',
        resourceProfile: _resourceProfile(profile),
        limitValue: limit,
        surfaceId: 'home_feed',
      ),
    );
  }

  void recordActiveVideoControllerCount({
    required String surfaceId,
    required int activeCount,
  }) {
    final surface = surfaceId.trim();
    if (surface.isEmpty) return;
    final current = _nonNegative(activeCount);
    const limit = AppVideoRuntimeBudget.maxConcurrentControllers;
    _record(
      AppTelemetryPayload.homeFeedResourceSnapshot(
        resourceKind: AppTelemetryValueResourceKind.activeVideoControllers,
        currentValue: current,
        result: current <= limit ? 'within_budget' : 'over_budget',
        limitValue: limit,
        surfaceId: surface,
      ),
    );
  }

  void recordMediaDownloadQueue({
    required String profile,
    required int activeDownloads,
    required int queuedDownloads,
    required int inflightDownloads,
    required int cacheSizeBytes,
  }) {
    _record(
      AppTelemetryPayload.homeFeedResourceSnapshot(
        resourceKind: AppTelemetryValueResourceKind.mediaDownloads,
        currentValue: _nonNegative(activeDownloads),
        result: 'observed',
        resourceProfile: _resourceProfile(profile),
        queuedValue: _nonNegative(queuedDownloads),
        inflightValue: _nonNegative(inflightDownloads),
        cacheSizeBytes: _nonNegative(cacheSizeBytes),
        surfaceId: 'home_feed',
      ),
    );
  }

  void _record(AppTelemetryPayload payload) {
    unawaited(_telemetry.record(payload));
  }

  int _nonNegative(int value) => value < 0 ? 0 : value;

  String? _nonEmpty(String value) {
    final normalized = value.trim();
    return normalized.isEmpty ? null : normalized;
  }

  String? _resourceProfile(String value) {
    final normalized = value.trim();
    return AppTelemetryValueResourceProfile.values.contains(normalized)
        ? normalized
        : null;
  }
}
