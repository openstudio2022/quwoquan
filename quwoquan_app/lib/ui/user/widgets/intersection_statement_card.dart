import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_propagation_path.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/components/object_page/intersection_icon_resolver.dart';
import 'package:quwoquan_app/components/object_page/intersection_lifecycle_badge.dart';
import 'package:quwoquan_app/components/object_page/intersection_object_cover.dart';
import 'package:quwoquan_app/components/object_page/intersection_propagation_view.dart';
import 'package:quwoquan_app/components/object_page/intersection_visual_cluster.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

enum IntersectionStatementHighlight { blue, gray }

/// 一条交集结论行（统一交互子契约 · A–E 横切复用，Phase 0 §20.7 + 架构基线 v2 §21.5）。
///
/// [primaryText] 为单通道真相源（云侧 primaryText / briefText），[spans] 为同一句话的
/// 结构化富文本切分（云侧产出，端不拼装，G2）；端侧降级链 spans → primaryText → 隐藏。
/// [visuals] 为对象级样本视觉（sampleVisuals），经 [IntersectionVisualCluster] 渲染。
///
/// 四槽具象化（§21.5.1，全部可选、向后兼容）：
/// - 槽①类型图标：[iconKey]/[sourceRef]/[dimension] 任一可解析时渲染 leading 类型图标；
/// - 槽②句内头像：由 [spans] 内 `visual` 字段驱动（[InteractiveIntersectionText] 内联）；
/// - 槽③对象封面：[objectVisual] 非空时渲染 trailing 封面（替代 chevron）；
/// - 槽④生命周期弱标：[lifecycleState]（+ [strengthDelta]）驱动弱标/红点。
///
/// [propagationPath] 非空时（我的影响力 / 圈子影响），主句下方渲染传播视图（替代 subtitle 行）。
class IntersectionStatementItem {
  const IntersectionStatementItem({
    required this.primaryText,
    required this.subtitleText,
    this.highlight = IntersectionStatementHighlight.gray,
    this.onTap,
    this.spans = const <IntersectionTextSpan>[],
    this.visuals = const <IntersectionVisual>[],
    this.onSpanTap,
    this.onVisualTap,
    this.iconKey = '',
    this.sourceRef = '',
    this.dimension = '',
    this.objectVisual,
    this.lifecycleState = '',
    this.strengthDelta = 0,
    this.dotOnlyForNew = false,
    this.propagationPath,
    this.onPropagationTap,
    this.showAuxiliaryLine = true,
  });

  final String primaryText;
  final String subtitleText;
  final IntersectionStatementHighlight highlight;

  /// 整行点击（名字/数字片段未命中时的兜底进入，优先级低于片段点击）。
  final VoidCallback? onTap;

  /// 同一句话的结构化富文本切分（云侧产出）；为空时整行降级渲染 [primaryText]。
  final List<IntersectionTextSpan> spans;

  /// 对象级样本视觉（最多 3 个 + 计数）。
  final List<IntersectionVisual> visuals;

  /// 命中可点击片段（role=object 进对象页 / role=count 进维度或明细）。
  final void Function(IntersectionTextSpan span)? onSpanTap;

  /// 命中样本视觉（进对象页）。
  final void Function(IntersectionVisual visual)? onVisualTap;

  /// 槽① 类型图标语义键（云侧 iconKey）；缺省时回退 [sourceRef]/[dimension]。
  final String iconKey;

  /// 槽① 类型图标回退用标准 kind（sourceRef）。
  final String sourceRef;

  /// 槽① 类型图标末级回退用维度（5 维闭集）。
  final String dimension;

  /// 槽③ 对象封面（结论句所指对象的封面/缩略图）；非空时走四槽布局。
  final IntersectionVisual? objectVisual;

  /// 槽④ 生命周期状态（new/strengthened/stable/weakened/reactivated）。
  final String lifecycleState;

  /// 槽④ strengthened 态增量（叠加 +N）。
  final int strengthDelta;

  /// 紧凑面下 new 仅渲染红点。
  final bool dotOnlyForNew;

  /// 传播视图（我的影响力 / 圈子影响）；非空时主句下方渲染。
  final IntersectionPropagationPath? propagationPath;

  /// 命中传播结论句。
  final VoidCallback? onPropagationTap;

  /// 是否显示主句下方辅助层；主页高保行只展示一行主文案时关闭。
  final bool showAuxiliaryLine;

  bool get _hasTypeIcon =>
      iconKey.trim().isNotEmpty ||
      sourceRef.trim().isNotEmpty ||
      dimension.trim().isNotEmpty;

  bool get _hasObjectCover => objectVisual != null;

  bool get _hasPropagation =>
      propagationPath != null && propagationPath!.summaryText.trim().isNotEmpty;

  /// 句内是否已携带头像（槽②）——此时 leading 视觉簇冗余。
  bool get _hasInlineSpanVisuals => spans.any(
    (s) => s.visual != null && s.visual!.imageUrl.trim().isNotEmpty,
  );

  /// 头像已由槽②/槽③/传播节点承载时，抑制 leading 视觉簇，避免重复。
  bool get _suppressLeadingCluster =>
      _hasPropagation || _hasObjectCover || _hasInlineSpanVisuals;
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
    this.topDivider = false,
  });

  final String title;
  final List<IntersectionStatementItem> items;
  final Widget? titleBadge;
  final Widget? emptyChild;
  final int collapsedMaxItems;
  final EdgeInsetsGeometry? padding;

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
  static const double _sectionAccentWidth = 3.0;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final separator = AppColors.iosSeparator(context);
    final cardBorder = separator.withValues(alpha: isDark ? 0.14 : 0.07);
    final cardShadow = AppColors.black.withValues(alpha: isDark ? 0.10 : 0.018);
    final accentColor = AppColors.iosAccent(
      context,
    ).withValues(alpha: isDark ? 0.82 : 0.68);
    final visible = _expanded
        ? widget.items
        : widget.items.take(widget.collapsedMaxItems).toList(growable: false);
    final hasMore = widget.items.length > widget.collapsedMaxItems;

    // 区块标题（深色 label）：iOS 分组头，轻量蓝色短线只做“交集资产”锚点。
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

class IntersectionStatementRow extends StatelessWidget {
  const IntersectionStatementRow({super.key, required this.item});

  final IntersectionStatementItem item;

  @override
  Widget build(BuildContext context) {
    final primaryColor = item.highlight == IntersectionStatementHighlight.blue
        ? AppColors.iosAccent(context)
        : AppColors.iosLabel(context);
    final metaSurface = AppColors.iosSecondaryFill(context).withValues(
      alpha: CupertinoTheme.of(context).brightness == Brightness.dark
          ? 0.20
          : 0.28,
    );
    final subtitle = item.subtitleText.trim().isNotEmpty
        ? item.subtitleText.trim()
        : UITextConstants.profileStatementFallbackSubtitle;
    final hasSpans = item.spans.isNotEmpty;
    // 头像已由槽②（句内头像）/槽③（对象封面）/传播节点承载时不再渲染 leading 视觉簇，
    // 避免重复；否则继续渲染 leading 簇服务通用消费者。
    final hasVisuals = item.visuals.isNotEmpty && !item._suppressLeadingCluster;
    final Widget primaryLine = hasSpans
        ? InteractiveIntersectionText(
            spans: item.spans,
            fallbackText: item.primaryText.trim(),
            onSpanTap: item.onSpanTap,
            baseStyle: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              height: AppSpacing.textLineHeightFootnote,
              fontWeight: AppTypography.regular,
              color: AppColors.iosLabel(context),
              letterSpacing: -0.08,
            ),
            accentFontWeight: AppTypography.regular,
          )
        : Text(
            item.primaryText.trim(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              height: AppSpacing.textLineHeightFootnote,
              fontWeight: AppTypography.regular,
              color: primaryColor,
              letterSpacing: -0.08,
            ),
          );
    // 槽④ 生命周期弱标（new/strengthened/reactivated 才渲染；其余零尺寸）。
    const lifecycleVisibleStates = <String>{
      'new',
      'strengthened',
      'reactivated',
    };
    final lifecycleVisible = lifecycleVisibleStates.contains(
      item.lifecycleState.trim(),
    );
    final lifecycleBadge = IntersectionLifecycleBadge(
      lifecycleState: item.lifecycleState,
      strengthDelta: item.strengthDelta,
      dotOnlyForNew: item.dotOnlyForNew,
    );
    // 主句下方辅助行：传播视图（我的影响力/圈子影响）优先，否则维度副句胶囊。
    final Widget auxiliaryLine = item._hasPropagation
        ? IntersectionPropagationView(
            path: item.propagationPath!,
            onSummaryTap: item.onPropagationTap ?? item.onTap,
            onNodeTap: item.onVisualTap,
          )
        : Align(
            alignment: Alignment.centerLeft,
            child: Container(
              constraints: BoxConstraints(
                maxWidth: MediaQuery.sizeOf(context).width * 0.68,
              ),
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerXs,
                vertical: AppSpacing.intraGroupXs / 2,
              ),
              decoration: BoxDecoration(
                color: metaSurface,
                borderRadius: BorderRadius.circular(
                  AppSpacing.smallBorderRadius,
                ),
              ),
              child: Text(
                subtitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption2,
                  height: AppSpacing.textLineHeightCaption,
                  color: AppColors.iosTertiaryLabel(context),
                  letterSpacing: -0.02,
                ),
              ),
            ),
          );
    final content = ConstrainedBox(
      constraints: BoxConstraints(minHeight: AppSpacing.minInteractiveSize + 8),
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.containerXs),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: <Widget>[
            // 槽① 类型图标（四槽布局 leading）。
            if (item._hasTypeIcon) ...<Widget>[
              IntersectionTypeIcon(
                iconKey: item.iconKey,
                sourceRef: item.sourceRef,
                dimension: item.dimension,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
            ],
            // 旧布局 leading 视觉簇（无类型图标时保留，向后兼容）。
            if (hasVisuals) ...<Widget>[
              IntersectionVisualCluster(
                visuals: item.visuals,
                size: AppSpacing.avatarUserSm,
                onVisualTap: item.onVisualTap,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  primaryLine,
                  if (item.showAuxiliaryLine) ...<Widget>[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    auxiliaryLine,
                  ],
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            // 槽③ 对象封面（+ 槽④ overlay）替代 chevron；否则弱标独立 + chevron。
            if (item._hasObjectCover)
              IntersectionObjectCover(
                visual: item.objectVisual!,
                lifecycleBadge: lifecycleBadge,
                onTap: item.onTap,
              )
            else ...<Widget>[
              if (lifecycleVisible) ...<Widget>[
                lifecycleBadge,
                SizedBox(width: AppSpacing.intraGroupXs),
              ],
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconXSmall,
                color: AppColors.iosQuaternaryLabel(context),
              ),
            ],
          ],
        ),
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
