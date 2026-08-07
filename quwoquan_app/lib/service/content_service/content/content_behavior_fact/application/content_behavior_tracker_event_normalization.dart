import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show BehaviorEventType;

BehaviorEvent normalizeContentBehaviorEvent(BehaviorEvent event) {
  if ((event.clientEventId ?? '').isNotEmpty) return event;
  final now = DateTime.now().toUtc().microsecondsSinceEpoch;
  final safeContent = event.contentId.isEmpty ? 'none' : event.contentId;
  final feed = event.feedRequestId?.trim();
  final suffix = feed == null || feed.isEmpty ? now.toString() : feed;
  return BehaviorEvent(
    clientEventId: 'beh:${event.action.wireName}:$safeContent:$suffix:$now',
    state: event.state ?? _stateForAction(event.action),
    contentId: event.contentId,
    action: event.action,
    contentType: event.contentType,
    objectId: event.objectId,
    objectKind: event.objectKind,
    displayName: event.displayName,
    sourceSurface: event.sourceSurface,
    tags: event.tags,
    duration: event.duration,
    feedRequestId: event.feedRequestId,
    position: event.position,
    channelId: event.channelId,
    policyDigest: event.policyDigest,
    recallPath: event.recallPath,
    supplySource: event.supplySource,
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
    subjectId: event.subjectId,
    feedbackKind: event.feedbackKind,
    motionDirection: event.motionDirection,
    motionProfile: event.motionProfile,
    settleMs: event.settleMs,
    reducedMotion: event.reducedMotion,
    committed: event.committed,
  );
}

String contentBehaviorEventDedupKey(BehaviorEvent event) {
  final feed = event.feedRequestId ?? '';
  // subjectId + feedbackKind 纳入去重键：交集负反馈不绑定 post（contentId 恒空），
  // 若仅按 contentId/action/state 去重会把不同 subject / 不同 kind 的负反馈误合并成一条，
  // 导致多主体降权 / 冷却丢失（F 推荐差异化）。非交集事件二者为空，去重语义不变。
  final subject = event.subjectId ?? '';
  final kind = event.feedbackKind ?? '';
  final motion =
      '${event.motionDirection ?? ''}|${event.motionProfile ?? ''}|'
      '${event.settleMs ?? ''}|${event.reducedMotion ?? ''}|'
      '${event.committed ?? ''}';
  return '$feed|${event.contentId}|${event.action.wireName}|${event.state ?? ''}|$subject|$kind|$motion';
}

String _stateForAction(BehaviorEventType action) {
  switch (action) {
    case BehaviorEventType.impression:
      return 'impressed';
    case BehaviorEventType.dwell:
      return 'dwell';
    case BehaviorEventType.dislike:
    case BehaviorEventType.hideAuthor:
    case BehaviorEventType.hideContentType:
    case BehaviorEventType.report:
    case BehaviorEventType.skip:
    case BehaviorEventType.intersectionFeedback:
    case BehaviorEventType.wishlistRemove:
      return 'negative';
    case BehaviorEventType.click:
    case BehaviorEventType.intersectionExpand:
    case BehaviorEventType.like:
    case BehaviorEventType.undoDislike:
    case BehaviorEventType.share:
    case BehaviorEventType.comment:
    case BehaviorEventType.follow:
    case BehaviorEventType.authorView:
    case BehaviorEventType.entityPageView:
    case BehaviorEventType.tagClick:
    case BehaviorEventType.playProgress:
    case BehaviorEventType.effectivePlay:
    case BehaviorEventType.contentDepth:
    case BehaviorEventType.joinCircle:
    case BehaviorEventType.addContact:
    case BehaviorEventType.assistantInterest:
    case BehaviorEventType.onboardingInterest:
    case BehaviorEventType.wishlistAdd:
      return 'interaction';
    // leave_circle 由 behaviors.yaml non_content_signal_events 声明为非内容推荐信号，
    // owner 是 circle_management/circle_behavior_fact，只经 AppendCircleBehaviorFact 上报。
    // 内容侧没有对应 tracker 方法；若它出现在这里说明有人新开了第二条上报轨，
    // 必须暴露而不是按正向 interaction 兜底污染内容推荐。
    case BehaviorEventType.leaveCircle:
      throw StateError(
        'leave_circle 不是内容行为事件，禁止进入 POST /content/behaviors；'
        '圈子行为事实请走 AppendCircleBehaviorFact',
      );
  }
}
