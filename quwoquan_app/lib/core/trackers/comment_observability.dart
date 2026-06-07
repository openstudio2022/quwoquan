import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/analytics/analytics.dart';

class CommentMetricNames {
  static const String listLoadMs = 'comment_list_load_ms';
  static const String submitConfirmMs = 'comment_submit_confirm_ms';
  static const String replyExpandMs = 'comment_reply_expand_ms';
  static const String reactionConfirmMs = 'comment_reaction_confirm_ms';
  static const String pollingRefreshMs = 'comment_polling_refresh_ms';

  const CommentMetricNames._();
}

class CommentEventNames {
  static const String surfaceExpose = 'comment_surface_expose';
  static const String sortChanged = 'comment_sort_changed';
  static const String replyExpanded = 'comment_reply_expanded';
  static const String submitSucceeded = 'comment_submit_succeeded';
  static const String submitFailed = 'comment_submit_failed';
  static const String reactionChanged = 'comment_reaction_changed';
  static const String attachmentAdded = 'comment_attachment_added';
  static const String mentionAdded = 'comment_mention_added';
  static const String reported = 'comment_reported';
  static const String newNoticeClicked = 'comment_new_notice_clicked';
  static const String surfaceClosed = 'comment_surface_closed';
  static const String listCacheHit = 'comment_list_cache_hit';

  const CommentEventNames._();
}

class CommentObservability {
  CommentObservability({required AnalyticsService analytics})
    : _analytics = analytics;

  final AnalyticsService _analytics;

  void trackLatency({
    required String metricName,
    required String postId,
    required int durationMs,
    required String result,
    String? commentId,
    String? source,
    int? itemCount,
  }) {
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'comment_metric',
          eventName: metricName,
          properties: <String, dynamic>{
            'postId': postId,
            'durationMs': durationMs,
            'result': result,
            if (commentId != null) 'commentId': commentId,
            if (source != null) 'source': source,
            if (itemCount != null) 'itemCount': itemCount,
          },
        ),
      ),
    );
  }

  void trackAction({
    required String eventName,
    required String postId,
    String? commentId,
    String? entrySource,
    String? surfaceMode,
    String? sortMode,
    int? replyDepth,
    int? latencyMs,
    String? failureKind,
    int? attachmentCount,
    int? mentionCount,
    int? itemCount,
    String? reaction,
  }) {
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'comment_action',
          eventName: eventName,
          properties: <String, dynamic>{
            'postId': postId,
            if (commentId != null) 'commentId': commentId,
            if (entrySource != null) 'entrySource': entrySource,
            if (surfaceMode != null) 'surfaceMode': surfaceMode,
            if (sortMode != null) 'sortMode': sortMode,
            if (replyDepth != null) 'replyDepth': replyDepth,
            if (latencyMs != null) 'latencyMs': latencyMs,
            if (failureKind != null) 'failureKind': failureKind,
            if (attachmentCount != null) 'attachmentCount': attachmentCount,
            if (mentionCount != null) 'mentionCount': mentionCount,
            if (itemCount != null) 'itemCount': itemCount,
            if (reaction != null) 'reaction': reaction,
          },
        ),
      ),
    );
  }
}

final commentObservabilityProvider = Provider<CommentObservability>((ref) {
  return CommentObservability(analytics: ref.read(analyticsProvider));
});
