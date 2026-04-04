import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/analytics/analytics.dart';

class ArticleReaderMetricNames {
  static const String readerOpenMs = 'article_reader_open_ms';
  static const String hydrationMs = 'article_reader_hydration_ms';
  static const String pageFlipCommitMs = 'article_page_flip_commit_ms';
  static const String pageCurlAbortRate = 'article_page_curl_abort_rate';
  static const String readerFallbackRate = 'article_reader_fallback_rate';

  const ArticleReaderMetricNames._();
}

class ArticleReaderObservability {
  ArticleReaderObservability({required AnalyticsService analytics})
    : _analytics = analytics;

  final AnalyticsService _analytics;
  final Set<String> _openReportedPostIds = <String>{};
  final Set<String> _fallbackKeys = <String>{};

  void trackReaderOpen({
    required String postId,
    required int durationMs,
    required String source,
    required String template,
    required String fontPreset,
    required int pageCount,
    required bool bookReaderEnabled,
  }) {
    if (!_openReportedPostIds.add(postId)) {
      return;
    }
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
  }) {
    _track(
      eventName: ArticleReaderMetricNames.pageCurlAbortRate,
      properties: <String, dynamic>{
        'postId': postId,
        'corner': corner,
        'progress': progress,
      },
    );
  }

  void trackReaderFallback({
    required String postId,
    required String reason,
    required bool bookReaderEnabled,
  }) {
    final key = '$postId|$reason';
    if (!_fallbackKeys.add(key)) {
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
}

final articleReaderObservabilityProvider = Provider<ArticleReaderObservability>(
  (ref) {
    return ArticleReaderObservability(analytics: ref.read(analyticsProvider));
  },
);
