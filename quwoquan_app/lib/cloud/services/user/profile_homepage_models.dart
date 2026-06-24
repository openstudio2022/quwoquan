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

  /// Wire DTO 解码在 [SubAccountProfileWireDto]（含 `skip_empty_string_aliases`）；此处仅做展示层回退。
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

  /// 仅用于 Repository / 契约解码边界；页面与业务层请使用 [fromProfileSubjectWire]。
  @Deprecated('Use fromSubAccountProfileWire(SubAccountProfileWireDto)')
  factory SubAccountProfileViewData.fromMap(Map<String, dynamic> map) {
    return SubAccountProfileViewData.fromSubAccountProfileWire(
      SubAccountProfileWireDto.fromMap(map),
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

  @Deprecated('Use fromUserProfileStatsWire(UserProfileStatsWireDto)')
  factory UserProfileStatsViewData.fromMap(Map<String, dynamic> m) {
    return UserProfileStatsViewData.fromUserProfileStatsWire(
      UserProfileStatsWireDto.fromMap(m),
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

  @Deprecated(
    'Use fromRelationshipNormalizedWire(RelationshipNormalizedWireDto)',
  )
  factory RelationshipViewData.fromNormalizedMap(Map<String, dynamic> m) {
    return RelationshipViewData.fromRelationshipNormalizedWire(
      RelationshipNormalizedWireDto.fromMap(m),
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

  @Deprecated('Use fromProfileUserLikeRowWire(ProfileUserLikeRowWireDto)')
  factory ProfileUserLikeRowViewData.fromMap(Map<String, dynamic> m) {
    return ProfileUserLikeRowViewData.fromProfileUserLikeRowWire(
      ProfileUserLikeRowWireDto.fromMap(m),
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

  @Deprecated(
    'Use fromProfileSocialRelationRowWire(ProfileSocialRelationRowWireDto)',
  )
  factory ProfileSocialRelationRowViewData.fromMap(Map<String, dynamic> map) {
    return ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
      ProfileSocialRelationRowWireDto.fromMap(map),
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

/// 清单用户档案展示面别名：端侧统一 [SubAccountProfileViewData]（与 codegen UserProfileDto wire 对齐由 Repository 负责）。
typedef UserProfileViewData = SubAccountProfileViewData;

/// 清单 PersonaDto：端侧管理行统一 [PersonaManagementItemViewData]。
typedef PersonaDtoSurface = PersonaManagementItemViewData;

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
    required this.actorSubAccountId,
    required this.actorDisplayName,
    required this.actorAvatarUrl,
    this.actorAvatarVersion = 0,
    required this.targetSubAccountId,
    required this.targetContentId,
    required this.targetContentType,
    required this.targetContentSummary,
    required this.displaySubAccountId,
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
    required this.filterKeys,
    required this.createdAt,
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
  final String actorSubAccountId;
  final String actorDisplayName;
  final String actorAvatarUrl;
  final int actorAvatarVersion;
  final String targetSubAccountId;
  final String targetContentId;
  final String targetContentType;
  final String targetContentSummary;
  final String displaySubAccountId;
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
  final List<String> filterKeys;
  final DateTime? createdAt;

  factory ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
    ProfileInteractionActivityWireDto w,
  ) {
    var activityId = w.activityId;
    if (activityId.isEmpty) {
      final prefix = w.activityType.isEmpty ? 'activity' : w.activityType;
      activityId = '$prefix:${w.actorSubAccountId}';
    }
    final actorDisplayName = w.actorDisplayName.isNotEmpty
        ? w.actorDisplayName
        : w.actorSubAccountId;
    final displaySubAccountId = w.displaySubAccountId.isNotEmpty
        ? w.displaySubAccountId
        : w.actorSubAccountId;
    final displayName = w.displayName.isNotEmpty
        ? w.displayName
        : (actorDisplayName.isNotEmpty
              ? actorDisplayName
              : displaySubAccountId);
    final displayAvatarUrl = w.displayAvatarUrl.isNotEmpty
        ? w.displayAvatarUrl
        : w.actorAvatarUrl;
    final actorAvatarVersion = w.actorAvatarVersion;
    final displayAvatarVersion = w.displayAvatarVersion > 0
        ? w.displayAvatarVersion
        : (displayAvatarUrl == w.actorAvatarUrl ? w.actorAvatarVersion : 0);
    final primaryText = w.primaryText;
    final previewObjectId = w.previewObjectId.isNotEmpty
        ? w.previewObjectId
        : w.targetContentId;
    final previewMediaKind = w.previewMediaKind.isNotEmpty
        ? w.previewMediaKind
        : 'none';
    final filterKeys = <String>{
      'all',
      ...w.filterKeys.map((key) => key.trim()).where((key) => key.isNotEmpty),
    }.toList(growable: false);
    final actorAvatarUrl = resolveAvatarImageUrl(
      w.actorAvatarUrl,
      avatarVersion: actorAvatarVersion,
    );
    final resolvedDisplayAvatarUrl = resolveAvatarImageUrl(
      displayAvatarUrl,
      avatarVersion: displayAvatarVersion,
    );
    final previewImageUrl = resolveContentMediaUrl(w.previewImageUrl);
    return ProfileInteractionActivityViewData(
      activityId: activityId,
      activityType: w.activityType,
      direction: w.direction,
      commentKind: w.commentKind,
      commentId: w.commentId,
      parentCommentId: w.parentCommentId,
      viewerReaction: w.viewerReaction,
      actorSubAccountId: w.actorSubAccountId,
      actorDisplayName: actorDisplayName,
      actorAvatarUrl: actorAvatarUrl,
      actorAvatarVersion: actorAvatarVersion,
      targetSubAccountId: w.targetSubAccountId,
      targetContentId: w.targetContentId,
      targetContentType: w.targetContentType,
      targetContentSummary: w.targetContentSummary,
      displaySubAccountId: displaySubAccountId,
      displayName: displayName,
      displayAvatarUrl: resolvedDisplayAvatarUrl,
      displayAvatarVersion: displayAvatarVersion,
      displayUserRouteId: w.displayUserRouteId,
      primaryText: primaryText,
      contextText: w.contextText,
      previewMediaKind: previewMediaKind,
      previewImageUrl: previewImageUrl,
      previewText: w.previewText,
      previewUnavailable: w.previewUnavailable,
      previewObjectId: previewObjectId,
      previewRouteId: w.previewRouteId,
      filterKeys: filterKeys,
      createdAt: w.createdAt,
    );
  }

  @Deprecated(
    'Use fromProfileInteractionActivityWire(ProfileInteractionActivityWireDto)',
  )
  factory ProfileInteractionActivityViewData.fromMap(Map<String, dynamic> map) {
    return ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
      ProfileInteractionActivityWireDto.fromMap(map),
    );
  }
}

@immutable
class ActivePersonaContextViewData {
  const ActivePersonaContextViewData({
    required this.subAccountId,
    required this.ownerUserId,
    required this.subjectType,
    required this.displayName,
    required this.avatarUrl,
    this.avatarVersion = 0,
    required this.personaContextVersion,
    this.isPrimary = false,
    this.isFallback = false,
  });

  final String subAccountId;
  final String ownerUserId;
  final String subjectType;
  final String displayName;
  final String avatarUrl;
  final int avatarVersion;
  final String personaContextVersion;
  final bool isPrimary;
  final bool isFallback;

  String get contextVersion => personaContextVersion;

  String get personaSnapshotVersion => '1';

  bool get hasSubAccount => subAccountId.isNotEmpty;

  Map<String, Object?> toTypedEnvelope({
    String sourceSurfaceId = '',
    bool explicitOverride = false,
  }) {
    return <String, Object?>{
      'subAccountId': subAccountId,
      if (contextVersion.isNotEmpty) 'contextVersion': contextVersion,
      if (personaContextVersion.isNotEmpty)
        'personaContextVersion': personaContextVersion,
      'personaSnapshotVersion': personaSnapshotVersion,
      if (sourceSurfaceId.trim().isNotEmpty)
        'sourceSurfaceId': sourceSurfaceId.trim(),
      'explicitOverride': explicitOverride,
    };
  }

  factory ActivePersonaContextViewData.fromActivePersonaContextWire(
    ActivePersonaContextWireDto w,
  ) {
    final subAccountId = w.subAccountId;
    var ownerUserId = w.ownerUserId;
    if (ownerUserId.isEmpty) {
      ownerUserId = subAccountId;
    }
    final displayName = w.displayName.isNotEmpty ? w.displayName : subAccountId;
    final subjectType = w.subjectType.isNotEmpty ? w.subjectType : 'subAccount';
    return ActivePersonaContextViewData(
      subAccountId: subAccountId,
      ownerUserId: ownerUserId,
      subjectType: subjectType,
      displayName: displayName,
      avatarUrl: resolveAvatarImageUrl(
        w.avatarUrl,
        avatarVersion: w.avatarVersion,
      ),
      avatarVersion: w.avatarVersion,
      personaContextVersion: w.personaContextVersion,
      isPrimary: w.isPrimary,
    );
  }

  @Deprecated('Use fromActivePersonaContextWire(ActivePersonaContextWireDto)')
  factory ActivePersonaContextViewData.fromMap(Map<String, dynamic> map) {
    return ActivePersonaContextViewData.fromActivePersonaContextWire(
      ActivePersonaContextWireDto.fromMap(map),
    );
  }

  factory ActivePersonaContextViewData.fallback({
    required String subAccountId,
    required String ownerUserId,
    required String displayName,
    required String avatarUrl,
    int avatarVersion = 0,
    String subjectType = 'subAccount',
    String personaContextVersion = '',
  }) {
    return ActivePersonaContextViewData(
      subAccountId: subAccountId,
      ownerUserId: ownerUserId,
      subjectType: subjectType,
      displayName: displayName,
      avatarUrl: avatarUrl,
      avatarVersion: avatarVersion,
      personaContextVersion: personaContextVersion,
      isFallback: true,
    );
  }
}

@immutable
class PersonaManagementItemViewData {
  const PersonaManagementItemViewData({
    required this.subAccountId,
    required this.displayName,
    required this.userHandle,
    required this.phone,
    required this.email,
    required this.avatarUrl,
    this.avatarVersion = 0,
    required this.isolationLevel,
    required this.profileVisibility,
    required this.isPrimary,
    required this.isActive,
    required this.status,
    required this.retiredAt,
    required this.hasAttributedHistory,
    required this.hasPublishedContent,
    required this.inheritsProfileFromOwner,
    required this.overriddenProfileFields,
    required this.lastProfileSyncAt,
    required this.lastProfileSyncSource,
    required this.lastActivatedAt,
    required this.subjectType,
  });

  final String subAccountId;
  final String displayName;
  final String userHandle;
  final String phone;
  final String email;
  final String avatarUrl;
  final int avatarVersion;
  final String isolationLevel;
  final String profileVisibility;
  final bool isPrimary;
  final bool isActive;
  final String status;
  final DateTime? retiredAt;
  final bool hasAttributedHistory;
  final bool hasPublishedContent;
  final bool inheritsProfileFromOwner;
  final List<String> overriddenProfileFields;
  final DateTime? lastProfileSyncAt;
  final String lastProfileSyncSource;
  final DateTime? lastActivatedAt;
  final String subjectType;

  bool get hasContactInfo => phone.isNotEmpty || email.isNotEmpty;
  bool get isRetired => status == 'retired';

  /// 纠正 wire 默认 `subjectType: persona`：无 `subAccountId` 时视为 user 主行。
  factory PersonaManagementItemViewData.fromPersonaManagementItemWire(
    PersonaManagementItemWireDto w,
  ) {
    final displayName = w.displayName.isNotEmpty
        ? w.displayName
        : w.subAccountId;
    final subjectType = w.subAccountId.isEmpty
        ? (w.subjectType.isEmpty || w.subjectType == 'persona'
              ? 'user'
              : w.subjectType)
        : (w.subjectType.isNotEmpty ? w.subjectType : 'persona');
    return PersonaManagementItemViewData(
      subAccountId: w.subAccountId,
      displayName: displayName,
      userHandle: w.userHandle,
      phone: w.phone,
      email: w.email,
      avatarUrl: resolveAvatarImageUrl(
        w.avatarUrl,
        avatarVersion: w.avatarVersion,
      ),
      avatarVersion: w.avatarVersion,
      isolationLevel: w.isolationLevel,
      profileVisibility: w.profileVisibility,
      isPrimary: w.isPrimary,
      isActive: w.isActive,
      status: w.status,
      retiredAt: w.retiredAt,
      hasAttributedHistory: w.hasAttributedHistory,
      hasPublishedContent: w.hasPublishedContent,
      inheritsProfileFromOwner: w.inheritsProfileFromOwner,
      overriddenProfileFields: w.overriddenProfileFields,
      lastProfileSyncAt: w.lastProfileSyncAt,
      lastProfileSyncSource: w.lastProfileSyncSource,
      lastActivatedAt: w.lastActivatedAt,
      subjectType: subjectType,
    );
  }

  @Deprecated('Use fromPersonaManagementItemWire(PersonaManagementItemWireDto)')
  factory PersonaManagementItemViewData.fromMap(Map<String, dynamic> map) {
    return PersonaManagementItemViewData.fromPersonaManagementItemWire(
      PersonaManagementItemWireDto.fromMap(map),
    );
  }
}

@immutable
class PersonaSyncSuggestionViewData {
  const PersonaSyncSuggestionViewData({
    required this.sourcePersonaId,
    required this.sourceDisplayName,
    required this.targetPersonaIds,
    required this.targetDisplayNames,
    required this.fieldKeys,
  });

  final String sourcePersonaId;
  final String sourceDisplayName;
  final List<String> targetPersonaIds;
  final List<String> targetDisplayNames;
  final List<String> fieldKeys;

  bool get canApply => targetPersonaIds.isNotEmpty && fieldKeys.isNotEmpty;
}

@immutable
class PersonaManagementQuotaViewData {
  const PersonaManagementQuotaViewData({
    required this.maxSubAccounts,
    required this.usedSubAccounts,
  });

  final int maxSubAccounts;
  final int usedSubAccounts;

  int get remainingSlots {
    final remaining = maxSubAccounts - usedSubAccounts;
    return remaining < 0 ? 0 : remaining;
  }

  bool get quotaReached => usedSubAccounts >= maxSubAccounts;

  factory PersonaManagementQuotaViewData.fromPersonaManagementQuotaWire(
    PersonaManagementQuotaWireDto w,
  ) {
    var max = w.maxSubAccounts;
    if (max <= 0) max = 5;
    return PersonaManagementQuotaViewData(
      maxSubAccounts: max,
      usedSubAccounts: w.usedSubAccounts,
    );
  }

  @Deprecated(
    'Use fromPersonaManagementQuotaWire(PersonaManagementQuotaWireDto)',
  )
  factory PersonaManagementQuotaViewData.fromMap(Map<String, dynamic> map) {
    return PersonaManagementQuotaViewData.fromPersonaManagementQuotaWire(
      PersonaManagementQuotaWireDto.fromMap(map),
    );
  }
}

@immutable
class PersonaLifecycleGuardViewData {
  const PersonaLifecycleGuardViewData({
    required this.subAccountId,
    required this.canDelete,
    required this.canRetire,
    required this.requiredAction,
    required this.reasonCode,
    required this.message,
  });

  final String subAccountId;
  final bool canDelete;
  final bool canRetire;
  final String requiredAction;
  final String reasonCode;
  final String message;

  factory PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
    PersonaLifecycleGuardWireDto w,
  ) {
    return PersonaLifecycleGuardViewData(
      subAccountId: w.subAccountId,
      canDelete: w.canDelete,
      canRetire: w.canRetire,
      requiredAction: w.requiredAction,
      reasonCode: w.reasonCode,
      message: w.message,
    );
  }

  @Deprecated('Use fromPersonaLifecycleGuardWire(PersonaLifecycleGuardWireDto)')
  factory PersonaLifecycleGuardViewData.fromMap(Map<String, dynamic> map) {
    return PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
      PersonaLifecycleGuardWireDto.fromMap(map),
    );
  }
}

@immutable
class PersonaManagementSummaryViewData {
  const PersonaManagementSummaryViewData({
    required this.items,
    required this.quota,
    this.activeContext,
  });

  final List<PersonaManagementItemViewData> items;
  final PersonaManagementQuotaViewData quota;
  final ActivePersonaContextViewData? activeContext;

  factory PersonaManagementSummaryViewData.fromPersonaManagementSummaryWire(
    PersonaManagementSummaryWireDto w,
  ) {
    final items = w.items
        .map(
          (m) => PersonaManagementItemViewData.fromPersonaManagementItemWire(
            PersonaManagementItemWireDto.fromMap(m),
          ),
        )
        .toList(growable: false);
    final quotaMap =
        w.quota ??
        <String, dynamic>{'usedSubAccounts': items.length, 'maxSubAccounts': 5};
    final activeMap = w.activeContext;
    return PersonaManagementSummaryViewData(
      items: items,
      quota: PersonaManagementQuotaViewData.fromPersonaManagementQuotaWire(
        PersonaManagementQuotaWireDto.fromMap(quotaMap),
      ),
      activeContext: activeMap == null
          ? null
          : ActivePersonaContextViewData.fromActivePersonaContextWire(
              ActivePersonaContextWireDto.fromMap(activeMap),
            ),
    );
  }

  @Deprecated(
    'Use fromPersonaManagementSummaryWire(PersonaManagementSummaryWireDto)',
  )
  factory PersonaManagementSummaryViewData.fromMap(Map<String, dynamic> map) {
    return PersonaManagementSummaryViewData.fromPersonaManagementSummaryWire(
      PersonaManagementSummaryWireDto.fromMap(map),
    );
  }
}

// ─── 主页 Tab 行模型（与 mock 数据字段对齐；待 service.yaml codegen 收敛）────────

/// 作品集条目。
@immutable
class UserWorkItem {
  const UserWorkItem({
    required this.id,
    required this.type,
    required this.title,
    required this.coverUrl,
    required this.likeCount,
    required this.date,
    required this.desc,
  });

  final String id;
  final String type;
  final String title;
  final String coverUrl;
  final int likeCount;
  final String date;
  final String desc;
}

/// 生活记录条目。字段与后端契约 `user/user_life_item`（UserLifeItemDto）一一对齐。
/// category 为 LifeItemCategory 枚举值（footprint/soul/taste/private），子页过滤直接比对。
@immutable
class UserLifeItem {
  const UserLifeItem({
    required this.id,
    required this.category,
    required this.title,
    this.subtitle = '',
    this.imageUrl = '',
    this.refId = '',
  });

  final String id;

  /// LifeItemCategory 枚举值：footprint=足迹 / soul=书影音 / taste=味蕾 / private=爱物。
  final String category;

  /// 记录主文案。
  final String title;

  /// 记录副标题/描述。
  final String subtitle;

  /// 封面图（绝对 URL 或对象键）。
  final String imageUrl;

  /// 关联内容引用（作品/圈子等）。
  final String refId;
}

// ─── 主页首屏聚合（homepage-bundle，锁定决策 #1：一次聚合 + 交集/影响力并发补充）──
