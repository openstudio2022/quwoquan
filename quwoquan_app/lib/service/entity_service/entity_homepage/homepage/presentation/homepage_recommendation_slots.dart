import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/object_intersection_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef HomepageIntersectionReasonSlotBuilder =
    Widget? Function(
      List<IntersectionReason>? reasons, {
      required bool isDark,
      required ReferralSource referralSource,
      required String contextObjectName,
      required IntersectionTarget contextObjectTarget,
    });

typedef HomepageObjectIntersectionSlotBuilder =
    Widget Function({
      required Key key,
      required ObjectIntersectionQuery query,
      required String title,
      required bool isDark,
      required String emptyText,
      required Key emptyKey,
    });

typedef HomepageObjectImpactSlotBuilder =
    Widget Function({
      required String objectId,
      required ReferralSource referralSource,
      required String title,
      required String enumerableHint,
      required Key cardKey,
      required bool topDivider,
    });

/// Entity homepage source owner 声明的 Recommendation participant 插槽。
///
/// 具体 Widget 只由 runtime/di 绑定；本对象 presentation 不依赖 Recommendation
/// 的私有 presentation/provider。
final class HomepageRecommendationSlots {
  const HomepageRecommendationSlots({
    required this.buildIntersectionReason,
    required this.buildObjectIntersection,
    required this.buildObjectImpact,
  });

  final HomepageIntersectionReasonSlotBuilder buildIntersectionReason;
  final HomepageObjectIntersectionSlotBuilder buildObjectIntersection;
  final HomepageObjectImpactSlotBuilder buildObjectImpact;
}
