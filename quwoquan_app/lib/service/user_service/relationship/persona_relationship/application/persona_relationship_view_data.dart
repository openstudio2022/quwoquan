import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 关注关系查询视图（由 PersonaRelationship 对象级 Query 提供）。
///
/// 直接消费 RelationshipView wire（relationState + block 双向位）；
/// isFollowing / isFollowedBy / isMutual 是端侧从 relationState 派生的
/// view model 便捷位，不再期待 wire 下发。
@immutable
class RelationshipViewData {
  const RelationshipViewData({
    required this.relationState,
    this.isBlocked = false,
    this.isBlockedBy = false,
  });
  final String relationState;
  final bool isBlocked;
  final bool isBlockedBy;

  bool get isMutual => relationState == 'mutual';
  bool get isFollowing => relationState == 'following' || isMutual;
  bool get isFollowedBy => relationState == 'followed_by' || isMutual;
}

/// 关注/粉丝列表行（`listFollowing` / `listFollowers` wire → 强类型，供 UI 使用）。
@immutable
class ProfileSocialRelationRowViewData {
  const ProfileSocialRelationRowViewData({
    required this.personaId,
    required this.userHandle,
    required this.displayName,
    required this.avatarUrl,
    this.avatarVersion = 0,
    this.profileVisibility = 'public',
    this.relationState = 'not_following',
    this.followedAt,
    this.relationshipCapability,
  });
  final String personaId;
  final String userHandle;
  final String displayName;
  final String avatarUrl;
  final int avatarVersion;
  final String profileVisibility;
  final String relationState;
  final DateTime? followedAt;
  final RelationshipCapabilityViewData? relationshipCapability;
  bool get isSelf => relationshipCapability?.isSelf ?? false;
  bool get isFollowing => relationshipCapability?.viewerFollowsTarget ?? false;

  factory ProfileSocialRelationRowViewData.fromFollowingWire(
    FollowingListItemView w,
  ) {
    final id = w.personaId;
    final name = w.displayName.isNotEmpty ? w.displayName : id;
    return ProfileSocialRelationRowViewData(
      personaId: id,
      userHandle: w.userHandle,
      displayName: name,
      avatarUrl: resolveAvatarImageUrl(w.avatarUrl ?? '', avatarVersion: 0),
      avatarVersion: 0,
      profileVisibility: w.profileVisibility.wireName,
      relationState: w.relationState.wireName,
      followedAt: w.followedAt,
      relationshipCapability: w.relationshipCapability == null
          ? null
          : RelationshipCapabilityViewData.fromWire(w.relationshipCapability!),
    );
  }

  factory ProfileSocialRelationRowViewData.fromFollowerWire(
    FollowerListItemView item,
  ) {
    final id = item.personaId;
    final name = item.displayName.isNotEmpty ? item.displayName : id;
    return ProfileSocialRelationRowViewData(
      personaId: id,
      userHandle: item.userHandle,
      displayName: name,
      avatarUrl: resolveAvatarImageUrl(item.avatarUrl ?? ''),
      profileVisibility: item.profileVisibility.wireName,
      relationState: item.relationState.wireName,
      followedAt: item.followedAt,
      relationshipCapability: item.relationshipCapability == null
          ? null
          : RelationshipCapabilityViewData.fromWire(
              item.relationshipCapability!,
            ),
    );
  }

  ProfileSocialRelationRowViewData copyWith({
    String? personaId,
    String? userHandle,
    String? displayName,
    String? avatarUrl,
    int? avatarVersion,
    String? profileVisibility,
    String? relationState,
    DateTime? followedAt,
    RelationshipCapabilityViewData? relationshipCapability,
  }) {
    return ProfileSocialRelationRowViewData(
      personaId: personaId ?? this.personaId,
      userHandle: userHandle ?? this.userHandle,
      displayName: displayName ?? this.displayName,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      avatarVersion: avatarVersion ?? this.avatarVersion,
      profileVisibility: profileVisibility ?? this.profileVisibility,
      relationState: relationState ?? this.relationState,
      followedAt: followedAt ?? this.followedAt,
      relationshipCapability:
          relationshipCapability ?? this.relationshipCapability,
    );
  }
}
