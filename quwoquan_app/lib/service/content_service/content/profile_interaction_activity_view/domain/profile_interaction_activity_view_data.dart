import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

@immutable
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
    this.targetAvailability = 'active',
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

  factory ProfileInteractionActivityViewData.fromWire(
    ProfileInteractionActivityView w,
  ) {
    final actorDisplayName = w.actorDisplayName.isNotEmpty
        ? w.actorDisplayName
        : w.actorPersonaId;
    final displayPersonaId = w.displayPersonaId.isNotEmpty
        ? w.displayPersonaId
        : w.actorPersonaId;
    final displayName = w.displayName.isNotEmpty
        ? w.displayName
        : (actorDisplayName.isNotEmpty ? actorDisplayName : displayPersonaId);
    final rawActorAvatarUrl = w.actorAvatarUrl ?? '';
    final displayAvatarUrl = (w.displayAvatarUrl ?? '').isNotEmpty
        ? w.displayAvatarUrl!
        : rawActorAvatarUrl;
    final actorAvatarVersion = w.actorAvatarVersion;
    final displayAvatarVersion = w.displayAvatarVersion > 0
        ? w.displayAvatarVersion
        : (displayAvatarUrl == rawActorAvatarUrl ? w.actorAvatarVersion : 0);
    final primaryText = w.primaryText;
    final previewObjectId = (w.previewObjectId ?? '').isNotEmpty
        ? w.previewObjectId!
        : w.targetContentId;
    final previewMediaKind = w.previewMediaKind.isNotEmpty
        ? w.previewMediaKind
        : 'none';
    final filterKeys = <String>{
      'all',
      ...w.filterKeys.map((key) => key.trim()).where((key) => key.isNotEmpty),
    }.toList(growable: false);
    final actorAvatarUrl = resolveAvatarImageUrl(
      rawActorAvatarUrl,
      avatarVersion: actorAvatarVersion,
    );
    final resolvedDisplayAvatarUrl = resolveAvatarImageUrl(
      displayAvatarUrl,
      avatarVersion: displayAvatarVersion,
    );
    final previewImageUrl = resolveContentMediaUrl(w.previewImageUrl ?? '');
    return ProfileInteractionActivityViewData(
      activityId: w.activityId,
      activityType: w.activityType.wireName,
      direction: w.direction.wireName,
      commentKind: w.commentKind,
      commentId: w.commentId ?? '',
      parentCommentId: w.parentCommentId ?? '',
      viewerReaction: w.viewerReaction.wireName,
      actorPersonaId: w.actorPersonaId,
      actorDisplayName: actorDisplayName,
      actorAvatarUrl: actorAvatarUrl,
      actorAvatarVersion: actorAvatarVersion,
      counterpartPersonaId: w.counterpartPersonaId ?? '',
      counterpartDisplayName: w.counterpartDisplayName ?? '',
      counterpartAvatarUrl: resolveAvatarImageUrl(w.counterpartAvatarUrl ?? ''),
      targetPersonaId: w.targetPersonaId,
      targetContentId: w.targetContentId,
      targetContentType: w.targetContentType.wireName,
      targetContentSummary: w.targetContentSummary ?? '',
      targetKind: w.targetKind,
      targetAvailability: w.targetAvailability,
      targetReplyCount: w.targetReplyCount,
      displayPersonaId: displayPersonaId,
      displayName: displayName,
      displayAvatarUrl: resolvedDisplayAvatarUrl,
      displayAvatarVersion: displayAvatarVersion,
      displayUserRouteId: w.displayUserRouteId ?? '',
      primaryText: primaryText,
      contextText: w.contextText ?? '',
      previewMediaKind: previewMediaKind,
      previewImageUrl: previewImageUrl,
      previewText: w.previewText ?? '',
      previewUnavailable: w.previewUnavailable,
      previewObjectId: previewObjectId,
      previewRouteId: w.previewRouteId ?? '',
      outboundShareEventId: w.outboundShareEventId ?? '',
      shareText: w.shareText ?? '',
      impactPrimaryText: w.impactPrimaryText ?? '',
      impactDeepLink: w.impactDeepLink ?? '',
      filterKeys: filterKeys,
      createdAt: w.createdAt,
      occurredAt: w.occurredAt,
      seenAt: w.seenAt,
      readAt: w.readAt,
    );
  }
}
