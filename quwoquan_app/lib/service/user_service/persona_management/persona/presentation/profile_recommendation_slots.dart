import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_tracker_port.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/author_impact_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ProfileOtherIntersectionSlotBuilder =
    Widget Function({required String userId});

typedef ProfileMyIntersectionSlotBuilder =
    Widget Function({required bool isDark});

typedef ProfileMyGatheringsSlotBuilder =
    Widget Function({required bool isDark});

typedef ProfileMyExperienceSlotBuilder =
    Widget Function({required bool isDark});

typedef ProfileCreatorProofSlotBuilder =
    Widget Function({required String personaId});

typedef ProfileAuthorImpactSlotBuilder =
    Widget Function({
      required AuthorImpactSummary summary,
      required bool isDark,
      required bool isMine,
      required AuthorImpactQuery authorImpactQuery,
      required ContentBehaviorTrackerPort contentBehaviorTracker,
    });

typedef ProfileIntersectionReasonSlotBuilder =
    Widget? Function(
      List<IntersectionReason>? reasons, {
      required bool isDark,
      required ReferralSource referralSource,
      required String contextObjectName,
      required IntersectionTarget contextObjectTarget,
    });

/// Persona source owner 声明的跨域 participant 插槽（Recommendation + Circle）。
///
/// 具体 Widget 只由 runtime/di 绑定；ProfileShell/ProfileWorksTab 不依赖
/// Recommendation / Circle 私有 presentation。
final class ProfileRecommendationSlots {
  const ProfileRecommendationSlots({
    required this.buildOtherIntersection,
    required this.buildMyIntersection,
    required this.buildAuthorImpact,
    required this.buildIntersectionReason,
    required this.buildMyGatherings,
    required this.buildMyExperience,
    required this.buildCreatorProof,
  });

  final ProfileOtherIntersectionSlotBuilder buildOtherIntersection;
  final ProfileMyIntersectionSlotBuilder buildMyIntersection;
  final ProfileAuthorImpactSlotBuilder buildAuthorImpact;
  final ProfileIntersectionReasonSlotBuilder buildIntersectionReason;

  /// 「我的行动」单行入口（Circle participant；REQ-008，仅 mine 模式挂载）。
  final ProfileMyGatheringsSlotBuilder buildMyGatherings;

  /// 「共同经历」资产行（Recommendation participant；REQ-008，仅 mine 模式挂载）。
  final ProfileMyExperienceSlotBuilder buildMyExperience;

  /// 创作者「成行力」单行事实计数（影响力面扩展；零计数不渲染，仅 mine 挂载）。
  final ProfileCreatorProofSlotBuilder buildCreatorProof;
}
