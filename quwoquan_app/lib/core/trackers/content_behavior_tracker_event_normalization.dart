part of 'content_behavior_tracker.dart';

extension _ContentBehaviorTrackerEventNormalization on ContentBehaviorTracker {
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
      objectId: event.objectId,
      objectKind: event.objectKind,
      displayName: event.displayName,
      sourceSurface: event.sourceSurface,
      tags: event.tags,
      duration: event.duration,
      feedRequestId: event.feedRequestId,
      position: event.position,
      channelId: event.channelId,
      rankingVersion: event.rankingVersion,
      reasonVersion: event.reasonVersion,
      recallPath: event.recallPath,
      contentVertical: event.contentVertical,
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

  String _dedupKey(BehaviorEvent event) {
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
    return '$feed|${event.contentId}|${event.action.wireValue}|${event.state ?? ''}|$subject|$kind|$motion';
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
      case BehaviorAction.intersectionFeedback:
      case BehaviorAction.wishlistRemove:
        return 'negative';
      case BehaviorAction.click:
      case BehaviorAction.intersectionExpand:
      case BehaviorAction.like:
      case BehaviorAction.undoDislike:
      case BehaviorAction.share:
      case BehaviorAction.comment:
      case BehaviorAction.follow:
      case BehaviorAction.authorView:
      case BehaviorAction.entityPageView:
      case BehaviorAction.tagClick:
      case BehaviorAction.playProgress:
      case BehaviorAction.effectivePlay:
      case BehaviorAction.contentDepth:
      case BehaviorAction.joinCircle:
      case BehaviorAction.addContact:
      case BehaviorAction.assistantInterest:
      case BehaviorAction.onboardingInterest:
      case BehaviorAction.wishlistAdd:
        return 'interaction';
    }
  }
}
