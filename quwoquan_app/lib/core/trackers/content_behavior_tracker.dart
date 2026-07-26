import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

part 'content_behavior_tracker_effective_playback.dart';
part 'content_behavior_tracker_event_normalization.dart';

/// 批量行为缓冲 + 自动 flush Tracker。
///
/// 负责将散落的行为事件（impression/dwell/click/dislike/share 等）
/// 按批次合并后统一上报给 BehaviorReporter。
/// like/comment/report 使用专属路由，不经过此 Tracker。
class ContentBehaviorTracker {
  factory ContentBehaviorTracker({
    required BehaviorReporter reporter,
    Duration flushInterval = const Duration(seconds: 5),
    int maxBatchSize = 20,
    bool enablePeriodicFlush = true,
  }) {
    return ContentBehaviorTracker._(
      reporter,
      flushInterval,
      maxBatchSize,
      enablePeriodicFlush,
    );
  }

  ContentBehaviorTracker._(
    this._reporter,
    this._flushInterval,
    this._maxBatchSize,
    bool enablePeriodicFlush,
  ) {
    if (enablePeriodicFlush) {
      _startTimer();
    }
  }

  final BehaviorReporter _reporter;
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
      reasonVersion: reasonVersion,
      recallPath: recallPath,
      contentVertical: contentVertical,
      supplySource: supplySource,
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
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
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
        state: 'click',
        contentType: contentType,
        tags: tags,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
        intersectionId: intersectionId,
        intersectionDimension: intersectionDimension,
        intersectionSourceRef: intersectionSourceRef,
        intersectionTagRefs: intersectionTagRefs,
        intersectionClass: intersectionClass,
        intersectionEvidenceId: intersectionEvidenceId,
      ),
    );
  }

  /// 记录列表入口「查看更多」展开交集列表（intersection_expand）。
  ///
  /// behaviors.yaml 已登记（weight 0.2 弱正信号）、云侧 `SignalWeights` 已受支持；
  /// 本方法补齐端侧执行链（B6）。payload 契约（behaviors.yaml payload_fields）：
  /// intersectionId/dimension/class/sourceRef + surfaceId（经 sourceSurface 承载）。
  /// 展开动作不绑定具体 post，contentId 传交集主体对象 id（无则空串走弱信号观测）。
  void trackIntersectionExpand({
    String? contentId,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionClass,
    String? intersectionSourceRef,
    String? surfaceId,
    ReferralSource? referralSource,
  }) {
    _add(
      BehaviorEvent(
        contentId: contentId ?? '',
        action: BehaviorAction.intersectionExpand,
        state: 'interaction',
        referralSource: referralSource,
        sourceSurface: surfaceId,
        intersectionId: intersectionId,
        intersectionDimension: intersectionDimension,
        intersectionClass: intersectionClass,
        intersectionSourceRef: intersectionSourceRef,
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
      ),
    );
  }

  /// 撤销短时窗口内的「不感兴趣」；只恢复当前内容的精确负反馈。
  void trackUndoDislike(
    String contentId, {
    String? contentType,
    String? authorId,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
  }) {
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorAction.undoDislike,
        state: 'interaction',
        contentType: contentType,
        authorId: authorId,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
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
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
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
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
      ),
    );
  }

  // N0-3：trackComment 已删除。comment 信号由云侧 CommentCreated outbox 事实
  // 权威注入（服务端确认、防伪造），端侧不再补报评论行为。

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

  /// 记录新用户首启兴趣采集（onboarding_interest，W11 interest-onboarding-prior）。
  ///
  /// 四维标签选择（topic/audience/format/entity）合成上报；不绑定具体 post，
  /// 仅回流路径制 tagRefs。云侧强正权重（2.5）写入 HotPath tag weights +
  /// rm_recommend_feature 先验，首刷 TagRecall 立即可用。独立 action 使
  /// onboarding 转化漏斗可与对话兴趣（assistant_interest）分开归因。
  void trackOnboardingInterest(List<String> tagRefs) {
    final normalized = tagRefs
        .map((tag) => tag.trim())
        .where((tag) => tag.isNotEmpty)
        .toSet()
        .toList(growable: false);
    if (normalized.isEmpty) return;
    _add(
      BehaviorEvent(
        contentId: '',
        action: BehaviorAction.onboardingInterest,
        state: 'interaction',
        tags: normalized,
      ),
    );
  }

  /// 记录交集条目负反馈（intersection_feedback，F 推荐与交集配对差异化）。
  ///
  /// 不绑定具体 post：[subjectId] 为交集主体对象（person/circle/place…，与
  /// reason.subjectId / actionTargetId 同源），[feedbackKind] 必须属于
  /// registry.feedbackKinds 闭集（[intersectionFeedbackKinds] codegen 常量，
  /// 端上报与云侧降权/冷却读同一集合）。非法 kind 或空 subject 直接丢弃不上报，
  /// 避免脏信号污染云侧 rec:ineg 交集负反馈冷却集（命中 subject 冷却期内不再推荐）。
  void trackIntersectionFeedback(
    String subjectId, {
    required String feedbackKind,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionClass,
    String? intersectionSourceRef,
  }) {
    final normalizedSubject = subjectId.trim();
    final normalizedKind = feedbackKind.trim();
    if (normalizedSubject.isEmpty ||
        !intersectionFeedbackKinds.contains(normalizedKind)) {
      return;
    }
    _add(
      BehaviorEvent(
        contentId: '',
        action: BehaviorAction.intersectionFeedback,
        state: 'negative',
        subjectId: normalizedSubject,
        feedbackKind: normalizedKind,
        intersectionId: intersectionId,
        intersectionDimension: intersectionDimension,
        intersectionClass: intersectionClass,
        intersectionSourceRef: intersectionSourceRef,
      ),
    );
  }

  /// 记录用户显式点亮「想去 / 收藏 / 计划去」。
  ///
  /// 该事件会由 content-service 投影到 `entity_wishlist_events`，作为
  /// `coWishlistedEntity` 的真实意图源；缺对象 id 或类型时不上报，避免生成
  /// 无法参与交集的脏事实。
  void trackWishlistAdd(
    String objectId, {
    required String objectKind,
    String? displayName,
    String? sourceSurface,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    _trackWishlistIntent(
      objectId,
      action: BehaviorAction.wishlistAdd,
      objectKind: objectKind,
      displayName: displayName,
      sourceSurface: sourceSurface,
      feedRequestId: feedRequestId,
      position: position,
      referralSource: referralSource,
      channelId: channelId,
      rankingVersion: rankingVersion,
    );
  }

  /// 记录用户取消「想去 / 收藏 / 计划去」，云侧标记为 removed。
  void trackWishlistRemove(
    String objectId, {
    required String objectKind,
    String? sourceSurface,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    _trackWishlistIntent(
      objectId,
      action: BehaviorAction.wishlistRemove,
      objectKind: objectKind,
      sourceSurface: sourceSurface,
      feedRequestId: feedRequestId,
      position: position,
      referralSource: referralSource,
      channelId: channelId,
      rankingVersion: rankingVersion,
    );
  }

  void trackWorksImagePageflipMotion(
    String contentId, {
    required String direction,
    required String motionProfile,
    required int settleMs,
    required bool reducedMotion,
    required bool committed,
    String? contentType,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
  }) {
    final normalizedContentId = contentId.trim();
    if (normalizedContentId.isEmpty) {
      return;
    }
    _add(
      BehaviorEvent(
        contentId: normalizedContentId,
        action: BehaviorAction.contentDepth,
        state: 'works_image_pageflip_motion',
        contentType: contentType,
        sourceSurface: 'works_immersive_viewer',
        duration: settleMs <= 0 ? null : settleMs / 1000.0,
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
        reasonVersion: reasonVersion,
        recallPath: recallPath,
        contentVertical: contentVertical,
        supplySource: supplySource,
        motionDirection: direction,
        motionProfile: motionProfile,
        settleMs: settleMs,
        reducedMotion: reducedMotion,
        committed: committed,
      ),
    );
  }

  void _trackWishlistIntent(
    String objectId, {
    required BehaviorAction action,
    required String objectKind,
    String? displayName,
    String? sourceSurface,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? rankingVersion,
  }) {
    final normalizedObjectId = objectId.trim();
    final normalizedObjectKind = objectKind.trim();
    if (normalizedObjectId.isEmpty || normalizedObjectKind.isEmpty) {
      return;
    }
    _add(
      BehaviorEvent(
        contentId: normalizedObjectId,
        action: action,
        state: action == BehaviorAction.wishlistRemove
            ? 'negative'
            : 'interaction',
        contentType: normalizedObjectKind,
        objectId: normalizedObjectId,
        objectKind: normalizedObjectKind,
        displayName: displayName?.trim(),
        sourceSurface: sourceSurface?.trim(),
        entityRefs: <String>[normalizedObjectId],
        feedRequestId: feedRequestId,
        position: position,
        referralSource: referralSource,
        channelId: channelId,
        rankingVersion: rankingVersion,
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

  /// 立即将缓冲区内容上报，并清空缓冲区。
  Future<void> flush() async {
    if (_buffer.isEmpty) return;
    final toSend = List<BehaviorEvent>.from(_buffer);
    _buffer.clear();
    _bufferDedupKeys.clear();
    try {
      await _reporter.reportEvents(events: toSend);
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
  final reporter = ref.watch(behaviorReporterProvider);
  final tracker = ContentBehaviorTracker(reporter: reporter);
  ref.onDispose(() => tracker.dispose());
  return tracker;
});
