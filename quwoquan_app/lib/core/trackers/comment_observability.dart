import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/analytics/analytics.dart';

class CommentMetricNames {
  static const String listLoadMs = 'comment_list_load_ms';
  static const String submitConfirmMs = 'comment_submit_confirm_ms';
  static const String replyExpandMs = 'comment_reply_expand_ms';
  static const String reactionConfirmMs = 'comment_reaction_confirm_ms';
  static const String pollingRefreshMs = 'comment_polling_refresh_ms';
  static const String pinConfirmMs = 'comment_pin_confirm_ms';

  const CommentMetricNames._();
}

class CommentEventNames {
  static const String surfaceExpose = 'comment_surface_expose';
  static const String replyExpanded = 'comment_reply_expanded';
  static const String replyCollapsed = 'comment_reply_collapsed';
  static const String submitSucceeded = 'comment_submit_succeeded';
  static const String submitFailed = 'comment_submit_failed';
  static const String reactionChanged = 'comment_reaction_changed';

  /// 评论置顶/取消置顶（仅内容作者）。reaction 字段复用为 pin/unpin 区分。
  static const String pinChanged = 'comment_pin_changed';
  static const String attachmentAdded = 'comment_attachment_added';
  static const String mentionAdded = 'comment_mention_added';
  static const String reported = 'comment_reported';
  static const String newNoticeClicked = 'comment_new_notice_clicked';
  static const String surfaceClosed = 'comment_surface_closed';
  static const String listCacheHit = 'comment_list_cache_hit';

  /// 评论深链：从入口（如「我的-互动」）跳转打开评论区，或评论列表定位高亮命中目标。
  /// entrySource 区分入口（profile-interaction）与落地（deeplink-highlight）。
  static const String deeplinkOpened = 'comment_deeplink_opened';

  const CommentEventNames._();
}

class CommentObservability {
  CommentObservability({required this._analytics});

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
            'commentId': ?commentId,
            'source': ?source,
            'itemCount': ?itemCount,
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
    String? result,
  }) {
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'comment_action',
          eventName: eventName,
          properties: <String, dynamic>{
            'postId': postId,
            'commentId': ?commentId,
            'entrySource': ?entrySource,
            'surfaceMode': ?surfaceMode,
            'sortMode': ?sortMode,
            'replyDepth': ?replyDepth,
            'latencyMs': ?latencyMs,
            'failureKind': ?failureKind,
            'attachmentCount': ?attachmentCount,
            'mentionCount': ?mentionCount,
            'itemCount': ?itemCount,
            'reaction': ?reaction,
            'result': ?result,
          },
        ),
      ),
    );
  }
}

final commentObservabilityProvider = Provider<CommentObservability>((ref) {
  return CommentObservability(analytics: ref.read(analyticsProvider));
});
