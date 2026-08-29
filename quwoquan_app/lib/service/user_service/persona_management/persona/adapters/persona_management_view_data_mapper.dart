import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Maps the canonical profile projection while keeping URL normalization at
/// the adapter boundary.
PersonaProfileViewData personaProfileViewDataFromWire(
  PersonaProfileView projection,
) {
  final personaId = projection.personaId;
  final rawAvatarUrl = projection.avatarUrl ?? '';
  final rawBackgroundUrl = projection.backgroundUrl ?? '';
  return PersonaProfileViewData(
    personaId: personaId,
    ownerUserId: '',
    subjectType: projection.subjectType.wireName,
    userHandle: projection.userHandle,
    displayName: projection.displayName.isEmpty
        ? personaId
        : projection.displayName,
    nicknameCustomized: projection.nicknameCustomized,
    avatarUrl: isLocalFileImageSource(rawAvatarUrl)
        ? rawAvatarUrl
        : resolveAvatarImageUrl(rawAvatarUrl, avatarVersion: 0),
    // 媒体交付绑定（DEC-033）：契约缺席即保持 null，不以 personaId 冒充。
    avatarAssetId: projection.avatarAssetId,
    avatarAccessMode: projection.avatarAccessMode,
    avatarVersion: 0,
    backgroundUrl: isLocalFileImageSource(rawBackgroundUrl)
        ? rawBackgroundUrl
        : resolveContentMediaUrl(rawBackgroundUrl),
    bio: projection.bio ?? '',
    identityTags: projection.identityTags ?? const <String>[],
    verified: false,
    followerCount: projection.followerCount,
    followingCount: projection.followingCount,
    postCount: projection.postCount,
    circleCount: projection.circleCount,
    likeCount: projection.likeCount,
    profileCompleteness: 100,
    profileCompletenessMissingItems: const <String>[],
    isolationLevel: projection.isolationLevel.wireName,
    profileVisibility: projection.profileVisibility.wireName,
    inheritsFromOwner: projection.inheritsFromOwner,
    overriddenFields: projection.overriddenFields ?? const <String>[],
    updatedAt: projection.updatedAt,
  );
}

/// Maps generated Persona projections into App-facing values at the adapter boundary.
ActivePersonaContextViewData activePersonaContextViewDataFromWire(
  ActivePersonaContextView projection,
) {
  final personaId = projection.personaId;
  final ownerUserId = projection.ownerUserId.isEmpty
      ? personaId
      : projection.ownerUserId;
  return ActivePersonaContextViewData(
    personaId: personaId,
    ownerUserId: ownerUserId,
    subjectType: projection.subjectType.wireName,
    displayName: projection.displayName.isEmpty
        ? personaId
        : projection.displayName,
    avatarUrl: resolveAvatarImageUrl(
      projection.avatarUrl ?? '',
      avatarVersion: projection.avatarVersion,
    ),
    avatarVersion: projection.avatarVersion,
    contextVersion: projection.contextVersion,
    personaSnapshotVersion: projection.personaSnapshotVersion,
    isPrimary: projection.isPrimary,
  );
}

PersonaManagementItemViewData personaManagementItemViewDataFromWire(
  PersonaManagementItemView projection,
) {
  final displayName = projection.displayName.isEmpty
      ? projection.personaId
      : projection.displayName;
  return PersonaManagementItemViewData(
    personaId: projection.personaId,
    displayName: displayName,
    userHandle: projection.userHandle ?? '',
    avatarUrl: resolveAvatarImageUrl(
      projection.avatarUrl ?? '',
      avatarVersion: 0,
    ),
    avatarVersion: 0,
    isolationLevel: projection.isolationLevel.wireName,
    profileVisibility: projection.profileVisibility.wireName,
    isPrimary: projection.isPrimary,
    isActive: projection.isActive,
    status: projection.status.wireName,
    retiredAt: projection.retiredAt,
    hasPublishedContent: false,
    inheritsProfileFromOwner: projection.inheritsProfileFromOwner,
    overriddenProfileFields:
        projection.overriddenProfileFields ?? const <String>[],
    lastProfileSyncAt: projection.lastProfileSyncAt,
    lastProfileSyncSource: projection.lastProfileSyncSource ?? '',
    lastActivatedAt: projection.lastActivatedAt,
    subjectType: 'persona',
  );
}

PersonaManagementSummaryViewData personaManagementSummaryViewDataFromWire(
  PersonaManagementSummaryView projection,
) {
  final items = projection.items
      .map(personaManagementItemViewDataFromWire)
      .toList(growable: false);
  return PersonaManagementSummaryViewData(
    items: items,
    quota: PersonaManagementQuotaViewData.fromWire(projection.quota),
    activeContext: activePersonaContextViewDataFromWire(
      projection.activeContext,
    ),
  );
}
