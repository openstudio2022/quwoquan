import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/user/providers/my_intersection_inbox_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/intersection_statement_card.dart';

/// 我的主页「我的交集」聚合入口卡（V4 · 动态简报）。
///
/// 设计（专业设计师视角：精致 / 事实清晰 / 简洁）：
/// - 头部总数 + 未读红点；
/// - 维度胶囊改为「动态简报行」：每行一条云侧实例化简报句（briefText，
///   如"3 位联系人新加入了你关注的圈子"），缺省回落 label + 新增数，端不编造事实；
/// - 默认 3 行，超出收起「展开更多」；点击行/卡进入分维度列表页（打开即清零红点）。
/// - 维度 dimension 为开放字符串，未知维度优雅降级（必读要求 1）。
class MyIntersectionInboxCard extends ConsumerStatefulWidget {
  const MyIntersectionInboxCard({super.key, required this.isDark});

  final bool isDark;

  @override
  ConsumerState<MyIntersectionInboxCard> createState() =>
      _MyIntersectionInboxCardState();
}

class _MyIntersectionInboxCardState
    extends ConsumerState<MyIntersectionInboxCard> {
  @override
  void initState() {
    super.initState();
    Future<void>.microtask(
      () => ref.read(myIntersectionSummaryProvider.notifier).load(),
    );
  }

  void _openList({String dimension = ''}) {
    final path = dimension.isEmpty
        ? AppRoutePaths.myIntersections()
        : AppRoutePaths.myIntersections(dimension: dimension);
    context.push(path);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(myIntersectionSummaryProvider);
    final summary = state.summary;
    if (summary == null) {
      return const SizedBox.shrink();
    }
    if (summary.totalCount == 0) {
      return IntersectionStatementCard(
        title: UITextConstants.myIntersectionsTitle,
        items: const <IntersectionStatementItem>[],
        emptyChild: _buildEmpty(context),
      );
    }
    final dimensions = summary.dimensions;
    return IntersectionStatementCard(
      title: UITextConstants.myIntersectionsTitle,
      titleBadge: summary.totalNewCount > 0
          ? _RedCountBadge(count: summary.totalNewCount)
          : null,
      items: <IntersectionStatementItem>[
        for (var i = 0; i < dimensions.length; i += 1)
          IntersectionStatementItem(
            primaryText: _primaryTextFor(dimensions[i]),
            subtitleText: _subtitleTextFor(dimensions[i]),
            highlight: i == 0
                ? IntersectionStatementHighlight.blue
                : IntersectionStatementHighlight.gray,
            onTap: () => _openList(dimension: dimensions[i].dimension),
          ),
      ],
    );
  }

  Widget _buildEmpty(BuildContext context) {
    return Text(
      UITextConstants.myIntersectionsEmpty,
      style: TextStyle(
        fontSize: AppTypography.iosCaption1,
        color: AppColors.iosSecondaryLabel(context),
      ),
    );
  }

  String _primaryTextFor(IntersectionDimensionTally tally) {
    final brief = tally.briefText.trim();
    if (brief.isNotEmpty) {
      return brief;
    }
    if (tally.newCount > 0) {
      return '${tally.label} ${tally.newCount} ${UITextConstants.intersectionNewBadgeSuffix}';
    }
    return '${tally.label} ${tally.count}';
  }

  String _subtitleTextFor(IntersectionDimensionTally tally) {
    final subtitle = tally.subtitleText.trim();
    if (subtitle.isNotEmpty) {
      return subtitle;
    }
    return UITextConstants.myIntersectionsSubtitle;
  }
}

/// 仅用于「未读/新增」数字的红色提醒徽标。
class _RedCountBadge extends StatelessWidget {
  const _RedCountBadge({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(minWidth: AppSpacing.lg),
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.intraGroupXs),
      decoration: BoxDecoration(
        color: AppColors.error,
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        count > 99 ? '99+' : '$count',
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.semiBold,
          color: AppColors.white,
        ),
      ),
    );
  }
}
