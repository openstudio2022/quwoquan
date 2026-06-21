import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 批量行为缓冲 + 自动 flush Tracker。
///
/// 负责将散落的行为事件（impression/dwell/click/dislike/share 等）
/// 按批次合并后统一上报给 BehaviorRepository。
/// like/comment/report 使用专属路由，不经过此 Tracker。
class ContentBehaviorTracker {
  factory ContentBehaviorTracker({
    required BehaviorRepository repository,
    Duration flushInterval = const Duration(seconds: 5),
    int maxBatchSize = 20,
    bool enablePeriodicFlush = true,
  }) {
    return ContentBehaviorTracker._(
      repository,
      flushInterval,
      maxBatchSize,
      enablePeriodicFlush,
    );
  }

  ContentBehaviorTracker._(
    this._repository,
    this._flushInterval,
    this._maxBatchSize,
    bool enablePeriodicFlush,
  ) {
    if (enablePeriodicFlush) {
      _startTimer();
    }
  }

  final BehaviorRepository _repository;
  final Duration _flushInterval;
  final int _maxBatchSize;

  final List<BehaviorEvent> _buffer = <BehaviorEvent>[];
  final Set<String> _bufferDedupKeys = <String>{};
  // 同一页面 impression 去重：同一 contentId 只上报一次
  final Set<String> _impressionSeen = <String>{};
  Timer? _timer;

  void _startTimer() {
    _timer = Timer.periodic(_flushInterval, (_) => flush());
  }

  /// 记录一次真实曝光（impressed）。同一 contentId 在本 session 内去重。
  ///
  /// 调用方应在可见面积 + 停留阈值达标后调用；若没有阈值证据，
  /// 请调用 [trackVisible]，避免把 build/enter 误记为真实曝光。
  void trackImpression(
    String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
    String? intersectionClass,
    String? intersectionEvidenceId,
  }) {
    trackQualifiedImpression(
      contentId,
      visibleFraction: 1,
      visibleDuration: const Duration(milliseconds: 1000),
      contentType: contentType,
      tags: tags,
      feedRequestId: feedRequestId,
      position: position,
      referralSource: referralSource,
      channelId: channelId,
      rankingVersion: rankingVersion,
      intersectionId: intersectionId,
      intersectionDimension: intersectionDimension,
      intersectionSourceRef: intersectionSourceRef,
      intersectionTagRefs: intersectionTagRefs,
      intersectionClass: intersectionClass,
      intersectionEvidenceId: intersectionEvidenceId,
    );
  }

  /// 记录弱可见性（visible），不等同于真实 impressed。
  void trackVisible(
    String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.impression,
        state: 'visible',
        contentType: contentType,
        tags: tags,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
      ),
    );
  }

  /// 达到「可见面积 + 停留」阈值后上报真实 impressed；未达标仅记 visible。
  void trackQualifiedImpression(
    String contentId, {
    required double visibleFraction,
    required Duration visibleDuration,
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
    String? intersectionClass,
    String? intersectionEvidenceId,
  }) {
    if (visibleFraction < 0.5 ||
        visibleDuration < const Duration(milliseconds: 1000)) {
      trackVisible(
        contentId,
        contentType: contentType,
        tags: tags,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
      );
      return;
    }
    if (_impressionSeen.contains(contentId)) return;
    _impressionSeen.add(contentId);
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.impression,
        state: 'impressed',
        contentType: contentType,
        tags: tags,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
        intersectionId: intersectionId,
        intersectionDimension: intersectionDimension,
        intersectionSourceRef: intersectionSourceRef,
        intersectionTagRefs: intersectionTagRefs,
        intersectionClass: intersectionClass,
        intersectionEvidenceId: intersectionEvidenceId,
      ),
    );
  }

  /// 记录停留时长（dwell）。
  void trackDwell(
    String contentId, {
    required double durationSeconds,
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    if (durationSeconds < 1) return;
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.dwell,
        state: 'dwell',
        contentType: contentType,
        tags: tags,
        duration: durationSeconds,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
      ),
    );
  }

  /// 记录点击（click）。
  void trackClick(
    String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
    String? intersectionClass,
    String? intersectionEvidenceId,
  }) {
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.click,
        state: 'interaction',
        contentType: contentType,
        tags: tags,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
        intersectionId: intersectionId,
        intersectionDimension: intersectionDimension,
        intersectionSourceRef: intersectionSourceRef,
        intersectionTagRefs: intersectionTagRefs,
        intersectionClass: intersectionClass,
        intersectionEvidenceId: intersectionEvidenceId,
      ),
    );
  }

  /// 记录交集证据组 / 内容标签点击（tag_click）。
  ///
  /// 语义区别于 [trackClick]：`tag_click` 在推荐 HotPath 有独立强权重（云侧
  /// `behaviors.yaml` 已登记、`runtime/recommendation/hotpath.go` 权重 1.8），
  /// 用于交集证据组与内容标签点击；**禁止降级为 `click`**（会丢权重、改变推荐归因）。
  /// 归因字段与统一交互子契约对齐（intersectionId/dimension/sourceRef/class/tagRefs/evidenceId），
  /// 统一通道（替代散落的 `behaviorRepository.reportEvents` 直发）但不改信号语义。
  void trackTagClick(
    String contentId, {
    String? contentType,
    String? authorId,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
    String? intersectionClass,
    String? intersectionEvidenceId,
  }) {
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.tagClick,
        state: 'interaction',
        contentType: contentType,
        authorId: authorId,
        tags: tags,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
        intersectionId: intersectionId,
        intersectionDimension: intersectionDimension,
        intersectionSourceRef: intersectionSourceRef,
        intersectionTagRefs: intersectionTagRefs,
        intersectionClass: intersectionClass,
        intersectionEvidenceId: intersectionEvidenceId,
      ),
    );
  }

  /// 记录「不感兴趣」（dislike）。
  void trackDislike(
    String contentId, {
    String? contentType,
    List<String>? tags,
    String? authorId,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.dislike,
        state: 'negative',
        contentType: contentType,
        tags: tags,
        authorId: authorId,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
      ),
    );
  }

  /// 记录「减少该作者内容」（hide_author）。当前内容同时会被云侧纳入 negative。
  void trackHideAuthor(
    String contentId, {
    required String authorId,
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    final normalizedAuthorId = authorId.trim();
    if (normalizedAuthorId.isEmpty) return;
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.hideAuthor,
        state: 'negative',
        contentType: contentType,
        tags: tags,
        authorId: normalizedAuthorId,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
      ),
    );
  }

  /// 记录「减少此类内容」（hide_content_type）。当前内容同时会被云侧纳入 negative。
  void trackHideContentType(
    String contentId, {
    required String contentType,
    List<String>? tags,
    String? authorId,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    final normalizedType = contentType.trim();
    if (normalizedType.isEmpty) return;
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.hideContentType,
        state: 'negative',
        contentType: normalizedType,
        tags: tags,
        authorId: authorId,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
      ),
    );
  }

  /// 记录分享（share）。
  void trackShare(
    String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.share,
        state: 'interaction',
        contentType: contentType,
        tags: tags,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
      ),
    );
  }

  /// 记录翻页跳过（skip）——沉浸式流翻到下一帖时上报前帖。
  void trackSkip(
    String contentId, {
    double? dwellSeconds,
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.skip,
        state: 'negative',
        contentType: contentType,
        tags: tags,
        duration: dwellSeconds,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
      ),
    );
  }

  /// 记录评论完成（comment）。
  void trackComment(
    String contentId, {
    String? contentType,
    int? commentLength,
    List<String>? tags,
    String? feedRequestId,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.comment,
        state: 'interaction',
        contentType: contentType,
        tags: tags,
        feedRequestId: feedRequestId,
        commentLength: commentLength,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
      ),
    );
  }

  /// 记录关注完成（follow）。关注是交集行动，回流带 dimension + tagRefs（B3 归因）。
  void trackFollow(
    String authorId, {
    String? feedRequestId,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
  }) {
    _add(
      BehaviorEvent(
        contentId: authorId,
        action: BehaviorAction.follow,
        state: 'interaction',
        authorId: authorId,
        feedRequestId: feedRequestId,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
        intersectionDimension: intersectionDimension,
        intersectionSourceRef: intersectionSourceRef,
        intersectionTagRefs: intersectionTagRefs,
      ),
    );
  }

  /// 记录加入圈子（join_circle）。交集行动，回流带 dimension + tagRefs（S6 归因）。
  void trackJoinCircle(
    String circleId, {
    String? feedRequestId,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
  }) {
    _add(
      BehaviorEvent(
        contentId: circleId,
        action: BehaviorAction.joinCircle,
        state: 'interaction',
        feedRequestId: feedRequestId,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
        intersectionDimension: intersectionDimension,
        intersectionSourceRef: intersectionSourceRef,
        intersectionTagRefs: intersectionTagRefs,
      ),
    );
  }

  /// 记录添加联系人（add_contact）。交集行动，回流带 dimension + tagRefs（S6 归因）。
  void trackAddContact(
    String authorId, {
    String? feedRequestId,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
  }) {
    _add(
      BehaviorEvent(
        contentId: authorId,
        action: BehaviorAction.addContact,
        state: 'interaction',
        authorId: authorId,
        feedRequestId: feedRequestId,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
        intersectionDimension: intersectionDimension,
        intersectionSourceRef: intersectionSourceRef,
        intersectionTagRefs: intersectionTagRefs,
      ),
    );
  }

  /// 记录小艺对话浮现兴趣（assistant_interest）。不绑定具体 post，仅回流路径制 tagRefs。
  ///
  /// 经 reportEvents → 云侧 BehaviorBatchReported → RecommendFeatureProjector
  /// 的 tagInteraction 累加，使对话兴趣进入推荐特征（rm_recommend_feature）。
  void trackAssistantInterest(List<String> tagRefs) {
    final normalized = tagRefs
        .map((tag) => tag.trim())
        .where((tag) => tag.isNotEmpty)
        .toSet()
        .toList(growable: false);
    if (normalized.isEmpty) return;
    _add(
      BehaviorEvent(
        contentId: '',
        action: BehaviorAction.assistantInterest,
        state: 'interaction',
        tags: normalized,
      ),
    );
  }

  void _add(BehaviorEvent event) {
    final normalized = _withClientEventId(event);
    final dedupKey = _dedupKey(normalized);
    if (!_bufferDedupKeys.add(dedupKey)) return;
    _buffer.add(normalized);
    if (_buffer.length >= _maxBatchSize) {
      flush();
    }
  }

  BehaviorEvent _withClientEventId(BehaviorEvent event) {
    if ((event.clientEventId ?? '').isNotEmpty) return event;
    final now = DateTime.now().toUtc().microsecondsSinceEpoch;
    final safeContent = event.contentId.isEmpty ? 'none' : event.contentId;
    final feed = event.feedRequestId?.trim();
    final suffix = feed == null || feed.isEmpty ? now.toString() : feed;
    return BehaviorEvent(
      clientEventId: 'beh:${event.action.wireValue}:$safeContent:$suffix:$now',
      state: event.state ?? _stateForAction(event.action),
      contentId: event.contentId,
      action: event.action,
      contentType: event.contentType,
      tags: event.tags,
      duration: event.duration,
      feedRequestId: event.feedRequestId,
      position: event.position,
      channelId: event.channelId,
      rankingVersion: event.rankingVersion,
      commentLength: event.commentLength,
      authorId: event.authorId,
      referralSource: event.referralSource,
      engagementDepth: event.engagementDepth,
      consumedRatio: event.consumedRatio,
      totalUnits: event.totalUnits,
      entityRefs: event.entityRefs,
      pageVisitId: event.pageVisitId,
      intersectionDimension: event.intersectionDimension,
      intersectionSourceRef: event.intersectionSourceRef,
      intersectionTagRefs: event.intersectionTagRefs,
      intersectionId: event.intersectionId,
      intersectionClass: event.intersectionClass,
      intersectionEvidenceId: event.intersectionEvidenceId,
    );
  }

  String _dedupKey(BehaviorEvent event) {
    final feed = event.feedRequestId ?? '';
    return '$feed|${event.contentId}|${event.action.wireValue}|${event.state ?? ''}';
  }

  String _stateForAction(BehaviorAction action) {
    switch (action) {
      case BehaviorAction.impression:
        return 'impressed';
      case BehaviorAction.dwell:
        return 'dwell';
      case BehaviorAction.dislike:
      case BehaviorAction.hideAuthor:
      case BehaviorAction.hideContentType:
      case BehaviorAction.report:
      case BehaviorAction.skip:
        return 'negative';
      case BehaviorAction.click:
      case BehaviorAction.like:
      case BehaviorAction.share:
      case BehaviorAction.comment:
      case BehaviorAction.follow:
      case BehaviorAction.authorView:
      case BehaviorAction.entityPageView:
      case BehaviorAction.tagClick:
      case BehaviorAction.playProgress:
      case BehaviorAction.contentDepth:
      case BehaviorAction.joinCircle:
      case BehaviorAction.addContact:
      case BehaviorAction.assistantInterest:
        return 'interaction';
    }
  }

  /// 立即将缓冲区内容上报，并清空缓冲区。
  Future<void> flush() async {
    if (_buffer.isEmpty) return;
    final toSend = List<BehaviorEvent>.from(_buffer);
    _buffer.clear();
    _bufferDedupKeys.clear();
    try {
      await _repository.reportEvents(events: toSend);
    } catch (error, stackTrace) {
      // 任务 B · 失败路径结构化归因：批量上报失败时记录并有界回灌，
      // 避免周期 flush 抛出未捕获异步异常，也避免行为事件被静默丢弃。
      developer.log(
        'behavior flush failed: ${toSend.length} event(s) deferred for retry',
        name: 'ContentBehaviorTracker',
        error: error,
        stackTrace: stackTrace,
      );
      if (_buffer.length < _maxBatchSize * 3) {
        _buffer.insertAll(0, toSend);
      }
    }
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
