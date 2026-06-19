import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/evidence_group.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

/// 对象页统一交集卡（V4 · 纵向交集列表）。
///
/// 三对象页共用同一结构与口径：
/// - 用户主页：`你们的交集`
/// - 地点和事物页 / 圈子页：`与你的交集`
///
/// 设计：
/// - 证据组以纵向列表行呈现：主结论 + 原因说明；
/// - 默认展示 [inlineExpandCount] 行，第一次点击展开，第二次进入全部交集；
/// - 文案、数字、实例全部来自云侧证据组，端不本地拼装事实（G2）。
///
/// 口径（必读要求 2 事实清晰）：
/// - 顶部总数 = 可见证据组 count 之和（[EvidenceGroup.totalCount]），与列表逐项一致；
/// - 维度 kind 开放字符串，未知维度优雅降级展示 label + count（必读要求 1）。
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
    this.onMoreTap,
    this.highlightKind,
  });

  static const Key cardKey = ValueKey<String>('object-intersection-card');

  final String title;
  final List<IntersectionReason> reasons;
  final bool isDark;

  /// 默认就地展开的证据组行数（真相源为 /v1/config/app，调用方传入）。
  final int inlineExpandCount;

  /// 「全部交集」入口文案；为空则不展示更多入口。
  final String? moreLabel;

  /// 连接说明副标题（由实例构成的一句话），为空则不展示。
  final String? subtitle;

  final void Function(IntersectionReason reason)? onReasonTap;
  final VoidCallback? onMoreTap;

  /// 旅程高亮（§7.3）：从 post 作者徽标跳入时携带的最强证据组 kind；
  /// 命中时该行高亮并默认展开（即便它在折叠区之外），让旅程无断点。
  final String? highlightKind;

  /// 便捷构造：把 reasons 摊平为可见证据组；无可渲染证据组返回 null（不展示，G2）。
  static Widget? fromReasons({
    required String title,
    required List<IntersectionReason>? reasons,
    required bool isDark,
    int inlineExpandCount = 3,
    String? moreLabel,
    String? subtitle,
    void Function(IntersectionReason reason)? onReasonTap,
    VoidCallback? onMoreTap,
    String? highlightKind,
    Key? key,
  }) {
    final usable = (reasons ?? const <IntersectionReason>[])
        .where((r) => EvidenceGroup.fromReason(r).isNotEmpty)
        .toList(growable: false);
    if (usable.isEmpty) return null;
    // 连接说明（§7.1）：调用方未显式传入时，回落云侧实例化 connectionSummary，
    // 端不本地拼装，缺省则不展示该行（G2）。
    final resolvedSubtitle = subtitle ?? _connectionSummaryOf(usable);
    return ObjectIntersectionCard(
      key: key ?? cardKey,
      title: title,
      reasons: usable,
      isDark: isDark,
      inlineExpandCount: inlineExpandCount,
      moreLabel: moreLabel,
      subtitle: resolvedSubtitle,
      onReasonTap: onReasonTap,
      onMoreTap: onMoreTap,
      highlightKind: highlightKind,
    );
  }

  static String? _connectionSummaryOf(List<IntersectionReason> reasons) {
    for (final r in reasons) {
      final s = r.connectionSummary.trim();
      if (s.isNotEmpty) return s;
    }
    return null;
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

    final rows = <_IntersectionRow>[];
    for (final reason in widget.reasons) {
      for (final group in EvidenceGroup.fromReason(reason)) {
        rows.add(_IntersectionRow(reason: reason, group: group));
      }
    }
    final inline = widget.inlineExpandCount <= 0 ? 3 : widget.inlineExpandCount;
    final highlight = (widget.highlightKind ?? '').trim();
    final highlightHidden =
        highlight.isNotEmpty &&
        rows.skip(inline).any((row) => row.group.kind == highlight);
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
                    isDark: widget.isDark,
                    isPrimary: i == 0,
                    highlighted:
                        highlight.isNotEmpty &&
                        visible[i].group.kind == highlight,
                    onTap: widget.onReasonTap == null
                        ? null
                        : () => widget.onReasonTap!(visible[i].reason),
                  ),
                ],
              ],
            ),
          ),
          if (hiddenCount > 0 || (expanded && rows.length > inline))
            _buildMore(context, expanded: expanded),
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

  Widget _buildMore(BuildContext context, {required bool expanded}) {
    final accent = AppColors.iosAccent(context);
    final canOpenAll = widget.moreLabel != null && widget.onMoreTap != null;
    final label = expanded
        ? (canOpenAll
              ? widget.moreLabel!
              : DiscoveryFeedText.intersectionCollapse)
        : DiscoveryFeedText.intersectionExpandMore;
    final opensAll = expanded && canOpenAll;
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: opensAll
            ? widget.onMoreTap
            : () => setState(() => _expanded = !expanded),
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
  const _IntersectionRow({required this.reason, required this.group});
  final IntersectionReason reason;
  final EvidenceGroup group;
}

/// 单行证据组：头像簇 + 短句 + 计数 + 实例 + chevron（≥44 命中区）。
class _EvidenceRow extends StatelessWidget {
  const _EvidenceRow({
    required this.row,
    required this.isDark,
    required this.isPrimary,
    this.onTap,
    this.highlighted = false,
  });

  final _IntersectionRow row;
  final bool isDark;
  final bool isPrimary;
  final VoidCallback? onTap;

  /// 旅程高亮（§7.3）：从 post 徽标跳入命中的证据组行加弱底色强调。
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    final group = row.group;
    final accent = AppColors.iosAccent(context);
    final labelColor = isPrimary ? accent : AppColors.iosLabel(context);
    final secondary = AppColors.iosSecondaryLabel(context);
    final body = ConstrainedBox(
      constraints: BoxConstraints(minHeight: AppSpacing.minInteractiveSize),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Row(
          children: <Widget>[
            _ConnectionLeadingIcon(
              fallbackKind: group.fallbackIconKind,
              isDark: isDark,
              isPrimary: isPrimary,
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          group.count > 0
                              ? '${group.label} ${group.count}'
                              : group.label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosSubheadline,
                            fontWeight: AppTypography.medium,
                            color: labelColor,
                          ),
                        ),
                      ),
                      if (group.isRecommended) ...<Widget>[
                        SizedBox(width: AppSpacing.intraGroupSm),
                        _RecommendBadge(isDark: isDark),
                      ],
                    ],
                  ),
                  if (group.sampleText.isNotEmpty) ...<Widget>[
                    SizedBox(height: AppSpacing.two),
                    Text(
                      group.sampleText,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: secondary,
                      ),
                    ),
                  ],
                ],
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

/// 连接行语义图标。主页交集模块统一用纵向列表，避免头像堆叠造成信息焦点偏移。
class _ConnectionLeadingIcon extends StatelessWidget {
  const _ConnectionLeadingIcon({
    required this.fallbackKind,
    required this.isDark,
    required this.isPrimary,
  });

  final String fallbackKind;
  final bool isDark;
  final bool isPrimary;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    final foreground = isPrimary
        ? accent
        : AppColors.iosSecondaryLabel(context);
    final background = isPrimary
        ? accent.withValues(alpha: isDark ? 0.22 : 0.12)
        : AppColors.iosFill(context);
    const size = AppSpacing.avatarUserSm;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: background, shape: BoxShape.circle),
      child: Icon(
        _fallbackIcon(fallbackKind),
        size: AppSpacing.iconSmall,
        color: foreground,
      ),
    );
  }

  IconData _fallbackIcon(String kind) {
    switch (kind) {
      case 'circle':
        return CupertinoIcons.person_3_fill;
      case 'place':
      case 'poi':
      case 'location':
        return CupertinoIcons.location_solid;
      case 'org':
      case 'organization':
      case 'school':
        return CupertinoIcons.building_2_fill;
      case 'discussion':
        return CupertinoIcons.bubble_left_bubble_right_fill;
      case 'tag':
        return CupertinoIcons.tag_fill;
      case 'link':
        return CupertinoIcons.link;
      default:
        return CupertinoIcons.person_crop_circle_fill;
    }
  }
}

/// 推荐类小角标（概率，不伪装事实）。
class _RecommendBadge extends StatelessWidget {
  const _RecommendBadge({required this.isDark});
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupXs,
        vertical: AppSpacing.hairline,
      ),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: isDark ? 0.22 : 0.12),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
      ),
      child: Text(
        DiscoveryFeedText.intersectionAffinityLabel,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: accent,
        ),
      ),
    );
  }
}
