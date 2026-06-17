import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum IntersectionStatementHighlight { blue, gray }

class IntersectionStatementItem {
  const IntersectionStatementItem({
    required this.primaryText,
    required this.subtitleText,
    this.highlight = IntersectionStatementHighlight.gray,
    this.onTap,
  });

  final String primaryText;
  final String subtitleText;
  final IntersectionStatementHighlight highlight;
  final VoidCallback? onTap;
}

class IntersectionStatementCard extends StatefulWidget {
  const IntersectionStatementCard({
    super.key,
    required this.title,
    required this.items,
    this.titleBadge,
    this.emptyChild,
    this.collapsedMaxItems = 3,
    this.padding,
  });

  final String title;
  final List<IntersectionStatementItem> items;
  final Widget? titleBadge;
  final Widget? emptyChild;
  final int collapsedMaxItems;
  final EdgeInsetsGeometry? padding;

  @override
  State<IntersectionStatementCard> createState() =>
      _IntersectionStatementCardState();
}

class _IntersectionStatementCardState extends State<IntersectionStatementCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final border = AppColors.iosSeparator(context).withValues(alpha: 0.08);
    final visible = _expanded
        ? widget.items
        : widget.items.take(widget.collapsedMaxItems).toList(growable: false);
    final hasMore = widget.items.length > widget.collapsedMaxItems;
    return Container(
      width: double.infinity,
      padding:
          widget.padding ??
          EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.containerSm,
          ),
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: border, width: AppSpacing.hairline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  widget.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.iosLabel(context),
                    letterSpacing: -0.08,
                  ),
                ),
              ),
              if (widget.titleBadge != null) widget.titleBadge!,
              if (hasMore) ...<Widget>[
                SizedBox(width: AppSpacing.intraGroupSm),
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size(
                    AppSpacing.minInteractiveSize,
                    AppSpacing.minInteractiveSize,
                  ),
                  onPressed: () => setState(() => _expanded = !_expanded),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Text(
                        _expanded
                            ? UITextConstants.intersectionCollapse
                            : UITextConstants.intersectionExpandMore,
                        style: TextStyle(
                          fontSize: AppTypography.iosCaption1,
                          fontWeight: AppTypography.medium,
                          color: AppColors.iosAccent(context),
                        ),
                      ),
                      SizedBox(width: AppSpacing.intraGroupXs / 2),
                      Icon(
                        _expanded
                            ? CupertinoIcons.chevron_up
                            : CupertinoIcons.chevron_down,
                        size: AppSpacing.iconXSmall,
                        color: AppColors.iosAccent(context),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          if (visible.isEmpty)
            widget.emptyChild ?? const SizedBox.shrink()
          else
            AnimatedSize(
              duration: const Duration(milliseconds: 260),
              curve: Curves.easeOutCubic,
              alignment: Alignment.topCenter,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  for (var i = 0; i < visible.length; i += 1) ...<Widget>[
                    if (i > 0) _StatementDivider(),
                    IntersectionStatementRow(item: visible[i]),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class IntersectionStatementRow extends StatelessWidget {
  const IntersectionStatementRow({super.key, required this.item});

  final IntersectionStatementItem item;

  @override
  Widget build(BuildContext context) {
    final primaryColor = item.highlight == IntersectionStatementHighlight.blue
        ? AppColors.iosAccent(context)
        : AppColors.iosLabel(context);
    final subtitle = item.subtitleText.trim().isNotEmpty
        ? item.subtitleText.trim()
        : UITextConstants.profileStatementFallbackSubtitle;
    final content = ConstrainedBox(
      constraints: BoxConstraints(minHeight: AppSpacing.minInteractiveSize),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  item.primaryText.trim(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: AppTypography.medium,
                    color: primaryColor,
                    letterSpacing: -0.08,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs / 2),
                Text(
                  subtitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: AppColors.iosSecondaryLabel(context),
                    letterSpacing: -0.04,
                  ),
                ),
              ],
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Icon(
            CupertinoIcons.chevron_forward,
            size: AppSpacing.iconXSmall,
            color: AppColors.iosTertiaryLabel(context),
          ),
        ],
      ),
    );
    if (item.onTap == null) {
      return content;
    }
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.minInteractiveSize),
      onPressed: item.onTap,
      child: content,
    );
  }
}

class _StatementDivider extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
      child: Container(
        height: AppSpacing.hairline,
        color: AppColors.iosSeparator(context).withValues(alpha: 0.08),
      ),
    );
  }
}
