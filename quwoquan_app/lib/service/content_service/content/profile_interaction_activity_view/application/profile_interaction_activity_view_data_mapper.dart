import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/profile_interaction_activity_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/domain/profile_interaction_filter_keys.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ProfileInteractionActivityViewData profileInteractionActivityViewDataFromWire(
  ProfileInteractionActivityView wire,
) {
  final actorDisplayName = wire.actorDisplayName.isNotEmpty
      ? wire.actorDisplayName
      : wire.actorPersonaId;
  final displayPersonaId = wire.displayPersonaId.isNotEmpty
      ? wire.displayPersonaId
      : wire.actorPersonaId;
  final displayName = wire.displayName.isNotEmpty
      ? wire.displayName
      : (actorDisplayName.isNotEmpty ? actorDisplayName : displayPersonaId);
  final rawActorAvatarUrl = wire.actorAvatarUrl ?? '';
  final displayAvatarUrl = (wire.displayAvatarUrl ?? '').isNotEmpty
      ? wire.displayAvatarUrl!
      : rawActorAvatarUrl;
  final actorAvatarVersion = wire.actorAvatarVersion;
  final displayAvatarVersion = wire.displayAvatarVersion > 0
      ? wire.displayAvatarVersion
      : (displayAvatarUrl == rawActorAvatarUrl ? wire.actorAvatarVersion : 0);
  final previewObjectId = (wire.previewObjectId ?? '').isNotEmpty
      ? wire.previewObjectId!
      : wire.targetContentId;
  final previewMediaKind = wire.previewMediaKind.isNotEmpty
      ? wire.previewMediaKind
      : 'none';
  final filterKeys = normalizeProfileInteractionFilterKeys(wire.filterKeys);
  return ProfileInteractionActivityViewData(
    activityId: wire.activityId,
    activityType: wire.activityType.wireName,
    direction: wire.direction.wireName,
    commentKind: wire.commentKind,
    commentId: wire.commentId ?? '',
    parentCommentId: wire.parentCommentId ?? '',
    viewerReaction: wire.viewerReaction.wireName,
    actorPersonaId: wire.actorPersonaId,
    actorDisplayName: actorDisplayName,
    actorAvatarUrl: resolveAvatarImageUrl(
      rawActorAvatarUrl,
      avatarVersion: actorAvatarVersion,
    ),
    actorAvatarVersion: actorAvatarVersion,
    counterpartPersonaId: wire.counterpartPersonaId ?? '',
    counterpartDisplayName: wire.counterpartDisplayName ?? '',
    counterpartAvatarUrl: resolveAvatarImageUrl(
      wire.counterpartAvatarUrl ?? '',
    ),
    targetPersonaId: wire.targetPersonaId,
    targetContentId: wire.targetContentId,
    targetContentType: wire.targetContentType.wireName,
    targetContentSummary: wire.targetContentSummary ?? '',
    targetKind: wire.targetKind,
    targetAvailability: wire.targetAvailability,
    targetReplyCount: wire.targetReplyCount,
    displayPersonaId: displayPersonaId,
    displayName: displayName,
    displayAvatarUrl: resolveAvatarImageUrl(
      displayAvatarUrl,
      avatarVersion: displayAvatarVersion,
    ),
    displayAvatarVersion: displayAvatarVersion,
    displayUserRouteId: wire.displayUserRouteId ?? '',
    primaryText: wire.primaryText,
    contextText: wire.contextText ?? '',
    previewMediaKind: previewMediaKind,
    previewImageUrl: resolveContentMediaUrl(wire.previewImageUrl ?? ''),
    previewText: wire.previewText ?? '',
    previewUnavailable: wire.previewUnavailable,
    previewObjectId: previewObjectId,
    previewRouteId: wire.previewRouteId ?? '',
    outboundShareEventId: wire.outboundShareEventId ?? '',
    shareText: wire.shareText ?? '',
    impactPrimaryText: wire.impactPrimaryText ?? '',
    impactDeepLink: wire.impactDeepLink ?? '',
    filterKeys: filterKeys,
    createdAt: wire.createdAt,
    occurredAt: wire.occurredAt,
    seenAt: wire.seenAt,
    readAt: wire.readAt,
  );
}
