import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/active_persona_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_lifecycle_guard_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_quota_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_summary_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_interaction_activity_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_social_relation_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_subject_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_user_like_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_normalized_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_profile_stats_wire_dto.g.dart';

@immutable
class ProfileSubjectViewData {
  const ProfileSubjectViewData({
    required this.profileSubjectId,
    required this.ownerUserId,
    required this.subjectType,
    required this.subAccountId,
    required this.username,
    required this.displayName,
    required this.avatarUrl,
    required this.backgroundUrl,
    required this.bio,
    required this.followerCount,
    required this.followingCount,
    required this.postCount,
    required this.circleCount,
    required this.likeCount,
    required this.profileVisibility,
    required this.inheritsFromOwner,
    required this.overriddenFields,
    required this.updatedAt,
  });

  final String profileSubjectId;
  final String ownerUserId;
  final String subjectType;
  final String subAccountId;
  final String username;
  final String displayName;
  final String avatarUrl;
  final String backgroundUrl;
  final String bio;
  final int followerCount;
  final int followingCount;
  final int postCount;
  final int circleCount;
  final int likeCount;
  final String profileVisibility;
  final bool inheritsFromOwner;
  final List<String> overriddenFields;
  final DateTime? updatedAt;

  /// Wire DTO 解码在 [ProfileSubjectWireDto]（含 `skip_empty_string_aliases`）；此处仅做展示层回退。
  factory ProfileSubjectViewData.fromProfileSubjectWire(
    ProfileSubjectWireDto w,
  ) {
    final subjectId = w.profileSubjectId;
    final nickname = w.nickname;
    final displayName = w.displayName.isNotEmpty
        ? w.displayName
        : (nickname.isNotEmpty ? nickname : subjectId);
    final subAccountId = w.subAccountId;
    final subjectType = w.subjectType.isNotEmpty
        ? w.subjectType
        : (subAccountId.isNotEmpty ? 'sub_account' : 'owner');
    final username = w.username.isNotEmpty
        ? w.username
        : (nickname.isNotEmpty ? nickname : subjectId);
    return ProfileSubjectViewData(
      profileSubjectId: subjectId,
      ownerUserId: w.ownerUserId,
      subjectType: subjectType,
      subAccountId: subAccountId,
      username: username,
      displayName: displayName,
      avatarUrl: w.avatarUrl,
      backgroundUrl: w.backgroundUrl,
      bio: w.bio,
      followerCount: w.followerCount,
      followingCount: w.followingCount,
      postCount: w.postCount,
      circleCount: w.circleCount,
      likeCount: w.likeCount,
      profileVisibility: w.profileVisibility,
      inheritsFromOwner: w.inheritsFromOwner,
      overriddenFields: w.overriddenFields ?? const <String>[],
      updatedAt: w.updatedAt,
    );
  }

  /// 仅用于 Repository / 契约解码边界；页面与业务层请使用 [fromProfileSubjectWire]。
  @Deprecated('Use fromProfileSubjectWire(ProfileSubjectWireDto)')
  factory ProfileSubjectViewData.fromMap(Map<String, dynamic> map) {
    return ProfileSubjectViewData.fromProfileSubjectWire(
      ProfileSubjectWireDto.fromMap(map),
    );
  }

  ProfileSubjectViewData mergeStats(UserProfileStatsViewData stats) {
    return ProfileSubjectViewData(
      profileSubjectId: profileSubjectId,
      ownerUserId: ownerUserId,
      subjectType: subjectType,
      subAccountId: subAccountId,
      username: username,
      displayName: displayName,
      avatarUrl: avatarUrl,
      backgroundUrl: backgroundUrl,
      bio: bio,
      followerCount: stats.followerCount,
      followingCount: stats.followingCount,
      postCount: stats.postCount,
      circleCount: stats.circleCount,
      likeCount: stats.likeCount,
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

  factory UserProfileStatsViewData.fromProfile(ProfileSubjectViewData p) {
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
    this.likedAt,
  });

  final String postId;
  final String title;
  final String coverUrl;
  final String likerNickname;
  final String likerAvatarUrl;
  final DateTime? likedAt;

  factory ProfileUserLikeRowViewData.fromProfileUserLikeRowWire(
    ProfileUserLikeRowWireDto w,
  ) {
    return ProfileUserLikeRowViewData(
      postId: w.postId,
      title: w.title,
      coverUrl: w.coverUrl,
      likerNickname: w.likerNickname,
      likerAvatarUrl: w.likerAvatarUrl,
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
    required this.profileSubjectId,
    required this.displayName,
    required this.avatarUrl,
    this.isFollowing = false,
  });

  final String profileSubjectId;
  final String displayName;
  final String avatarUrl;
  final bool isFollowing;

  factory ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
    ProfileSocialRelationRowWireDto w,
  ) {
    final id = w.profileSubjectId;
    final name = w.displayName.isNotEmpty ? w.displayName : id;
    return ProfileSocialRelationRowViewData(
      profileSubjectId: id,
      displayName: name,
      avatarUrl: w.avatarUrl,
      isFollowing: w.isFollowing,
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
}

/// 清单用户档案展示面别名：端侧统一 [ProfileSubjectViewData]（与 codegen UserProfileDto wire 对齐由 Repository 负责）。
typedef UserProfileViewData = ProfileSubjectViewData;

/// 清单 PersonaDto：端侧管理行统一 [PersonaManagementItemViewData]。
typedef PersonaDtoSurface = PersonaManagementItemViewData;

@immutable
class ProfileInteractionActivityViewData {
  const ProfileInteractionActivityViewData({
    required this.activityId,
    required this.activityType,
    required this.direction,
    required this.actorProfileSubjectId,
    required this.actorDisplayName,
    required this.actorAvatarUrl,
    required this.targetProfileSubjectId,
    required this.targetContentId,
    required this.targetContentType,
    required this.targetContentSummary,
    required this.createdAt,
  });

  final String activityId;
  final String activityType;
  final String direction;
  final String actorProfileSubjectId;
  final String actorDisplayName;
  final String actorAvatarUrl;
  final String targetProfileSubjectId;
  final String targetContentId;
  final String targetContentType;
  final String targetContentSummary;
  final DateTime? createdAt;

  factory ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
    ProfileInteractionActivityWireDto w,
  ) {
    var activityId = w.activityId;
    if (activityId.isEmpty) {
      final prefix = w.activityType.isEmpty ? 'activity' : w.activityType;
      activityId = '$prefix:${w.actorProfileSubjectId}';
    }
    final actorDisplayName = w.actorDisplayName.isNotEmpty
        ? w.actorDisplayName
        : w.actorProfileSubjectId;
    return ProfileInteractionActivityViewData(
      activityId: activityId,
      activityType: w.activityType,
      direction: w.direction,
      actorProfileSubjectId: w.actorProfileSubjectId,
      actorDisplayName: actorDisplayName,
      actorAvatarUrl: w.actorAvatarUrl,
      targetProfileSubjectId: w.targetProfileSubjectId,
      targetContentId: w.targetContentId,
      targetContentType: w.targetContentType,
      targetContentSummary: w.targetContentSummary,
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
    required this.profileSubjectId,
    required this.ownerUserId,
    required this.subAccountId,
    required this.subjectType,
    required this.displayName,
    required this.avatarUrl,
    required this.personaContextVersion,
    this.isPrimary = false,
    this.isFallback = false,
  });

  final String profileSubjectId;
  final String ownerUserId;
  final String subAccountId;
  final String subjectType;
  final String displayName;
  final String avatarUrl;
  final String personaContextVersion;
  final bool isPrimary;
  final bool isFallback;

  bool get hasSubAccount => subAccountId.isNotEmpty;

  factory ActivePersonaContextViewData.fromActivePersonaContextWire(
    ActivePersonaContextWireDto w,
  ) {
    final profileSubjectId = w.profileSubjectId;
    var ownerUserId = w.ownerUserId;
    if (ownerUserId.isEmpty) {
      ownerUserId = profileSubjectId;
    }
    final subAccountId = w.subAccountId;
    final displayName = w.displayName.isNotEmpty
        ? w.displayName
        : profileSubjectId;
    final subjectType = w.subjectType.isNotEmpty
        ? w.subjectType
        : (subAccountId.isNotEmpty ? 'sub_account' : 'owner');
    return ActivePersonaContextViewData(
      profileSubjectId: profileSubjectId,
      ownerUserId: ownerUserId,
      subAccountId: subAccountId,
      subjectType: subjectType,
      displayName: displayName,
      avatarUrl: w.avatarUrl,
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
    required String profileSubjectId,
    required String ownerUserId,
    required String displayName,
    required String avatarUrl,
    String subAccountId = '',
    String subjectType = 'owner',
    String personaContextVersion = '',
  }) {
    return ActivePersonaContextViewData(
      profileSubjectId: profileSubjectId,
      ownerUserId: ownerUserId,
      subAccountId: subAccountId,
      subjectType: subjectType,
      displayName: displayName,
      avatarUrl: avatarUrl,
      personaContextVersion: personaContextVersion,
      isFallback: true,
    );
  }
}

@immutable
class PersonaManagementItemViewData {
  const PersonaManagementItemViewData({
    required this.subAccountId,
    required this.profileSubjectId,
    required this.displayName,
    required this.userHandle,
    required this.phone,
    required this.email,
    required this.avatarUrl,
    required this.isolationLevel,
    required this.profileVisibility,
    required this.isPrimary,
    required this.isActive,
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
  final String profileSubjectId;
  final String displayName;
  final String userHandle;
  final String phone;
  final String email;
  final String avatarUrl;
  final String isolationLevel;
  final String profileVisibility;
  final bool isPrimary;
  final bool isActive;
  final bool hasAttributedHistory;
  final bool hasPublishedContent;
  final bool inheritsProfileFromOwner;
  final List<String> overriddenProfileFields;
  final DateTime? lastProfileSyncAt;
  final String lastProfileSyncSource;
  final DateTime? lastActivatedAt;
  final String subjectType;

  bool get hasContactInfo => phone.isNotEmpty || email.isNotEmpty;

  /// 纠正 wire 默认 `subjectType: sub_account`：无 `subAccountId` 时视为 owner 主行。
  factory PersonaManagementItemViewData.fromPersonaManagementItemWire(
    PersonaManagementItemWireDto w,
  ) {
    final profileSubjectId = w.profileSubjectId.isNotEmpty
        ? w.profileSubjectId
        : w.subAccountId;
    final displayName = w.displayName.isNotEmpty
        ? w.displayName
        : profileSubjectId;
    final subjectType = w.subAccountId.isEmpty
        ? (w.subjectType.isEmpty || w.subjectType == 'sub_account'
              ? 'owner'
              : w.subjectType)
        : (w.subjectType.isNotEmpty ? w.subjectType : 'sub_account');
    return PersonaManagementItemViewData(
      subAccountId: w.subAccountId,
      profileSubjectId: profileSubjectId,
      displayName: displayName,
      userHandle: w.userHandle,
      phone: w.phone,
      email: w.email,
      avatarUrl: w.avatarUrl,
      isolationLevel: w.isolationLevel,
      profileVisibility: w.profileVisibility,
      isPrimary: w.isPrimary,
      isActive: w.isActive,
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

/// 生活记录条目。
@immutable
class UserLifeItem {
  const UserLifeItem({
    required this.id,
    required this.name,
    required this.category,
    required this.categoryKey,
    required this.coverUrl,
    required this.desc,
  });

  final String id;
  final String name;
  final String category;
  final String categoryKey;
  final String coverUrl;
  final String desc;
}
