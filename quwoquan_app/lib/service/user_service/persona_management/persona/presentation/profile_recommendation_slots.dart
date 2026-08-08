import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_tracker_port.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/author_impact_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ProfileOtherIntersectionSlotBuilder =
    Widget Function({required String userId});

typedef ProfileMyIntersectionSlotBuilder =
    Widget Function({required bool isDark});

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

/// Persona source owner 声明的 Recommendation participant 插槽。
///
/// 具体 Widget 只由 runtime/di 绑定；ProfileShell/ProfileWorksTab 不依赖
/// Recommendation 私有 presentation。
final class ProfileRecommendationSlots {
  const ProfileRecommendationSlots({
    required this.buildOtherIntersection,
    required this.buildMyIntersection,
    required this.buildAuthorImpact,
    required this.buildIntersectionReason,
  });

  final ProfileOtherIntersectionSlotBuilder buildOtherIntersection;
  final ProfileMyIntersectionSlotBuilder buildMyIntersection;
  final ProfileAuthorImpactSlotBuilder buildAuthorImpact;
  final ProfileIntersectionReasonSlotBuilder buildIntersectionReason;
}
