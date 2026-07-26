import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/active_persona_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_lifecycle_guard_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_quota_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_summary_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_social_relation_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/sub_account_profile_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_view_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/account/user_account_stats_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_homepage_bundle_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_homepage_tab_counts_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_homepage_viewer_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
part 'profile_homepage_bundle_models.dart';
part "profile_homepage_persona_models.dart";

@immutable
class SubAccountProfileViewData {
  const SubAccountProfileViewData({
    required this.subAccountId,
    required this.ownerUserId,
    required this.subjectType,
    required this.userHandle,
    required this.username,
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
  final String subAccountId;
  final String ownerUserId;
  final String subjectType;
  final String userHandle;
  final String username;
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

  /// Wire DTO 已按 canonical 字段解码；此处仅做展示层派生。
  factory SubAccountProfileViewData.fromSubAccountProfileWire(
    SubAccountProfileWireDto w,
  ) {
    final subAccountId = w.subAccountId;
    final nickname = w.nickname;
    final displayName = w.displayName.isNotEmpty
        ? w.displayName
        : (nickname.isNotEmpty ? nickname : subAccountId);
    final userHandle = w.userHandle.isNotEmpty
        ? w.userHandle
        : (w.username.isNotEmpty ? w.username : subAccountId);
    final subjectType = w.subjectType.isNotEmpty ? w.subjectType : 'user';
    final username = w.username.isNotEmpty ? w.username : userHandle;
    // 本地选取（相册/拍照）的临时文件路径在 alpha「保存后即时回显」链路中原样保留，
    // 不经媒体解析器（否则会被当作服务端相对路径拼接成不可访问 URL）。
    final avatarUrl = isLocalFileImageSource(w.avatarUrl)
        ? w.avatarUrl
        : resolveAvatarImageUrl(w.avatarUrl, avatarVersion: w.avatarVersion);
    final backgroundUrl = isLocalFileImageSource(w.backgroundUrl)
        ? w.backgroundUrl
        : resolveContentMediaUrl(w.backgroundUrl);
    return SubAccountProfileViewData(
      subAccountId: subAccountId,
      ownerUserId: w.ownerUserId,
      subjectType: subjectType,
      userHandle: userHandle,
      username: username,
      displayName: displayName,
      nicknameCustomized: w.nicknameCustomized,
      avatarUrl: avatarUrl,
      avatarVersion: w.avatarVersion,
      backgroundUrl: backgroundUrl,
      bio: w.bio,
      identityTags: w.identityTags,
      verified: w.verified,
      followerCount: w.followerCount,
      followingCount: w.followingCount,
      postCount: w.postCount,
      circleCount: w.circleCount,
      likeCount: w.likeCount,
      profileCompleteness: w.profileCompleteness,
      profileCompletenessMissingItems: w.profileCompletenessMissingItems,
      isolationLevel: w.isolationLevel,
      profileVisibility: w.profileVisibility,
      inheritsFromOwner: w.inheritsFromOwner,
      overriddenFields: w.overriddenFields ?? const <String>[],
      updatedAt: w.updatedAt,
    );
  }

  factory SubAccountProfileViewData.fromSubAccountProfileProjection(
    SubAccountProfileProjection projection,
  ) {
    final subAccountId = projection.subAccountId;
    final displayName = projection.displayName.isNotEmpty
        ? projection.displayName
        : (projection.nickname.isNotEmpty ? projection.nickname : subAccountId);
    final userHandle = projection.userHandle.isNotEmpty
        ? projection.userHandle
        : (projection.username.isNotEmpty ? projection.username : subAccountId);
    final subjectType = projection.subjectType.isNotEmpty
        ? projection.subjectType
        : 'user';
    final username = projection.username.isNotEmpty
        ? projection.username
        : userHandle;
    final avatarUrl = isLocalFileImageSource(projection.avatarUrl)
        ? projection.avatarUrl
        : resolveAvatarImageUrl(
            projection.avatarUrl,
            avatarVersion: projection.avatarVersion,
          );
    final backgroundUrl = isLocalFileImageSource(projection.backgroundUrl)
        ? projection.backgroundUrl
        : resolveContentMediaUrl(projection.backgroundUrl);
    return SubAccountProfileViewData(
      subAccountId: subAccountId,
      ownerUserId: projection.ownerUserId,
      subjectType: subjectType,
      userHandle: userHandle,
      username: username,
      displayName: displayName,
      nicknameCustomized: projection.nicknameCustomized,
      avatarUrl: avatarUrl,
      avatarVersion: projection.avatarVersion,
      backgroundUrl: backgroundUrl,
      bio: projection.bio,
      identityTags: projection.identityTags,
      verified: projection.verified,
      followerCount: projection.followerCount,
      followingCount: projection.followingCount,
      postCount: projection.postCount,
      circleCount: projection.circleCount,
      likeCount: projection.likeCount,
      profileCompleteness: projection.profileCompleteness,
      profileCompletenessMissingItems:
          projection.profileCompletenessMissingItems,
      isolationLevel: projection.isolationLevel,
      profileVisibility: projection.profileVisibility,
      inheritsFromOwner: projection.inheritsFromOwner,
      overriddenFields: projection.overriddenFields ?? const <String>[],
      updatedAt: projection.updatedAt,
    );
  }

  SubAccountProfileViewData mergeStats(UserProfileStatsViewData stats) {
    return SubAccountProfileViewData(
      subAccountId: subAccountId,
      ownerUserId: ownerUserId,
      subjectType: subjectType,
      userHandle: userHandle,
      username: username,
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
  factory UserProfileStatsViewData.fromUserProfileStatsWire(
    UserProfileStatsWireDto w,
  ) {
    return UserProfileStatsViewData(
      followingCount: w.followingCount,
      circleCount: w.circleCount,
      followerCount: w.followerCount,
      likeCount: w.likeCount,
      postCount: w.postCount,
    );
  }

  factory UserProfileStatsViewData.fromUserProfileStatsProjection(
    UserProfileStatsProjection projection,
  ) {
    return UserProfileStatsViewData(
      followingCount: projection.followingCount,
      circleCount: projection.circleCount,
      followerCount: projection.followerCount,
      likeCount: projection.likeCount,
      postCount: projection.postCount,
    );
  }

  factory UserProfileStatsViewData.fromProfile(SubAccountProfileViewData p) {
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

  factory RelationshipViewData.fromRelationshipViewWire(
    RelationshipViewWireDto w,
  ) {
    return RelationshipViewData(
      relationState: w.relationState,
      isBlocked: w.isBlocked,
      isBlockedBy: w.isBlockedBy,
    );
  }
}

/// 关注/粉丝列表行（`listFollowing` / `listFollowers` wire → 强类型，供 UI 使用）。
@immutable
class ProfileSocialRelationRowViewData {
  const ProfileSocialRelationRowViewData({
    required this.subAccountId,
    required this.username,
    required this.userHandle,
    required this.displayName,
    required this.avatarUrl,
    this.avatarVersion = 0,
    this.profileVisibility = 'public',
    this.relationState = 'not_following',
    this.followedAt,
    this.relationshipCapability,
  });
  final String subAccountId;
  final String username;
  final String userHandle;
  final String displayName;
  final String avatarUrl;
  final int avatarVersion;
  final String profileVisibility;
  final String relationState;
  final DateTime? followedAt;
  final RelationshipCapabilityDto? relationshipCapability;
  bool get isSelf => effectiveRelationshipCapability?.isSelf ?? false;
  bool get isFollowing =>
      effectiveRelationshipCapability?.viewerFollowsTarget ?? false;
  RelationshipCapabilityDto? get effectiveRelationshipCapability {
    final capability = relationshipCapability;
    if (capability != null) {
      return capability;
    }
    return RelationshipCapabilityDto.fromFollowFlags(
      viewerId: '',
      targetId: subAccountId,
      isFollowing: relationState == 'following' || relationState == 'mutual',
      isFollowedBy: relationState == 'followed_by' || relationState == 'mutual',
      isSelf: relationState == 'self',
    );
  }

  factory ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
    ProfileSocialRelationRowWireDto w,
  ) {
    final id = w.subAccountId;
    final name = w.displayName.isNotEmpty ? w.displayName : id;
    final handle = w.userHandle.isNotEmpty
        ? w.userHandle
        : (w.username.isNotEmpty ? w.username : id);
    final username = w.username.isNotEmpty ? w.username : handle;
    return ProfileSocialRelationRowViewData(
      subAccountId: id,
      username: username,
      userHandle: handle,
      displayName: name,
      avatarUrl: resolveAvatarImageUrl(
        w.avatarUrl,
        avatarVersion: w.avatarVersion,
      ),
      avatarVersion: w.avatarVersion,
      profileVisibility: w.profileVisibility,
      relationState: w.relationState,
      followedAt: w.followedAt,
      relationshipCapability: w.relationshipCapability == null
          ? null
          : RelationshipCapabilityDto.fromMap(w.relationshipCapability!),
    );
  }

  factory ProfileSocialRelationRowViewData.fromPersonaRelationshipListItem(
    PersonaRelationshipListItem item,
  ) {
    final id = item.subAccountId;
    final name = item.displayName.isNotEmpty ? item.displayName : id;
    final handle = item.userHandle.isNotEmpty
        ? item.userHandle
        : (item.username.isNotEmpty ? item.username : id);
    final username = item.username.isNotEmpty ? item.username : handle;
    return ProfileSocialRelationRowViewData(
      subAccountId: id,
      username: username,
      userHandle: handle,
      displayName: name,
      avatarUrl: resolveAvatarImageUrl(item.avatarUrl),
      profileVisibility: item.profileVisibility,
      relationState: item.relationState,
      followedAt: item.followedAt,
      relationshipCapability: item.relationshipCapability == null
          ? null
          : RelationshipCapabilityDto.fromContract(
              item.relationshipCapability!,
            ),
    );
  }

  ProfileSocialRelationRowViewData copyWith({
    String? subAccountId,
    String? username,
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
      subAccountId: subAccountId ?? this.subAccountId,
      username: username ?? this.username,
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
