import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/components/object_page/intersection_statement_row.dart';

// Barrel re-export：消费者继续 import 本文件即可访问单行模型 / 渲染（[IntersectionStatementItem]
// / [IntersectionStatementRow] / [IntersectionStatementHighlight]）；拆分（R03）对
// object_page / circle_shell / 时间线等消费者零改动。
export 'package:quwoquan_app/components/object_page/intersection_statement_row.dart';

class IntersectionStatementCard extends StatefulWidget {
  const IntersectionStatementCard({
    super.key,
    required this.title,
    required this.items,
    this.titleBadge,
    this.emptyChild,
    this.collapsedMaxItems = 3,
    this.padding,
    this.topDivider = false,
    this.footerActionLabel,
    this.onFooterAction,
  });

  final String title;
  final List<IntersectionStatementItem> items;
  final Widget? titleBadge;
  final Widget? emptyChild;
  final int collapsedMaxItems;
  final EdgeInsetsGeometry? padding;
  final String? footerActionLabel;
  final VoidCallback? onFooterAction;

  /// 与上一区块的分隔间距（iOS 分组列表区块间留白）。
  /// 仅在本卡真实渲染（非 shrink）时出现，避免空区块残留孤立间距。
  final bool topDivider;

  @override
  State<IntersectionStatementCard> createState() =>
      _IntersectionStatementCardState();
}

class _IntersectionStatementCardState extends State<IntersectionStatementCard> {
  bool _expanded = false;

  /// iOS 分组列表行水平内边距（行文案左缘 = 卡片左 + 该值，分隔线同此内缩）。
  static const double _rowHorizontalPadding = AppSpacing.containerSm;

  /// 区块标题竖条宽度：与「我的交集」卡 [ProfileInsightSectionCard] 同 token
  /// （`AppSpacing.xs / 2`），保证交集 / 影响力双模块标题竖条像素级一致。
  static const double _sectionAccentWidth = AppSpacing.xs / 2;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final separator = AppColors.iosSeparator(context);
    final cardBorder = separator.withValues(alpha: isDark ? 0.14 : 0.07);
    final cardShadow = AppColors.black.withValues(alpha: isDark ? 0.10 : 0.018);
    final accentColor =
        (isDark
                ? AppColors.profileSloganAccentDark
                : AppColors.profileSloganAccentLight)
            .withValues(alpha: isDark ? 0.80 : 0.56);
    final visible = _expanded
        ? widget.items
        : widget.items.take(widget.collapsedMaxItems).toList(growable: false);
    final hasMore = widget.items.length > widget.collapsedMaxItems;

    // 区块标题（深色 label）：iOS 分组头，中性短线只做“交集资产”锚点。
    final header = Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerSm,
        AppSpacing.containerXs,
        AppSpacing.intraGroupXs,
        AppSpacing.intraGroupXs,
      ),
      child: Row(
        children: <Widget>[
          Container(
            width: _sectionAccentWidth,
            height: AppSpacing.iconSmall,
            decoration: BoxDecoration(
              color: accentColor,
              borderRadius: BorderRadius.circular(_sectionAccentWidth),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Text(
              widget.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                fontWeight: AppTypography.regular,
                color: AppColors.iosLabel(context),
                letterSpacing: -0.08,
              ),
            ),
          ),
          if (widget.titleBadge != null) widget.titleBadge!,
          if (hasMore)
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.buttonHeightSm,
              ),
              onPressed: () => setState(() => _expanded = !_expanded),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    _expanded
                        ? DiscoveryFeedText.intersectionCollapse
                        : DiscoveryFeedText.intersectionExpandMore,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.regular,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupXs / 2),
                  Icon(
                    _expanded
                        ? CupertinoIcons.chevron_up
                        : CupertinoIcons.chevron_down,
                    size: AppSpacing.iconXSmall,
                    color: AppColors.iosTertiaryLabel(context),
                  ),
                ],
              ),
            ),
        ],
      ),
    );

    // 列表卡：独立成块但弱化线条，靠柔和表面与轻阴影体现高级感。
    final Widget listBody = visible.isEmpty
        ? Padding(
            padding: EdgeInsets.symmetric(
              horizontal: _rowHorizontalPadding,
              vertical: AppSpacing.containerSm,
            ),
            child: widget.emptyChild ?? const SizedBox.shrink(),
          )
        : AnimatedSize(
            duration: const Duration(milliseconds: 260),
            curve: Curves.easeOutCubic,
            alignment: Alignment.topCenter,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                for (var i = 0; i < visible.length; i += 1) ...<Widget>[
                  if (i > 0)
                    Padding(
                      padding: EdgeInsets.only(left: _rowHorizontalPadding * 2),
                      child: Container(
                        height: AppSpacing.hairline,
                        color: AppColors.iosSeparator(
                          context,
                        ).withValues(alpha: 0.12),
                      ),
                    ),
                  Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: _rowHorizontalPadding,
                    ),
                    child: IntersectionStatementRow(item: visible[i]),
                  ),
                ],
              ],
            ),
          );

    final hasFooterAction =
        widget.onFooterAction != null &&
        (widget.footerActionLabel?.trim().isNotEmpty ?? false);
    final card = Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(color: cardBorder, width: AppSpacing.hairline),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: cardShadow,
            blurRadius: AppSpacing.fourteen,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          header,
          Container(
            height: AppSpacing.hairline,
            color: AppColors.iosSeparator(context).withValues(alpha: 0.12),
          ),
          listBody,
          if (hasFooterAction) ...<Widget>[
            Container(
              height: AppSpacing.hairline,
              color: accentColor.withValues(alpha: isDark ? 0.12 : 0.10),
            ),
            _TimelineFooterAction(
              label: widget.footerActionLabel!.trim(),
              onTap: widget.onFooterAction!,
            ),
          ],
        ],
      ),
    );

    Widget content = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[card],
    );
    if (widget.topDivider) {
      content = Padding(
        padding: EdgeInsets.only(top: AppSpacing.interGroupSm),
        child: content,
      );
    }
    if (widget.padding != null) {
      content = Padding(padding: widget.padding!, child: content);
    }
    return content;
  }
}

class _TimelineFooterAction extends StatelessWidget {
  const _TimelineFooterAction({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final surface = isDark
        ? AppColors.iosSecondaryFill(context)
        : AppColors.iosSystemBackground(context);
    final ink = AppColors.iosLabel(context);
    final ornament = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.26 : 0.18);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.buttonHeightMd,
      ),
      onPressed: onTap,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Expanded(child: _FooterOrnamentLine(color: ornament)),
          SizedBox(width: AppSpacing.intraGroupSm),
          DecoratedBox(
            decoration: BoxDecoration(
              color: surface.withValues(alpha: isDark ? 0.32 : 0.68),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              border: Border.all(color: ornament, width: AppSpacing.hairline),
            ),
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    label,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.regular,
                      color: ink,
                      letterSpacing: -0.04,
                    ),
                  ),
                ],
              ),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(child: _FooterOrnamentLine(color: ornament, reverse: true)),
        ],
      ),
    );
  }
}

class _FooterOrnamentLine extends StatelessWidget {
  const _FooterOrnamentLine({required this.color, this.reverse = false});

  final Color color;
  final bool reverse;

  @override
  Widget build(BuildContext context) {
    final dot = Container(
      width: AppSpacing.xs,
      height: AppSpacing.xs,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
    final line = Expanded(
      child: Container(height: AppSpacing.hairline, color: color),
    );
    return Row(
      children: reverse
          ? <Widget>[dot, SizedBox(width: AppSpacing.intraGroupXs), line]
          : <Widget>[line, SizedBox(width: AppSpacing.intraGroupXs), dot],
    );
  }
}
