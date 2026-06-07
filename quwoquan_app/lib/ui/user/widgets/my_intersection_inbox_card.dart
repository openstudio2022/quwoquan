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
          _buildSummaryHeader(
            context,
            totalCount: summary.totalCount,
            totalNew: summary.totalNewCount,
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          AnimatedSize(
            duration: const Duration(milliseconds: 280),
            curve: Curves.easeOutCubic,
            alignment: Alignment.topCenter,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                for (var i = 0; i < visible.length; i++) ...<Widget>[
                  if (i > 0)
                    Container(
                      height: AppSpacing.hairline,
                      margin: EdgeInsets.symmetric(
                        vertical: AppSpacing.intraGroupXs,
                      ),
                      color: AppColors.iosSeparator(
                        context,
                      ).withValues(alpha: widget.isDark ? 0.18 : 0.06),
                    ),
                  _BriefRow(
                    tally: visible[i],
                    onTap: () => _openList(dimension: visible[i].dimension),
                  ),
                ],
              ],
            ),
          ),
          if (hasMore)
            Padding(
              padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
              child: _MorePill(
                expanded: _expanded,
                onTap: () => setState(() => _expanded = !_expanded),
              ),
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

  Widget _buildSummaryHeader(
    BuildContext context, {
    required int totalCount,
    required int totalNew,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Container(
          width: AppSpacing.largeButtonSize,
          height: AppSpacing.largeButtonSize,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: AppColors.iosAccent(context).withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          ),
          child: Icon(
            CupertinoIcons.circle_grid_hex,
            size: AppSpacing.iconMedium,
            color: AppColors.iosAccent(context),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Text(
                    '$totalCount',
                    style: TextStyle(
                      fontSize: AppTypography.iosLargeTitle,
                      fontWeight: AppTypography.bold,
                      color: AppColors.iosLabel(context),
                      height: AppSpacing.textLineHeightSingle,
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupXs),
                  // §7.5 红点消除：清零后 fade+scale 收起，给「已读」确定感。
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 240),
                    switchInCurve: Curves.easeOutBack,
                    switchOutCurve: Curves.easeIn,
                    transitionBuilder: (child, anim) => ScaleTransition(
                      scale: anim,
                      child: FadeTransition(opacity: anim, child: child),
                    ),
                    child: totalNew > 0
                        ? _RedCountBadge(
                            key: ValueKey<int>(totalNew),
                            count: totalNew,
                          )
                        : const SizedBox.shrink(key: ValueKey<String>('no-new')),
                  ),
                ],
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                UITextConstants.myIntersectionsTitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosLabel(context),
                ),
              ),
              Text(
                UITextConstants.myIntersectionsSubtitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ],
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Padding(
          padding: EdgeInsets.only(top: AppSpacing.intraGroupXs),
          child: Icon(
            CupertinoIcons.chevron_forward,
            size: AppSpacing.iconSmall,
            color: AppColors.iosTertiaryLabel(context),
          ),
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

/// 动态简报行：云侧实例化一句话（briefText）优先；缺省回落 label + 新增数。
class _BriefRow extends StatelessWidget {
  const _BriefRow({required this.tally, required this.onTap});

  final IntersectionDimensionTally tally;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final hasNew = tally.newCount > 0;
    final brief = tally.briefText.trim();
    final text = brief.isNotEmpty
        ? brief
        : (hasNew
              ? '${tally.label} ${tally.newCount} ${UITextConstants.intersectionNewBadgeSuffix}'
              : '${tally.label} ${tally.count}');
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: ConstrainedBox(
        constraints: BoxConstraints(minHeight: AppSpacing.minInteractiveSize),
        child: Row(
          children: <Widget>[
            Container(
              width: AppSpacing.sm,
              height: AppSpacing.sm,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: hasNew
                    ? AppColors.error
                    : AppColors.iosTertiaryLabel(context),
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Text(
                text,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: hasNew
                      ? AppTypography.medium
                      : AppTypography.regular,
                  color: AppColors.iosLabel(context),
                ),
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.fourteen,
              color: AppColors.iosTertiaryLabel(context),
            ),
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
  const _RedCountBadge({super.key, required this.count});

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
