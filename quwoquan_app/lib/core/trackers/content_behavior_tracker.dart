import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 批量行为缓冲 + 自动 flush Tracker。
///
/// 负责将散落的行为事件（impression/dwell/click/dislike/share 等）
/// 按批次合并后统一上报给 BehaviorRepository。
/// like/favorite/comment/report 使用专属路由，不经过此 Tracker。
class ContentBehaviorTracker {
  ContentBehaviorTracker({
    required BehaviorRepository repository,
    Duration flushInterval = const Duration(seconds: 5),
    int maxBatchSize = 20,
  })  : _repository = repository,
        _flushInterval = flushInterval,
        _maxBatchSize = maxBatchSize {
    _startTimer();
  }

  final BehaviorRepository _repository;
  final Duration _flushInterval;
  final int _maxBatchSize;

  final List<BehaviorEvent> _buffer = <BehaviorEvent>[];
  // 同一页面 impression 去重：同一 contentId 只上报一次
  final Set<String> _impressionSeen = <String>{};
  Timer? _timer;

  void _startTimer() {
    _timer = Timer.periodic(_flushInterval, (_) => flush());
  }

  /// 记录一次曝光（impression）。同一 contentId 在本 session 内去重。
  void trackImpression(String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
  }) {
    if (_impressionSeen.contains(contentId)) return;
    _impressionSeen.add(contentId);
    _add(BehaviorEvent(
      contentId: contentId,
      action: BehaviorAction.impression,
      contentType: contentType,
      tags: tags,
      feedRequestId: feedRequestId,
      position: position,
    ));
  }

  /// 记录停留时长（dwell）。
  void trackDwell(String contentId, {
    required double durationSeconds,
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
  }) {
    if (durationSeconds < 1) return;
    _add(BehaviorEvent(
      contentId: contentId,
      action: BehaviorAction.dwell,
      contentType: contentType,
      tags: tags,
      duration: durationSeconds,
      feedRequestId: feedRequestId,
      position: position,
    ));
  }

  /// 记录点击（click）。
  void trackClick(String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
  }) {
    _add(BehaviorEvent(
      contentId: contentId,
      action: BehaviorAction.click,
      contentType: contentType,
      tags: tags,
      feedRequestId: feedRequestId,
      position: position,
    ));
  }

  /// 记录「不感兴趣」（dislike）。
  void trackDislike(String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
  }) {
    _add(BehaviorEvent(
      contentId: contentId,
      action: BehaviorAction.dislike,
      contentType: contentType,
      tags: tags,
      feedRequestId: feedRequestId,
      position: position,
    ));
  }

  /// 记录分享（share）。
  void trackShare(String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
  }) {
    _add(BehaviorEvent(
      contentId: contentId,
      action: BehaviorAction.share,
      contentType: contentType,
      tags: tags,
      feedRequestId: feedRequestId,
      position: position,
    ));
  }

  /// 记录翻页跳过（skip）——沉浸式流翻到下一帖时上报前帖。
  void trackSkip(String contentId, {
    double? dwellSeconds,
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
  }) {
    _add(BehaviorEvent(
      contentId: contentId,
      action: BehaviorAction.skip,
      contentType: contentType,
      tags: tags,
      duration: dwellSeconds,
      feedRequestId: feedRequestId,
      position: position,
    ));
  }

  /// 记录评论完成（comment）。
  void trackComment(String contentId, {
    String? contentType,
    int? commentLength,
    List<String>? tags,
    String? feedRequestId,
  }) {
    _add(BehaviorEvent(
      contentId: contentId,
      action: BehaviorAction.comment,
      contentType: contentType,
      tags: tags,
      feedRequestId: feedRequestId,
      commentLength: commentLength,
    ));
  }

  /// 记录关注完成（follow）。
  void trackFollow(String authorId, {
    String? feedRequestId,
  }) {
    _add(BehaviorEvent(
      contentId: authorId,
      action: BehaviorAction.follow,
      feedRequestId: feedRequestId,
    ));
  }

  void _add(BehaviorEvent event) {
    _buffer.add(event);
    if (_buffer.length >= _maxBatchSize) {
      flush();
    }
  }

  /// 立即将缓冲区内容上报，并清空缓冲区。
  Future<void> flush() async {
    if (_buffer.isEmpty) return;
    final toSend = List<BehaviorEvent>.from(_buffer);
    _buffer.clear();
    await _repository.reportEvents(events: toSend);
  }

  /// 销毁时停止定时器并 flush 剩余事件。
  Future<void> dispose() async {
    _timer?.cancel();
    _timer = null;
    await flush();
  }
}

/// Riverpod Provider：ContentBehaviorTracker 单例。
///
/// 生命周期与 ProviderContainer 绑定；销毁时自动 flush。
final contentBehaviorTrackerProvider = Provider<ContentBehaviorTracker>((ref) {
  final repo = ref.watch(behaviorRepositoryProvider);
  final tracker = ContentBehaviorTracker(repository: repo);
  ref.onDispose(() => tracker.dispose());
  return tracker;
});
