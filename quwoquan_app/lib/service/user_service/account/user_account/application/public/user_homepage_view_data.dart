import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 主页 Tab 角标计数（works / likes / circles / collections）。
///
/// collectionsCount 属 content 域，云侧 user 域置 0，端侧由 content 接口覆盖（不造假）。
class UserHomepageTabCountsViewData {
  const UserHomepageTabCountsViewData({
    required this.worksCount,
    required this.likesCount,
    required this.circlesCount,
    required this.collectionsCount,
  });

  final int worksCount;
  final int likesCount;
  final int circlesCount;
  final int collectionsCount;

  factory UserHomepageTabCountsViewData.fromWire(UserHomepageTabCountsWire w) {
    return UserHomepageTabCountsViewData(
      worksCount: w.worksCount,
      likesCount: w.likesCount,
      circlesCount: w.circlesCount,
      collectionsCount: w.collectionsCount,
    );
  }

  /// 缺省回退：用统计计数同源推导，collections 归 0 留待 content 域覆盖。
  factory UserHomepageTabCountsViewData.fromStats(UserProfileStatsViewData s) {
    return UserHomepageTabCountsViewData(
      worksCount: s.postCount,
      likesCount: s.likeCount,
      circlesCount: s.circleCount,
      collectionsCount: 0,
    );
  }

  UserHomepageTabCountsViewData copyWith({int? collectionsCount}) {
    return UserHomepageTabCountsViewData(
      worksCount: worksCount,
      likesCount: likesCount,
      circlesCount: circlesCount,
      collectionsCount: collectionsCount ?? this.collectionsCount,
    );
  }
}

/// 主页查看者上下文：区分本人 / 游客 / 关系态，驱动「我的主页 vs 他人主页」差异化外观。
class UserHomepageViewerContextViewData {
  const UserHomepageViewerContextViewData({
    required this.viewerPersonaId,
    required this.isOwner,
    required this.isGuest,
    required this.relationToTarget,
    required this.canViewFullProfile,
  });

  /// 游客保守回退：viewerContext 缺失时按未登录处理（不下发关系能力）。
  const UserHomepageViewerContextViewData.guest()
    : viewerPersonaId = '',
      isOwner = false,
      isGuest = true,
      relationToTarget = 'not_following',
      canViewFullProfile = true;

  final String viewerPersonaId;
  final bool isOwner;
  final bool isGuest;
  final String relationToTarget;
  final bool canViewFullProfile;

  /// 陌生人：已登录非本人且未建立关系（用于优雅隐藏私密入口）。
  bool get isStranger =>
      !isOwner && !isGuest && relationToTarget == 'not_following';

  factory UserHomepageViewerContextViewData.fromWire(
    UserHomepageViewerContextWire w,
  ) {
    return UserHomepageViewerContextViewData(
      viewerPersonaId: w.viewerPersonaId,
      isOwner: w.isOwner,
      isGuest: w.isGuest,
      relationToTarget: w.relationToTarget.wireName,
      canViewFullProfile: w.canViewFullProfile,
    );
  }
}

/// 主页首屏聚合视图（`ProfileQuery.getUserHomepageBundle`）。
///
/// 仅承载身份域真相（profile/stats/relationship/tabCounts/viewerContext）；交集卡与
/// 打动 evidence 属 content 域，由端侧并发补充，bundle 不做内容事实第二真相源。
class UserHomepageBundleViewData {
  const UserHomepageBundleViewData({
    required this.profile,
    required this.stats,
    required this.relationshipCapability,
    required this.tabCounts,
    required this.viewerContext,
    required this.cacheVersion,
  });

  final PersonaProfileViewData profile;
  final UserProfileStatsViewData stats;

  /// viewer→target 关系能力位（关注/私信/打招呼/通话/拉黑），统一复用既有
  /// [RelationshipCapabilityViewData]（端侧关系能力唯一真相源）。本人态/游客态为 null。
  final RelationshipCapabilityViewData? relationshipCapability;
  final UserHomepageTabCountsViewData tabCounts;
  final UserHomepageViewerContextViewData viewerContext;

  /// bundle 版本锚（随档案更新 / viewer / 关系态变化），供端乐观回填与并发刷新一致性校验。
  final String cacheVersion;

  /// 首屏 header 直接展示用：profile 已合并 stats 计数（同源）。
  PersonaProfileViewData get profileWithStats => profile.mergeStats(stats);

  factory UserHomepageBundleViewData.fromWire(
    UserHomepageBundleWire projection, {
    required PersonaProfileViewData profile,
  }) {
    final stats = UserProfileStatsViewData.fromWire(projection.stats);
    final counts = projection.tabCounts;
    final viewer = projection.viewerContext;
    final capability = projection.relationshipCapability;
    return UserHomepageBundleViewData(
      profile: profile,
      stats: stats,
      relationshipCapability: capability == null
          ? null
          : RelationshipCapabilityViewData.fromWire(capability),
      tabCounts: UserHomepageTabCountsViewData(
        worksCount: counts.worksCount,
        likesCount: counts.likesCount,
        circlesCount: counts.circlesCount,
        collectionsCount: counts.collectionsCount,
      ),
      viewerContext: UserHomepageViewerContextViewData(
        viewerPersonaId: viewer.viewerPersonaId,
        isOwner: viewer.isOwner,
        isGuest: viewer.isGuest,
        relationToTarget: viewer.relationToTarget.wireName,
        canViewFullProfile: viewer.canViewFullProfile,
      ),
      cacheVersion: projection.cacheVersion,
    );
  }
}
