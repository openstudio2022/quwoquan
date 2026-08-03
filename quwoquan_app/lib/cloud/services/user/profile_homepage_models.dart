import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
part 'profile_homepage_bundle_models.dart';
part "profile_homepage_persona_models.dart";

@immutable
class PersonaProfileViewData {
  const PersonaProfileViewData({
    required this.personaId,
    required this.ownerUserId,
    required this.subjectType,
    required this.userHandle,
    required this.displayName,
    this.nicknameCustomized = false,
    required this.avatarUrl,
    this.avatarVersion = 0,
    required this.backgroundUrl,
    required this.bio,
    this.identityTags = const <String>[],
    this.verified = false,
    required this.followerCount,
    required this.followingCount,
    required this.postCount,
    required this.circleCount,
    required this.likeCount,
    this.profileCompleteness = 100,
    this.profileCompletenessMissingItems = const <String>[],
    required this.isolationLevel,
    required this.profileVisibility,
    required this.inheritsFromOwner,
    required this.overriddenFields,
    required this.updatedAt,
  });
  final String personaId;
  final String ownerUserId;
  final String subjectType;
  final String userHandle;
  final String displayName;

  /// 昵称是否被用户自定义过。false = 仍是云侧默认昵称（我的主页展示编辑画笔，
  /// 引导用户改名）；true = 用户已改名，主页不再展示编辑画笔。
  final bool nicknameCustomized;
  final String avatarUrl;
  final int avatarVersion;
  final String backgroundUrl;
  final String bio;

  /// 主页单行身份标签（云侧 identityTags，端以 · 分隔单行展示）。
  final List<String> identityTags;

  /// 认证标识（蓝勾）。云侧 verified 直出，端只读展示，缺省 false。
  final bool verified;
  final int followerCount;
  final int followingCount;
  final int postCount;
  final int circleCount;
  final int likeCount;

  /// 主页完善度（0-100），用于「完善主页」提示。默认 100 表示不展示提示。
  final int profileCompleteness;

  /// 主页待补全项（avatar / tags / circles / entities 等开放字符串）。
  final List<String> profileCompletenessMissingItems;
  final String isolationLevel;
  final String profileVisibility;
  final bool inheritsFromOwner;
  final List<String> overriddenFields;
  final DateTime? updatedAt;

  /// canonical generated wire 到 App 展示模型的唯一映射。
  factory PersonaProfileViewData.fromWire(
    PersonaProfileView projection,
  ) {
    final personaId = projection.personaId;
    final displayName = projection.displayName.isNotEmpty
        ? projection.displayName
        : personaId;
    final userHandle = projection.userHandle;
    final subjectType = projection.subjectType.wireName;
    final rawAvatarUrl = projection.avatarUrl ?? '';
    final rawBackgroundUrl = projection.backgroundUrl ?? '';
    final avatarUrl = isLocalFileImageSource(rawAvatarUrl)
        ? rawAvatarUrl
        : resolveAvatarImageUrl(
            rawAvatarUrl,
            avatarVersion: 0,
          );
    final backgroundUrl = isLocalFileImageSource(rawBackgroundUrl)
        ? rawBackgroundUrl
        : resolveContentMediaUrl(rawBackgroundUrl);
    return PersonaProfileViewData(
      personaId: personaId,
      ownerUserId: '',
      subjectType: subjectType,
      userHandle: userHandle,
      displayName: displayName,
      nicknameCustomized: projection.nicknameCustomized,
      avatarUrl: avatarUrl,
      avatarVersion: 0,
      backgroundUrl: backgroundUrl,
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

  PersonaProfileViewData mergeStats(UserProfileStatsViewData stats) {
    return PersonaProfileViewData(
      personaId: personaId,
      ownerUserId: ownerUserId,
      subjectType: subjectType,
      userHandle: userHandle,
      displayName: displayName,
      nicknameCustomized: nicknameCustomized,
      avatarUrl: avatarUrl,
      avatarVersion: avatarVersion,
      backgroundUrl: backgroundUrl,
      bio: bio,
      identityTags: identityTags,
      verified: verified,
      followerCount: stats.followerCount,
      followingCount: stats.followingCount,
      postCount: stats.postCount,
      circleCount: stats.circleCount,
      likeCount: stats.likeCount,
      profileCompleteness: profileCompleteness,
      profileCompletenessMissingItems: profileCompletenessMissingItems,
      isolationLevel: isolationLevel,
      profileVisibility: profileVisibility,
      inheritsFromOwner: inheritsFromOwner,
      overriddenFields: overriddenFields,
      updatedAt: updatedAt,
    );
  }
}

/// 用户主页统计计数（`ProfileQuery.getUserStats` / 与档案合并）。
@immutable
class UserProfileStatsViewData {
  const UserProfileStatsViewData({
    required this.followingCount,
    required this.circleCount,
    required this.followerCount,
    required this.likeCount,
    required this.postCount,
  });
  final int followingCount;
  final int circleCount;
  final int followerCount;
  final int likeCount;
  final int postCount;
  factory UserProfileStatsViewData.fromWire(
    UserProfileStatsWire projection,
  ) {
    return UserProfileStatsViewData(
      followingCount: projection.followingCount,
      circleCount: projection.circleCount,
      followerCount: projection.followerCount,
      likeCount: projection.likeCount,
      postCount: projection.postCount,
    );
  }

  factory UserProfileStatsViewData.fromProfile(PersonaProfileViewData p) {
    return UserProfileStatsViewData(
      followingCount: p.followingCount,
      circleCount: p.circleCount,
      followerCount: p.followerCount,
      likeCount: p.likeCount,
      postCount: p.postCount,
    );
  }
}

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
  final RelationshipCapabilityDto? relationshipCapability;
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
      avatarUrl: resolveAvatarImageUrl(
        w.avatarUrl ?? '',
        avatarVersion: 0,
      ),
      avatarVersion: 0,
      profileVisibility: w.profileVisibility.wireName,
      relationState: w.relationState.wireName,
      followedAt: w.followedAt,
      relationshipCapability: w.relationshipCapability == null
          ? null
          : RelationshipCapabilityDto.fromWire(w.relationshipCapability!),
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
          : RelationshipCapabilityDto.fromWire(
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
    RelationshipCapabilityDto? relationshipCapability,
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
