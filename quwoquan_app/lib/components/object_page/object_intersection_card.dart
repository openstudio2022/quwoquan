import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/components/object_page/intersection_statement_row.dart';

/// 对象页统一交集卡（V5 · primaryText 单通道事实列表）。
///
/// 三对象页共用同一结构与口径：
/// - 用户主页：`我与TA的交集` / `为什么推荐TA`
/// - 圈子主页：`我的交集`
/// - 实体主页：`我的交集`
///
/// 设计：
/// - 每条行只读云侧 [IntersectionReason.primaryText]；
/// - [IntersectionReason.primarySpans] 只作为同一句话的结构化富文本投影；
/// - [IntersectionReason.sampleVisuals] / [IntersectionReason.objectVisual] 进入四槽视觉；
/// - 默认展示 [inlineExpandCount] 条理由，第一次点击展开，第二次进入全部连接。
///
/// G2 红线：
/// - 不再通过 `EvidenceGroup` / `intersectionPoints` 本地拼主句；
/// - 无 [IntersectionReason.primaryText] 的 reason 直接隐藏；
/// - affinity 只能作为推荐辅助行，不伪装成事实。
class ObjectIntersectionCard extends StatefulWidget {
  const ObjectIntersectionCard({
    super.key,
    required this.title,
    required this.reasons,
    required this.isDark,
    this.inlineExpandCount = 3,
    this.moreLabel,
    this.subtitle,
    this.onReasonTap,
    this.onSpanTap,
    this.onVisualTap,
    this.onActionHintTap,
    this.onMoreTap,
    this.onInlineExpand,
    this.highlightKind,
    this.contextObjectTarget,
  });

  static const Key cardKey = ValueKey<String>('object-intersection-card');

  final String title;
  final List<IntersectionReason> reasons;
  final bool isDark;

  /// 默认就地展开的证据组行数（真相源为 /config/app，调用方传入）。
  final int inlineExpandCount;

  /// 「全部交集」入口文案；为空则不展示更多入口。
  final String? moreLabel;

  /// 连接说明副标题（由实例构成的一句话），为空则不展示。
  final String? subtitle;

  final void Function(IntersectionReason reason)? onReasonTap;
  final void Function(IntersectionReason reason, IntersectionTextSpan span)?
  onSpanTap;
  final void Function(IntersectionReason reason, IntersectionVisual visual)?
  onVisualTap;
  final void Function(IntersectionReason reason, IntersectionActionHint hint)?
  onActionHintTap;
  final VoidCallback? onMoreTap;

  /// 就地「展开」被点击（折叠→展开）时回调，携带首条可渲染 reason 供归因；
  /// 调用方据此上报 intersection_expand（behaviors.yaml 弱正信号）。
  final void Function(IntersectionReason firstReason)? onInlineExpand;
  final IntersectionTarget? contextObjectTarget;

  /// 旅程高亮（§7.3）：从 post 作者徽标跳入时携带的最强证据组 kind；
  /// 命中时该行高亮并默认展开（即便它在折叠区之外），让旅程无断点。
  final String? highlightKind;

  /// 便捷构造：只保留携带 primaryText 的理由；无可渲染理由返回 null（不展示，G2）。
  static Widget? fromReasons({
    required String title,
    required List<IntersectionReason>? reasons,
    required bool isDark,
    int inlineExpandCount = 3,
    String? moreLabel,
    String? subtitle,
    void Function(IntersectionReason reason)? onReasonTap,
    void Function(IntersectionReason reason, IntersectionTextSpan span)?
    onSpanTap,
    void Function(IntersectionReason reason, IntersectionVisual visual)?
    onVisualTap,
    void Function(IntersectionReason reason, IntersectionActionHint hint)?
    onActionHintTap,
    VoidCallback? onMoreTap,
    void Function(IntersectionReason firstReason)? onInlineExpand,
    String? highlightKind,
    IntersectionTarget? contextObjectTarget,
    Key? key,
  }) {
    final usable = (reasons ?? const <IntersectionReason>[])
        .map(
          (reason) => displayReadyIntersectionReason(
            reason,
            contextObjectTarget: contextObjectTarget,
          ),
        )
        .whereType<IntersectionReason>()
        .toList(growable: false);
    if (usable.isEmpty) return null;
    return ObjectIntersectionCard(
      key: key ?? cardKey,
      title: title,
      reasons: usable,
      isDark: isDark,
      inlineExpandCount: inlineExpandCount,
      moreLabel: moreLabel,
      subtitle: subtitle,
      onReasonTap: onReasonTap,
      onSpanTap: onSpanTap,
      onVisualTap: onVisualTap,
      onActionHintTap: onActionHintTap,
      onMoreTap: onMoreTap,
      onInlineExpand: onInlineExpand,
      highlightKind: highlightKind,
      contextObjectTarget: contextObjectTarget,
    );
  }

  @override
  State<ObjectIntersectionCard> createState() => _ObjectIntersectionCardState();
}

class _ObjectIntersectionCardState extends State<ObjectIntersectionCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.backgroundSecondary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );

    final rows = widget.reasons
        .map(
          (reason) => displayReadyIntersectionReason(
            reason,
            contextObjectTarget: widget.contextObjectTarget,
          ),
        )
        .whereType<IntersectionReason>()
        .map(_IntersectionRow.new)
        .toList(growable: false);
    if (rows.isEmpty) {
      return const SizedBox.shrink();
    }
    final inline = widget.inlineExpandCount <= 0 ? 3 : widget.inlineExpandCount;
    final highlight = (widget.highlightKind ?? '').trim();
    final highlightHidden =
        highlight.isNotEmpty &&
        rows.skip(inline).any((row) => row.matchesHighlight(highlight));
    final expanded = _expanded || highlightHidden;
    final visible = expanded ? rows : rows.take(inline).toList(growable: false);
    final hiddenCount = rows.length - visible.length;

    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyFour),
      ),
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            widget.title,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          if ((widget.subtitle ?? '').trim().isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              widget.subtitle!.trim(),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: fgSecondary,
              ),
            ),
          ],
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
                  if (i > 0) _rowDivider(),
                  _EvidenceRow(
                    row: visible[i],
                    isPrimary: i == 0,
                    contextObjectTarget: widget.contextObjectTarget,
                    highlighted:
                        highlight.isNotEmpty &&
                        visible[i].matchesHighlight(highlight),
                    onTap: widget.onReasonTap == null
                        ? null
                        : () => widget.onReasonTap!(visible[i].reason),
                    onSpanTap: widget.onSpanTap == null
                        ? null
                        : (span) => widget.onSpanTap!(visible[i].reason, span),
                    onVisualTap: widget.onVisualTap == null
                        ? null
                        : (visual) =>
                              widget.onVisualTap!(visible[i].reason, visual),
                    onActionHintTap: widget.onActionHintTap == null
                        ? null
                        : (hint) =>
                              widget.onActionHintTap!(visible[i].reason, hint),
                  ),
                ],
              ],
            ),
          ),
          if (hiddenCount > 0 ||
              (expanded && rows.length > inline) ||
              (hiddenCount == 0 &&
                  widget.moreLabel != null &&
                  widget.onMoreTap != null))
            _buildMore(
              context,
              expanded: expanded,
              forceOpenAll: hiddenCount == 0,
            ),
        ],
      ),
    );
  }

  Widget _rowDivider() {
    return Container(
      height: AppSpacing.hairline,
      margin: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
      color: AppColors.iosSeparator(
        context,
      ).withValues(alpha: widget.isDark ? 0.18 : 0.08),
    );
  }

  Widget _buildMore(
    BuildContext context, {
    required bool expanded,
    bool forceOpenAll = false,
  }) {
    final accent = AppColors.iosAccent(context);
    final canOpenAll = widget.moreLabel != null && widget.onMoreTap != null;
    final label = forceOpenAll && canOpenAll
        ? widget.moreLabel!
        : expanded
        ? (canOpenAll
              ? widget.moreLabel!
              : DiscoveryFeedText.intersectionCollapse)
        : DiscoveryFeedText.intersectionExpandMore;
    final opensAll = (forceOpenAll || expanded) && canOpenAll;
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: opensAll
            ? widget.onMoreTap
            : () {
                // 折叠→展开时回调归因（intersection_expand 弱正信号，B6）。
                if (!expanded && widget.reasons.isNotEmpty) {
                  widget.onInlineExpand?.call(widget.reasons.first);
                }
                setState(() => _expanded = !expanded);
              },
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              label,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                fontWeight: AppTypography.medium,
                color: accent,
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
            Icon(
              opensAll || !expanded
                  ? CupertinoIcons.chevron_forward
                  : CupertinoIcons.chevron_up,
              size: AppSpacing.fourteen,
              color: accent,
            ),
          ],
        ),
      ),
    );
  }
}

class _IntersectionRow {
  const _IntersectionRow(this.reason);

  final IntersectionReason reason;

  bool matchesHighlight(String value) {
    final normalized = value.trim();
    if (normalized.isEmpty) {
      return false;
    }
    return <String>{
      reason.kind.trim(),
      reason.source.trim(),
      reason.dimension.trim(),
      reason.iconKey.trim(),
      reason.intersectionId.trim(),
    }.contains(normalized);
  }

  String get auxiliaryText {
    final secondary = reason.secondaryText.trim();
    if (secondary.isNotEmpty) {
      return secondary;
    }
    final summary = reason.connectionSummary.trim();
    if (summary.isNotEmpty) {
      return summary;
    }
    if (reason.intersectionClass.trim() == 'affinity') {
      final confidence = reason.confidenceLabel.trim();
      return confidence.isNotEmpty
          ? confidence
          : DiscoveryFeedText.intersectionAffinityLabel;
    }
    return '';
  }
}

/// 单行理由：类型图标 + primaryText/spans + 样本视觉 + 对象封面 + lifecycle 弱标。
class _EvidenceRow extends StatelessWidget {
  const _EvidenceRow({
    required this.row,
    required this.isPrimary,
    this.contextObjectTarget,
    this.onTap,
    this.onSpanTap,
    this.onVisualTap,
    this.onActionHintTap,
    this.highlighted = false,
  });

  final _IntersectionRow row;
  final bool isPrimary;
  final IntersectionTarget? contextObjectTarget;
  final VoidCallback? onTap;
  final void Function(IntersectionTextSpan span)? onSpanTap;
  final void Function(IntersectionVisual visual)? onVisualTap;
  final void Function(IntersectionActionHint hint)? onActionHintTap;

  /// 旅程高亮（§7.3）：从 post 徽标跳入命中的证据组行加弱底色强调。
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    final reason = displayReadyIntersectionReason(
      row.reason,
      contextObjectTarget: contextObjectTarget,
    );
    if (reason == null) {
      return const SizedBox.shrink();
    }
    final auxiliary = row.auxiliaryText;
    final hasActionHint = reason.actionHints.any(
      isDisplayableIntersectionActionHint,
    );
    final body = IntersectionStatementRow(
      item: IntersectionStatementItem(
        primaryText: reason.primaryText.trim(),
        subtitleText: auxiliary,
        highlight: isPrimary
            ? IntersectionStatementHighlight.blue
            : IntersectionStatementHighlight.gray,
        onTap: onTap,
        spans: reason.primarySpans,
        visuals: reason.sampleVisuals,
        onSpanTap: onSpanTap ?? (onTap == null ? null : (_) => onTap!()),
        onVisualTap: onVisualTap,
        iconKey: reason.iconKey,
        sourceRef: resolvedIntersectionReasonKind(reason),
        dimension: reason.dimension,
        objectVisual: reason.objectVisual,
        actionHints: reason.actionHints,
        onActionHintTap: onActionHintTap,
        lifecycleState: reason.lifecycleState,
        strengthDelta: reason.strengthDelta.round(),
        showAuxiliaryLine: auxiliary.isNotEmpty || hasActionHint,
      ),
    );
    if (!highlighted) return body;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 240),
      curve: Curves.easeOutCubic,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.intraGroupSm),
      decoration: BoxDecoration(
        color: AppColors.iosAccent(context).withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
      ),
      child: body,
    );
  }
}
