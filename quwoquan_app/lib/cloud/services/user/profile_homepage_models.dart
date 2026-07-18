import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/active_persona_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_lifecycle_guard_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_quota_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_summary_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_interaction_activity_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_social_relation_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/sub_account_profile_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_user_like_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_normalized_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_profile_stats_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_homepage_bundle_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_homepage_tab_counts_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_homepage_viewer_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
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
/// 用户主页统计计数（[UserProfileRepository.getUserStats] / 与档案合并）。
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

/// 关注关系查询视图（[UserProfileRepository.getRelationship] wire 归一化后）。
@immutable
class RelationshipViewData {
  const RelationshipViewData({
    required this.relationState,
    required this.isFollowing,
    required this.isFollowedBy,
    required this.isMutual,
  });
  final String relationState;
  final bool isFollowing;
  final bool isFollowedBy;
  final bool isMutual;
  factory RelationshipViewData.fromRelationshipNormalizedWire(
    RelationshipNormalizedWireDto w,
  ) {
    return RelationshipViewData(
      relationState: w.relationState,
      isFollowing: w.isFollowing,
      isFollowedBy: w.isFollowedBy,
      isMutual: w.isMutual,
    );
  }
}

/// 主页「获赞」列表行（[UserProfileRepository.listUserLikes]）。
@immutable
class ProfileUserLikeRowViewData {
  const ProfileUserLikeRowViewData({
    required this.postId,
    required this.title,
    required this.coverUrl,
    required this.likerNickname,
    required this.likerAvatarUrl,
    this.likerAvatarVersion = 0,
    this.likedAt,
  });
  final String postId;
  final String title;
  final String coverUrl;
  final String likerNickname;
  final String likerAvatarUrl;
  final int likerAvatarVersion;
  final DateTime? likedAt;
  factory ProfileUserLikeRowViewData.fromProfileUserLikeRowWire(
    ProfileUserLikeRowWireDto w,
  ) {
    return ProfileUserLikeRowViewData(
      postId: w.postId,
      title: w.title,
      coverUrl: resolveContentMediaUrl(w.coverUrl),
      likerNickname: w.likerNickname,
      likerAvatarUrl: resolveAvatarImageUrl(
        w.likerAvatarUrl,
        avatarVersion: w.likerAvatarVersion,
      ),
      likerAvatarVersion: w.likerAvatarVersion,
      likedAt: w.likedAt,
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
