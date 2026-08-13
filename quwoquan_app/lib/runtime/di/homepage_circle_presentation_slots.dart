import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_source_cards_section.dart';

/// 实体主页的 Circle participant 插槽绑定：来源=该实体的「近期公开行动」区块。
///
/// 与 [profile_presentation_slots] 同范式：跨域 participant Widget 只在
/// runtime/di 组合根绑定，entity presentation 不直接依赖 circle presentation。
Widget buildHomepageRecentGatheringsSlot({
  required String homepageId,
  required bool isDark,
}) => GatheringSourceCardsSection(
  sourceObjectTypeRef: 'homepage',
  sourceObjectId: homepageId,
  isDark: isDark,
);
