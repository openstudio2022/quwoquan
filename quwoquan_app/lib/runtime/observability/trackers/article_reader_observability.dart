import 'dart:async';
import 'dart:collection';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';

class ArticleReaderMetricNames {
  /// 阅读器打开耗时（区分 hydration 问题）。
  static const String readerOpenMs = 'article_reader_open_ms';

  /// 文档水合耗时（区分 hydration 问题）。
  static const String hydrationMs = 'article_reader_hydration_ms';

  /// 翻页完成耗时（区分 page_curl 问题，含 direction: forward/backward）。
  static const String pageFlipCommitMs = 'article_page_flip_commit_ms';

  /// 翻页中止率（区分 page_curl abort，含 direction: forward/backward）。
  static const String pageCurlAbortRate = 'article_page_curl_abort_rate';

  /// 降级率（区分 fallback 问题，reason 含 long_document / forced_degraded_pager /
  /// page_curl_disabled / accessibility_disable_animations）。
  static const String readerFallbackRate = 'article_reader_fallback_rate';

  const ArticleReaderMetricNames._();
}

class ArticleReaderObservability {
  ArticleReaderObservability(
    this._analytics,
    this._telemetryRecorder, {
    int fallbackDedupCapacity = 512,
    Duration fallbackDedupTtl = const Duration(minutes: 30),
    DateTime Function()? now,
  }) : assert(fallbackDedupCapacity > 0),
       assert(fallbackDedupTtl > Duration.zero),
       _fallbackDedupCapacity = fallbackDedupCapacity,
       _fallbackDedupTtl = fallbackDedupTtl,
       _now = now ?? DateTime.now;

  final AnalyticsService _analytics;
  final AppTelemetryRecorder _telemetryRecorder;
  final int _fallbackDedupCapacity;
  final Duration _fallbackDedupTtl;
  final DateTime Function() _now;
  final LinkedHashMap<String, DateTime> _fallbackKeys =
      LinkedHashMap<String, DateTime>();

  int get debugFallbackDedupEntryCount => _fallbackKeys.length;

  void trackReaderOpen({
    required String postId,
    required int durationMs,
    required String source,
    required String template,
    required String fontPreset,
    required int pageCount,
    required bool bookReaderEnabled,
  }) {
    _track(
      eventName: ArticleReaderMetricNames.readerOpenMs,
      properties: <String, dynamic>{
        'postId': postId,
        'durationMs': durationMs,
        'source': source,
        'template': template,
        'fontPreset': fontPreset,
        'pageCount': pageCount,
        'bookReaderEnabled': bookReaderEnabled,
      },
    );
    _record(
      AppTelemetryPayload.articleReaderEnter(
        surfaceId: 'workBrowser',
        objectType: 'contentPost',
        objectId: postId,
        durationMs: durationMs,
        result: 'success',
      ),
    );
  }

  /// Records an active-reading interval. The catalog samples this high-volume
  /// signal independently; entering, exiting, errors and recovery stay at 100%.
  void trackReaderDwell({required String postId, required int durationMs}) {
    _record(
      AppTelemetryPayload.articleReaderDwell(
        surfaceId: 'workBrowser',
        objectType: 'contentPost',
        objectId: postId,
        durationMs: durationMs,
        result: 'success',
      ),
    );
  }

  void trackReaderExit({required String postId, required int durationMs}) {
    _record(
      AppTelemetryPayload.articleReaderExit(
        surfaceId: 'workBrowser',
        objectType: 'contentPost',
        objectId: postId,
        durationMs: durationMs,
        result: 'success',
      ),
    );
  }

  void trackReaderError({
    required String postId,
    required String errorCode,
    required String recoveryAction,
    required int durationMs,
  }) {
    _record(
      AppTelemetryPayload.articleReaderError(
        surfaceId: 'workBrowser',
        objectType: 'contentPost',
        objectId: postId,
        errorCode: errorCode,
        recoveryAction: recoveryAction,
        result: 'failure',
        durationMs: durationMs,
      ),
    );
  }

  void trackReaderRecovery({
    required String postId,
    required String recoveryAction,
    required String result,
    required int durationMs,
    String? errorCode,
  }) {
    _record(
      AppTelemetryPayload.articleReaderRecovery(
        surfaceId: 'workBrowser',
        objectType: 'contentPost',
        objectId: postId,
        recoveryAction: recoveryAction,
        result: result,
        durationMs: durationMs,
        errorCode: errorCode,
      ),
    );
  }

  void trackHydration({
    required String postId,
    required int durationMs,
    required String result,
    required String trigger,
    required bool hadStructuredPayload,
  }) {
    _track(
      eventName: ArticleReaderMetricNames.hydrationMs,
      properties: <String, dynamic>{
        'postId': postId,
        'durationMs': durationMs,
        'result': result,
        'trigger': trigger,
        'hadStructuredPayload': hadStructuredPayload,
      },
    );
  }

  void trackPageFlipCommit({
    required String postId,
    required int durationMs,
    required String mechanism,
    required String direction,
    required int fromPage,
    required int toPage,
  }) {
    _track(
      eventName: ArticleReaderMetricNames.pageFlipCommitMs,
      properties: <String, dynamic>{
        'postId': postId,
        'durationMs': durationMs,
        'mechanism': mechanism,
        'direction': direction,
        'fromPage': fromPage,
        'toPage': toPage,
      },
    );
  }

  void trackPageCurlAbort({
    required String postId,
    required String corner,
    required double progress,
    required String direction,
  }) {
    _track(
      eventName: ArticleReaderMetricNames.pageCurlAbortRate,
      properties: <String, dynamic>{
        'postId': postId,
        'corner': corner,
        'progress': progress,
        'direction': direction,
      },
    );
  }

  void trackReaderFallback({
    required String postId,
    required String reason,
    required bool bookReaderEnabled,
  }) {
    final key = '$postId|$reason';
    if (!_markFallback(key)) {
      return;
    }
    _track(
      eventName: ArticleReaderMetricNames.readerFallbackRate,
      properties: <String, dynamic>{
        'postId': postId,
        'reason': reason,
        'bookReaderEnabled': bookReaderEnabled,
      },
    );
  }

  bool _markFallback(String key) {
    final now = _now().toUtc();
    _fallbackKeys.removeWhere(
      (_, seenAt) => now.difference(seenAt) >= _fallbackDedupTtl,
    );
    final existing = _fallbackKeys.remove(key);
    if (existing != null) {
      _fallbackKeys[key] = now;
      return false;
    }
    _fallbackKeys[key] = now;
    while (_fallbackKeys.length > _fallbackDedupCapacity) {
      _fallbackKeys.remove(_fallbackKeys.keys.first);
    }
    return true;
  }

  void _track({
    required String eventName,
    required Map<String, dynamic> properties,
  }) {
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'article_reader_metric',
          eventName: eventName,
          properties: properties,
        ),
      ),
    );
  }

  void _record(AppTelemetryPayload payload) {
    unawaited(
      _telemetryRecorder.record(payload, pageName: PageNames.workBrowser),
    );
  }
}

final articleReaderObservabilityProvider = Provider<ArticleReaderObservability>(
  (ref) {
    return ArticleReaderObservability(
      ref.read(analyticsProvider),
      ref.read(appTelemetryReporterProvider),
    );
  },
);
