import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class PersonaProfileViewData {
  const PersonaProfileViewData({
    required this.personaId,
    required this.ownerUserId,
    required this.subjectType,
    required this.userHandle,
    required this.displayName,
    this.nicknameCustomized = false,
    required this.avatarUrl,
    this.avatarAssetId,
    this.avatarAccessMode,
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

  /// 头像的媒体交付绑定（DEC-033）：release authority 的资产标识与交付形态。
  /// 契约缺席即为 null，禁止以 personaId 冒充资产标识。
  final String? avatarAssetId;
  final MediaDeliveryAccessMode? avatarAccessMode;
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

  PersonaProfileViewData mergeStats(UserProfileStatsViewData stats) {
    return PersonaProfileViewData(
      personaId: personaId,
      ownerUserId: ownerUserId,
      subjectType: subjectType,
      userHandle: userHandle,
      displayName: displayName,
      nicknameCustomized: nicknameCustomized,
      avatarUrl: avatarUrl,
      avatarAssetId: avatarAssetId,
      avatarAccessMode: avatarAccessMode,
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
  factory UserProfileStatsViewData.fromWire(UserProfileStatsWire projection) {
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
