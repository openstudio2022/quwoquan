import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/profile_interaction_activity_view_data.dart';

enum ShareInteractionDirection {
  received,
  initiated;

  String get wireValue => this == received ? 'received' : 'sent';
}

enum ShareTargetKind { record, discussion }

enum ShareTargetAvailability {
  active,
  deleted,
  private,
  reviewing,
  authorDeactivated,
  // 云侧取值不在本端闭集内时落这里。它是显式成员而不是放行态，
  // 因此每个消费点的穷尽 switch 都必须给它一条分支。
  unknown,
}

enum SharePreviewKind { image, video, text, discussion, unavailable }

enum ShareInteractionDateGroup { today, yesterday, older }

enum ShareTargetNavigationResolution { originalTarget, unavailable }

class ShareInteractionItem {
  const ShareInteractionItem({
    required this.interactionId,
    required this.direction,
    required this.displayPersonaId,
    required this.displayName,
    required this.displayAvatarUrl,
    required this.targetPersonaId,
    required this.targetContentId,
    required this.targetContentType,
    required this.targetSummary,
    required this.targetKind,
    required this.targetAvailability,
    required this.targetReplyCount,
    required this.previewKind,
    required this.previewImageUrl,
    required this.previewText,
    required this.outboundShareEventId,
    required this.shareText,
    required this.impactPrimaryText,
    required this.impactDeepLink,
    required this.occurredAt,
    this.seenAt,
    this.readAt,
  });

  final String interactionId;
  final ShareInteractionDirection direction;
  final String displayPersonaId;
  final String displayName;
  final String displayAvatarUrl;
  final String targetPersonaId;
  final String targetContentId;
  final String targetContentType;
  final String targetSummary;
  final ShareTargetKind targetKind;
  final ShareTargetAvailability targetAvailability;
  final int targetReplyCount;
  final SharePreviewKind previewKind;
  final String previewImageUrl;
  final String previewText;

  /// 不可变的站外分享事实 ID。它不能被当作内容或路由目标打开。
  final String outboundShareEventId;
  final String shareText;
  final String impactPrimaryText;
  final String impactDeepLink;
  final DateTime occurredAt;
  final DateTime? seenAt;
  final DateTime? readAt;

  bool get isUnread =>
      direction == ShareInteractionDirection.received && readAt == null;

  bool get hasImpact =>
      direction == ShareInteractionDirection.received &&
      impactPrimaryText.trim().isNotEmpty;

  bool get impactIsNavigable =>
      hasImpact && impactDeepLink.trim() == 'myIntersections';

  bool get canOpenTarget =>
      targetContentId.isNotEmpty &&
      targetAvailability == ShareTargetAvailability.active;

  ShareTargetNavigationResolution get targetNavigationResolution {
    if (canOpenTarget) {
      return ShareTargetNavigationResolution.originalTarget;
    }
    return ShareTargetNavigationResolution.unavailable;
  }

  factory ShareInteractionItem.fromActivity(
    ProfileInteractionActivityViewData activity,
    ShareInteractionDirection direction,
  ) {
    final displayPersonaId = direction == ShareInteractionDirection.received
        ? activity.actorPersonaId
        : (activity.counterpartPersonaId.isNotEmpty
              ? activity.counterpartPersonaId
              : activity.targetPersonaId);
    final displayName = direction == ShareInteractionDirection.received
        ? activity.actorDisplayName
        : (activity.counterpartDisplayName.isNotEmpty
              ? activity.counterpartDisplayName
              : activity.displayName);
    final displayAvatarUrl = direction == ShareInteractionDirection.received
        ? activity.actorAvatarUrl
        : (activity.counterpartAvatarUrl.isNotEmpty
              ? activity.counterpartAvatarUrl
              : activity.displayAvatarUrl);
    final targetKind = activity.targetKind == 'discussion'
        ? ShareTargetKind.discussion
        : ShareTargetKind.record;
    final availability = _parseAvailability(activity.targetAvailability);
    return ShareInteractionItem(
      interactionId: activity.activityId,
      direction: direction,
      displayPersonaId: displayPersonaId,
      displayName: displayName,
      displayAvatarUrl: displayAvatarUrl,
      targetPersonaId: activity.targetPersonaId,
      targetContentId: activity.targetContentId,
      targetContentType: activity.targetContentType,
      targetSummary: activity.targetContentSummary,
      targetKind: targetKind,
      targetAvailability: availability,
      targetReplyCount: activity.targetReplyCount,
      previewKind: _parsePreviewKind(
        activity.previewMediaKind,
        targetKind,
        availability,
      ),
      previewImageUrl: activity.previewImageUrl,
      previewText: activity.previewText,
      outboundShareEventId: activity.outboundShareEventId,
      shareText: activity.shareText.isNotEmpty
          ? activity.shareText
          : activity.contextText,
      impactPrimaryText: direction == ShareInteractionDirection.received
          ? activity.impactPrimaryText
          : '',
      impactDeepLink: direction == ShareInteractionDirection.received
          ? activity.impactDeepLink
          : '',
      occurredAt:
          activity.occurredAt ??
          activity.createdAt ??
          DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
      seenAt: direction == ShareInteractionDirection.received
          ? activity.seenAt
          : null,
      readAt: direction == ShareInteractionDirection.received
          ? activity.readAt
          : null,
    );
  }

  ShareInteractionItem copyWith({DateTime? seenAt, DateTime? readAt}) {
    return ShareInteractionItem(
      interactionId: interactionId,
      direction: direction,
      displayPersonaId: displayPersonaId,
      displayName: displayName,
      displayAvatarUrl: displayAvatarUrl,
      targetPersonaId: targetPersonaId,
      targetContentId: targetContentId,
      targetContentType: targetContentType,
      targetSummary: targetSummary,
      targetKind: targetKind,
      targetAvailability: targetAvailability,
      targetReplyCount: targetReplyCount,
      previewKind: previewKind,
      previewImageUrl: previewImageUrl,
      previewText: previewText,
      outboundShareEventId: outboundShareEventId,
      shareText: shareText,
      impactPrimaryText: impactPrimaryText,
      impactDeepLink: impactDeepLink,
      occurredAt: occurredAt,
      seenAt: seenAt ?? this.seenAt,
      readAt: readAt ?? this.readAt,
    );
  }
}

ShareInteractionDateGroup shareInteractionDateGroup(
  DateTime occurredAt,
  DateTime now,
) {
  final localOccurred = occurredAt.toLocal();
  final localNow = now.toLocal();
  final today = DateTime(localNow.year, localNow.month, localNow.day);
  final day = DateTime(
    localOccurred.year,
    localOccurred.month,
    localOccurred.day,
  );
  final difference = today.difference(day).inDays;
  if (difference <= 0) return ShareInteractionDateGroup.today;
  if (difference == 1) return ShareInteractionDateGroup.yesterday;
  return ShareInteractionDateGroup.older;
}

ShareTargetAvailability _parseAvailability(String raw) {
  switch (raw.trim()) {
    case 'deleted':
      return ShareTargetAvailability.deleted;
    case 'private':
      return ShareTargetAvailability.private;
    case 'reviewing':
      return ShareTargetAvailability.reviewing;
    case 'author_deactivated':
      return ShareTargetAvailability.authorDeactivated;
    case 'active':
      return ShareTargetAvailability.active;
    default:
      // 未识别的取值不能当可打开。「云侧新增了取值」与「本端解析错了」在这里形状相同，
      // 前者该收缩、后者该报错，两者都不该表现为放行。
      return ShareTargetAvailability.unknown;
  }
}

SharePreviewKind _parsePreviewKind(
  String raw,
  ShareTargetKind targetKind,
  ShareTargetAvailability availability,
) {
  if (availability != ShareTargetAvailability.active) {
    return SharePreviewKind.unavailable;
  }
  if (targetKind == ShareTargetKind.discussion) {
    return SharePreviewKind.discussion;
  }
  switch (raw.trim()) {
    case 'image':
      return SharePreviewKind.image;
    case 'video':
      return SharePreviewKind.video;
    default:
      return SharePreviewKind.text;
  }
}
