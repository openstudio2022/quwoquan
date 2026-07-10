import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/object_insight_primitives.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_section.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 「我的交集」预览入口（对象/圈子/用户主页共享）。
///
/// C 包收敛后，本类仅作为旧调用方的薄包装：运行时唯一渲染/导航/行动分发真相源是
/// [ObjectIntersectionSection]。保留构造 API 是为了避免同一轮大面积调用方 churn，
/// 但不得在本类内恢复独立行渲染、查看全部、span 导航或 actionHint 分发逻辑。
class ObjectIntersectionPreviewCard extends ConsumerWidget {
  const ObjectIntersectionPreviewCard({
    super.key,
    required this.objectId,
    required this.objectType,
    required this.title,
    required this.emptyText,
    required this.referralSource,
    this.viewAllTitle,
    this.cardKey,
    this.emptyKey,
    this.topPadding = true,
    this.maxPreview = 3,
  });

  /// 目标对象 id（实体 homepageId / 圈子 circleId / 用户 userId）。
  final String objectId;

  /// 目标对象类型（'homepage' | 'circle' | 'user'）。
  final String objectType;

  /// 模块标题（统一「我的交集」语义 token）。
  final String title;

  /// 无交集事实时的克制空态文案。
  final String emptyText;

  /// 交集片段点击归因来源（实体 entityPage / 圈子 circlePost / 用户 authorProfile）。
  final ReferralSource referralSource;

  /// 「查看全部」明细页标题；缺省回退 [title]。
  final String? viewAllTitle;

  final Key? cardKey;
  final Key? emptyKey;
  final bool topPadding;
  final int maxPreview;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final viewerId = ref.watch(currentUserIdProvider);
    final query = ObjectIntersectionQuery(
      objectAId: viewerId,
      objectAType: 'user',
      objectBId: objectId,
      objectBType: objectType,
    );
    if (!query.isResolvable) {
      return ProfileInsightSectionCard(
        key: cardKey,
        title: title,
        topPadding: topPadding,
        child: ProfileIntersectionEmptyState(key: emptyKey, text: emptyText),
      );
    }
    return ObjectIntersectionSection(
      key: cardKey,
      query: query,
      title: title,
      isDark: CupertinoTheme.of(context).brightness == Brightness.dark,
      emptyText: emptyText,
    );
  }
}
