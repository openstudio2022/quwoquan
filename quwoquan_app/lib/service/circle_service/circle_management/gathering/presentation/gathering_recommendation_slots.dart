import 'package:flutter/widgets.dart';

typedef GatheringMyIntersectionSlotBuilder = Widget Function({
  required bool isDark,
});

/// Gathering 行动发现页声明的 Recommendation participant 插槽。
///
/// 具体 Widget 只由 runtime/di 绑定；本页不依赖 Recommendation 私有 presentation。
final class GatheringRecommendationSlots {
  const GatheringRecommendationSlots({required this.buildMyIntersection});

  final GatheringMyIntersectionSlotBuilder buildMyIntersection;
}
