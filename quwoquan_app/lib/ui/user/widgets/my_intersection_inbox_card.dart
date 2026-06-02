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

/// 我的主页「我的交集」聚合入口卡。
///
/// 展示总数 + 最多 3 个维度的未读红点/数字；超过 3 个收起「展开更多」。
/// 点击卡或维度进入分维度列表页（打开列表即清零红点，由列表页推进已读水位）。
class MyIntersectionInboxCard extends ConsumerStatefulWidget {
  const MyIntersectionInboxCard({super.key, required this.isDark});

  final bool isDark;

  @override
  ConsumerState<MyIntersectionInboxCard> createState() =>
      _MyIntersectionInboxCardState();
}

class _MyIntersectionInboxCardState
    extends ConsumerState<MyIntersectionInboxCard> {
  static const int _collapsedMax = 3;
  bool _expanded = false;

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
      return _shell(context, child: _buildEmpty(context));
    }
    final dimensions = summary.dimensions;
    final visible = _expanded
        ? dimensions
        : dimensions.take(_collapsedMax).toList(growable: false);
    final hasMore = dimensions.length > _collapsedMax;
    return _shell(
      context,
      onTap: () => _openList(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _buildHeader(context, summary.totalNewCount),
          SizedBox(height: AppSpacing.intraGroupSm),
          Wrap(
            spacing: AppSpacing.intraGroupSm,
            runSpacing: AppSpacing.intraGroupSm,
            children: <Widget>[
              for (final tally in visible)
                _DimensionPill(
                  tally: tally,
                  isDark: widget.isDark,
                  onTap: () => _openList(dimension: tally.dimension),
                ),
              if (hasMore)
                _MorePill(
                  expanded: _expanded,
                  onTap: () => setState(() => _expanded = !_expanded),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _shell(
    BuildContext context, {
    required Widget child,
    VoidCallback? onTap,
  }) {
    final surface = AppColors.iosProfileSurface(context);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: widget.isDark ? 0.24 : 0.08);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(color: border, width: AppSpacing.hairline),
        ),
        child: child,
      ),
    );
  }

  Widget _buildHeader(BuildContext context, int totalNew) {
    return Row(
      children: <Widget>[
        Icon(
          CupertinoIcons.circle_grid_hex,
          size: AppSpacing.iconSmall,
          color: AppColors.iosAccent(context),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Flexible(
          child: Text(
            UITextConstants.myIntersectionsTitle,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
        ),
        if (totalNew > 0) ...<Widget>[
          SizedBox(width: AppSpacing.intraGroupSm),
          _RedCountBadge(count: totalNew),
        ],
        const Spacer(),
        Flexible(
          child: Text(
            UITextConstants.myIntersectionsSubtitle,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.end,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Icon(
          CupertinoIcons.chevron_forward,
          size: AppSpacing.iconSmall,
          color: AppColors.iosTertiaryLabel(context),
        ),
      ],
    );
  }

  Widget _buildEmpty(BuildContext context) {
    return Row(
      children: <Widget>[
        Icon(
          CupertinoIcons.circle_grid_hex,
          size: AppSpacing.iconSmall,
          color: AppColors.iosTertiaryLabel(context),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: Text(
            UITextConstants.myIntersectionsEmpty,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ),
      ],
    );
  }
}

class _DimensionPill extends StatelessWidget {
  const _DimensionPill({
    required this.tally,
    required this.isDark,
    required this.onTap,
  });

  final IntersectionDimensionTally tally;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupSm,
        ),
        decoration: BoxDecoration(
          color: AppColors.iosSystemBackground(context).withValues(alpha: 0.72),
          borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
          border: Border.all(
            color: AppColors.iosSeparator(
              context,
            ).withValues(alpha: isDark ? 0.3 : 0.12),
            width: AppSpacing.hairline,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              tally.label,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                fontWeight: AppTypography.medium,
                color: AppColors.iosLabel(context),
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
            Text(
              '${tally.count}',
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            if (tally.newCount > 0) ...<Widget>[
              SizedBox(width: AppSpacing.intraGroupXs),
              _RedCountBadge(count: tally.newCount),
            ],
          ],
        ),
      ),
    );
  }
}

class _MorePill extends StatelessWidget {
  const _MorePill({required this.expanded, required this.onTap});

  final bool expanded;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupSm,
        ),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
        ),
        child: Text(
          expanded
              ? UITextConstants.intersectionCollapse
              : UITextConstants.intersectionExpandMore,
          style: TextStyle(
            fontSize: AppTypography.iosCaption1,
            fontWeight: AppTypography.medium,
            color: AppColors.iosAccent(context),
          ),
        ),
      ),
    );
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
