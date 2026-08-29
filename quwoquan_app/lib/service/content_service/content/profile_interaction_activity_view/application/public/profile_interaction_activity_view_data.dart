import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show MediaDeliveryAccessMode;

class ProfileInteractionActivityViewData {
  const ProfileInteractionActivityViewData({
    required this.activityId,
    required this.activityType,
    required this.direction,
    required this.commentKind,
    required this.commentId,
    required this.parentCommentId,
    this.viewerReaction = 'none',
    required this.actorPersonaId,
    required this.actorDisplayName,
    required this.actorAvatarUrl,
    this.actorAvatarVersion = 0,
    this.counterpartPersonaId = '',
    this.counterpartDisplayName = '',
    this.counterpartAvatarUrl = '',
    required this.targetPersonaId,
    required this.targetContentId,
    required this.targetContentType,
    required this.targetContentSummary,
    this.targetKind = 'record',
    // 契约声明 NOT_NULL，wire 必然带这个取值；给默认值等于替云侧决定可用性。
    required this.targetAvailability,
    this.targetReplyCount = 0,
    required this.displayPersonaId,
    required this.displayName,
    required this.displayAvatarUrl,
    this.displayAvatarVersion = 0,
    required this.displayUserRouteId,
    required this.primaryText,
    required this.contextText,
    required this.previewMediaKind,
    required this.previewImageUrl,
    this.previewImageAssetId,
    this.previewImageAccessMode,
    required this.previewText,
    required this.previewUnavailable,
    required this.previewObjectId,
    required this.previewRouteId,
    this.outboundShareEventId = '',
    this.shareText = '',
    this.impactPrimaryText = '',
    this.impactDeepLink = '',
    required this.filterKeys,
    required this.createdAt,
    this.occurredAt,
    this.seenAt,
    this.readAt,
  });

  final String activityId;
  final String activityType;
  final String direction;
  final String commentKind;
  final String commentId;
  final String parentCommentId;

  /// 浏览者（当前登录用户）对该条评论/回复的反应：none/like/dislike。
  /// 用于「我的主页·互动」内联赞↔已赞态展示。
  final String viewerReaction;
  final String actorPersonaId;
  final String actorDisplayName;
  final String actorAvatarUrl;
  final int actorAvatarVersion;
  final String counterpartPersonaId;
  final String counterpartDisplayName;
  final String counterpartAvatarUrl;
  final String targetPersonaId;
  final String targetContentId;
  final String targetContentType;
  final String targetContentSummary;
  final String targetKind;
  final String targetAvailability;
  final int targetReplyCount;
  final String displayPersonaId;
  final String displayName;
  final String displayAvatarUrl;
  final int displayAvatarVersion;
  final String displayUserRouteId;
  final String primaryText;
  final String contextText;
  final String previewMediaKind;
  final String previewImageUrl;

  /// 预览图的配对资产标识与交付访问模式（DEC-033）；research 相位的
  /// previewImageUrl 是相对私有 CAS 引用，按 assetId 换短签。
  final String? previewImageAssetId;
  final MediaDeliveryAccessMode? previewImageAccessMode;
  final String previewText;
  final bool previewUnavailable;
  final String previewObjectId;
  final String previewRouteId;

  /// 不可变站外分享事实的事件标识，仅用于追踪，不能作为可导航内容。
  final String outboundShareEventId;
  final String shareText;
  final String impactPrimaryText;
  final String impactDeepLink;
  final List<String> filterKeys;
  final DateTime? createdAt;
  final DateTime? occurredAt;
  final DateTime? seenAt;
  final DateTime? readAt;
}
