// ignore_for_file: prefer_initializing_formals

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/analytics/analytics.dart';

/// 首页推荐性能指标名（首屏可交互 TTI / 视频自动播放启动 / 视频自动播放失败）。
class FeedPerformanceMetricNames {
  static const String firstScreenTtiMs = 'home_feed_first_screen_tti_ms';
  static const String videoAutoplayStartupMs =
      'home_feed_video_autoplay_startup_ms';
  static const String videoAutoplayFailed = 'home_feed_video_autoplay_failed';
  static const String feedLoadFailed = 'home_feed_load_failed';
  static const String frameJankRatio = 'home_feed_frame_jank_ratio';
  static const String imageCacheBytes = 'home_feed_image_cache_bytes';
  static const String activeVideoControllerCount =
      'home_feed_active_video_controller_count';
  static const String mediaDownloadQueue = 'home_feed_media_download_queue';
  static const String postCacheHitSource = 'home_feed_post_cache_hit_source';

  const FeedPerformanceMetricNames._();
}

/// 首页推荐性能可观测：首屏 TTI + 视频自动播放启动/失败归因。
///
/// 仅消费统一埋点出口 [AnalyticsService]，不触碰 `discovery_feed_provider`
/// 的实时补丁消费逻辑（任务约束：性能度量仅在 widget 层旁路采集）。
/// 每个 channel 的首屏 TTI 只上报一次；`force` 刷新通过 [resetChannel]
/// 复位后可重新计时。
class FeedPerformanceObservability {
  FeedPerformanceObservability({required AnalyticsService analytics})
    : _analytics = analytics;

  final AnalyticsService _analytics;

  /// 每个 channel 的首屏请求起点（首次触发加载时铸造）。
  final Map<String, Stopwatch> _firstScreenTimers = <String, Stopwatch>{};

  /// 已上报首屏 TTI 的 channel，避免重复上报。
  final Set<String> _firstScreenReported = <String>{};

  /// 已上报加载失败的 `channel::reason`，避免同因重复上报；首屏成功后复位。
  final Set<String> _loadFailureReported = <String>{};

  /// 标记某 channel 的首屏加载开始计时（幂等：已计时或已上报则忽略）。
  void markFeedRequested(String channelId) {
    final id = channelId.trim();
    if (id.isEmpty || _firstScreenReported.contains(id)) {
      return;
    }
    _firstScreenTimers.putIfAbsent(id, () => Stopwatch()..start());
  }

  /// 首屏内容首帧渲染：上报首屏可交互耗时（每 channel 仅一次）。
  void markFirstContentReady(String channelId, {required int itemCount}) {
    final id = channelId.trim();
    if (id.isEmpty || _firstScreenReported.contains(id)) {
      return;
    }
    final timer = _firstScreenTimers.remove(id);
    if (timer == null) {
      return;
    }
    timer.stop();
    _firstScreenReported.add(id);
    // 首屏成功后复位该 channel 的失败去重，使后续真实失败能再次上报。
    _loadFailureReported.removeWhere((key) => key.startsWith('$id::'));
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'feed_metric',
          eventName: FeedPerformanceMetricNames.firstScreenTtiMs,
          properties: <String, dynamic>{
            'channelId': id,
            'durationMs': timer.elapsedMilliseconds,
            'itemCount': itemCount,
          },
        ),
      ),
    );
  }

  /// `force` 刷新：复位该 channel 的首屏计时与上报标记，便于重新度量。
  void resetChannel(String channelId) {
    final id = channelId.trim();
    if (id.isEmpty) {
      return;
    }
    _firstScreenTimers.remove(id);
    _firstScreenReported.remove(id);
    _loadFailureReported.removeWhere((key) => key.startsWith('$id::'));
  }

  /// 首页加载失败（阻断态空内容）：按 `channel::reason` 去重上报异常归因。
  void recordFeedLoadFailed({
    required String channelId,
    required String reason,
  }) {
    final id = channelId.trim();
    final normalizedReason = reason.trim().isEmpty ? 'unknown' : reason.trim();
    if (id.isEmpty || !_loadFailureReported.add('$id::$normalizedReason')) {
      return;
    }
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'feed_metric',
          eventName: FeedPerformanceMetricNames.feedLoadFailed,
          properties: <String, dynamic>{
            'channelId': id,
            'reason': normalizedReason,
            'result': 'failed',
          },
        ),
      ),
    );
  }

  /// 视频自动播放启动成功：上报启动耗时与命中候选源序号。
  void recordVideoPlaybackStarted({
    required String contentId,
    required int startupMs,
    required int candidateIndex,
  }) {
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'feed_metric',
          eventName: FeedPerformanceMetricNames.videoAutoplayStartupMs,
          properties: <String, dynamic>{
            'contentId': contentId,
            'durationMs': startupMs,
            'candidateIndex': candidateIndex,
            'result': 'ok',
          },
        ),
      ),
    );
  }

  /// 视频自动播放失败（候选源全部失败）：上报失败归因供异常面板度量。
  void recordVideoPlaybackFailed({
    required String contentId,
    required int candidatesTried,
  }) {
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'feed_metric',
          eventName: FeedPerformanceMetricNames.videoAutoplayFailed,
          properties: <String, dynamic>{
            'contentId': contentId,
            'candidatesTried': candidatesTried,
            'result': 'failed',
          },
        ),
      ),
    );
  }

  void recordFrameJankRatio({
    required String surfaceId,
    required int sampledFrames,
    required int jankyFrames,
    required double ratio,
  }) {
    final normalizedSurface = surfaceId.trim();
    if (normalizedSurface.isEmpty || sampledFrames <= 0) {
      return;
    }
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'feed_metric',
          eventName: FeedPerformanceMetricNames.frameJankRatio,
          properties: <String, dynamic>{
            'surfaceId': normalizedSurface,
            'sampledFrames': sampledFrames,
            'jankyFrames': jankyFrames.clamp(0, sampledFrames),
            'ratio': ratio.clamp(0, 1),
          },
        ),
      ),
    );
  }

  void recordImageCacheBudget({
    required String profile,
    required int currentSizeBytes,
    required int maxSizeBytes,
  }) {
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'feed_metric',
          eventName: FeedPerformanceMetricNames.imageCacheBytes,
          properties: <String, dynamic>{
            'profile': profile,
            'currentSizeBytes': currentSizeBytes < 0 ? 0 : currentSizeBytes,
            'maxSizeBytes': maxSizeBytes < 0 ? 0 : maxSizeBytes,
          },
        ),
      ),
    );
  }

  void recordActiveVideoControllerCount({
    required String surfaceId,
    required int activeCount,
  }) {
    final normalizedSurface = surfaceId.trim();
    if (normalizedSurface.isEmpty) {
      return;
    }
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'feed_metric',
          eventName: FeedPerformanceMetricNames.activeVideoControllerCount,
          properties: <String, dynamic>{
            'surfaceId': normalizedSurface,
            'activeCount': activeCount < 0 ? 0 : activeCount,
          },
        ),
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
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'feed_metric',
          eventName: FeedPerformanceMetricNames.mediaDownloadQueue,
          properties: <String, dynamic>{
            'profile': profile,
            'activeDownloads': activeDownloads < 0 ? 0 : activeDownloads,
            'queuedDownloads': queuedDownloads < 0 ? 0 : queuedDownloads,
            'inflightDownloads': inflightDownloads < 0 ? 0 : inflightDownloads,
            'cacheSizeBytes': cacheSizeBytes < 0 ? 0 : cacheSizeBytes,
          },
        ),
      ),
    );
  }

  void recordPostCacheHitSource({
    required String source,
    required String cacheClass,
  }) {
    final normalizedSource = source.trim();
    if (normalizedSource.isEmpty) {
      return;
    }
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'feed_metric',
          eventName: FeedPerformanceMetricNames.postCacheHitSource,
          properties: <String, dynamic>{
            'source': normalizedSource,
            'cacheClass': cacheClass.trim().isEmpty ? 'unknown' : cacheClass,
          },
        ),
      ),
    );
  }
}

final feedPerformanceObservabilityProvider =
    Provider<FeedPerformanceObservability>((ref) {
      return FeedPerformanceObservability(
        analytics: ref.read(analyticsProvider),
      );
    });
