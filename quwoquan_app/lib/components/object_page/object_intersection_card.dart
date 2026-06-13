import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/evidence_group.dart';
import 'package:quwoquan_app/components/object_page/intersection_object_kind.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 对象页统一交集卡（V4 · 人脸抽屉列表）。
///
/// 三对象页共用同一结构与口径：
/// - 用户主页：`你们的连接`
/// - 地点和事物页 / 圈子页：`与你的连接`
///
/// 设计（专业设计师视角：精致 / 美观 / 事实清晰 / 简洁）：
/// - 去火花图标；标题右侧总数为中性大字，非彩色；
/// - 证据组以「抽屉列表行」呈现：头像簇 + 短句名词 + 计数 + 一个实例 + chevron；
/// - 默认展示 [inlineExpandCount] 行，超出以「全部交集」就地/跳转展开（混合策略）；
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
    return LayoutBuilder(
      builder: (context, constraints) {
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
        final total = rows.fold<int>(0, (sum, r) => sum + r.group.count);
        final inline = widget.inlineExpandCount <= 0
            ? 3
            : widget.inlineExpandCount;
        // 旅程高亮（§7.3）：命中 highlightKind 时强制展开，确保该证据组可见。
        final highlight = (widget.highlightKind ?? '').trim();
        final highlightHidden =
            highlight.isNotEmpty &&
            rows.skip(inline).any((r) => r.group.kind == highlight);
        final expanded = _expanded || highlightHidden;
        final visible = expanded
            ? rows
            : rows.take(inline).toList(growable: false);
        final primaryReason = rows.isEmpty ? null : rows.first.reason;
        final hiddenCount = rows.length - visible.length;
        final screenWidth = MediaQuery.sizeOf(context).width;
        final layoutWidth =
            constraints.hasBoundedWidth && constraints.maxWidth > 0
            ? constraints.maxWidth
            : screenWidth;
        final isWideLayout =
            screenWidth >= AppSpacing.webPcReadingMaxWidth &&
            layoutWidth >= AppSpacing.webPcReadingMinWidth;
        if (isWideLayout) {
          return _buildWideCard(
            context: context,
            surface: surface,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
            rows: rows,
            total: total,
            highlight: highlight,
          );
        }

        return Container(
          decoration: BoxDecoration(
            color: surface,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      widget.title,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.semiBold,
                        color: fgPrimary,
                      ),
                    ),
                  ),
                  if (total > 0)
                    Text(
                      '$total',
                      style: TextStyle(
                        fontSize: AppTypography.iosTitle3,
                        fontWeight: AppTypography.bold,
                        color: fgPrimary,
                        height: AppSpacing.textLineHeightSingle,
                      ),
                    ),
                ],
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
              // §7.5 就地展开：280ms easeOutCubic 高度过渡。
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
                _buildMore(
                  context,
                  hiddenCount: hiddenCount,
                  expanded: expanded,
                ),
              if (primaryReason != null) ...<Widget>[
                SizedBox(height: AppSpacing.intraGroupSm),
                _IntersectionCta(
                  reason: primaryReason,
                  isDark: widget.isDark,
                  onTap: widget.onReasonTap == null
                      ? null
                      : () => widget.onReasonTap!(primaryReason),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _buildWideCard({
    required BuildContext context,
    required Color surface,
    required Color fgPrimary,
    required Color fgSecondary,
    required List<_IntersectionRow> rows,
    required int total,
    required String highlight,
  }) {
    final wideHighlightHidden =
        highlight.isNotEmpty &&
        rows.skip(1).any((r) => r.group.kind == highlight);
    final wideExpanded = _expanded || wideHighlightHidden;
    final primaryRow = rows.first;
    final primaryReason = primaryRow.reason;
    final kind = UnifiedObjectKind.resolve(
      objectKind: primaryReason.objectKind,
      relationKind: primaryReason.relationKind,
    );
    final coverName = primaryReason.displayName.trim().isNotEmpty
        ? primaryReason.displayName.trim()
        : primaryReason.label.trim();
    final coverUrl = primaryReason.avatarUrl.trim();
    final extraRows = rows.skip(1).toList(growable: false);
    final remainingCount = extraRows.length;
    final secondaryLabel = extraRows.isNotEmpty
        ? (extraRows.first.group.label.trim().isNotEmpty
              ? extraRows.first.group.label.trim()
              : extraRows.first.group.sampleText.trim())
        : primaryRow.group.sampleText.trim();

    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(
          color: AppColors.iosSeparator(
            context,
          ).withValues(alpha: widget.isDark ? 0.18 : 0.08),
          width: AppSpacing.hairline,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          widget.title,
                          style: TextStyle(
                            fontSize: AppTypography.iosSubheadline,
                            fontWeight: AppTypography.semiBold,
                            color: fgPrimary,
                          ),
                        ),
                      ),
                      if (total > 0)
                        Text(
                          '$total',
                          style: TextStyle(
                            fontSize: AppTypography.iosTitle3,
                            fontWeight: AppTypography.bold,
                            color: fgPrimary,
                            height: AppSpacing.textLineHeightSingle,
                          ),
                        ),
                    ],
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  _buildWideCoverTile(
                    context: context,
                    kind: kind,
                    coverUrl: coverUrl,
                    primaryRow: primaryRow,
                    secondaryLabel: secondaryLabel,
                    remainingCount: remainingCount,
                    recommended: primaryRow.group.isRecommended,
                  ),
                  SizedBox(height: AppSpacing.containerSm),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          coverName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosSubheadline,
                            fontWeight: AppTypography.semiBold,
                            color: fgPrimary,
                            height: AppTypography.lineHeightTight,
                          ),
                        ),
                      ),
                    ],
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
                  if (remainingCount > 0) ...<Widget>[
                    SizedBox(height: AppSpacing.intraGroupSm),
                    _buildMore(
                      context,
                      hiddenCount: remainingCount,
                      expanded: wideExpanded,
                    ),
                  ],
                  if (wideExpanded && extraRows.isNotEmpty) ...<Widget>[
                    SizedBox(height: AppSpacing.intraGroupSm),
                    AnimatedSize(
                      duration: const Duration(milliseconds: 280),
                      curve: Curves.easeOutCubic,
                      alignment: Alignment.topCenter,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: <Widget>[
                          for (
                            var i = 0;
                            i < extraRows.length;
                            i++
                          ) ...<Widget>[
                            if (i > 0) _rowDivider(),
                            _EvidenceRow(
                              row: extraRows[i],
                              isDark: widget.isDark,
                              highlighted:
                                  highlight.isNotEmpty &&
                                  extraRows[i].group.kind == highlight,
                              onTap: widget.onReasonTap == null
                                  ? null
                                  : () => widget.onReasonTap!(
                                      extraRows[i].reason,
                                    ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                  SizedBox(height: AppSpacing.intraGroupSm),
                  _IntersectionCta(
                    reason: primaryReason,
                    isDark: widget.isDark,
                    onTap: widget.onReasonTap == null
                        ? null
                        : () => widget.onReasonTap!(primaryReason),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildWideCoverTile({
    required BuildContext context,
    required UnifiedObjectKind kind,
    required String coverUrl,
    required _IntersectionRow primaryRow,
    required String secondaryLabel,
    required int remainingCount,
    required bool recommended,
  }) {
    final surface = AppColors.iosSystemBackground(context);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: widget.isDark ? 0.22 : 0.1);
    final fill = AppColors.iosFill(context);
    final cover = kind == UnifiedObjectKind.person
        ? _personCover(context, coverUrl, fill)
        : _objectCover(coverUrl, fill);
    final primary = primaryRow.group;
    final primaryLabel = primary.label.trim();
    return SizedBox(
      height: AppSpacing.objectIntersectionCardWideCoverHeight,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(
            AppSpacing.contentPreviewCornerRadius,
          ),
          border: Border.all(color: border, width: AppSpacing.hairline),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(
            AppSpacing.contentPreviewCornerRadius,
          ),
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              cover,
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: <Color>[
                        AppColors.black.withValues(alpha: 0.04),
                        AppColors.black.withValues(alpha: 0.18),
                        AppColors.black.withValues(alpha: 0.5),
                      ],
                      stops: const <double>[0.0, 0.58, 1.0],
                    ),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.all(AppSpacing.containerSm),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: <Widget>[
                    if (primaryLabel.isNotEmpty)
                      Text(
                        primary.count > 0
                            ? '$primaryLabel · ${primary.count}'
                            : primaryLabel,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosSubheadline,
                          fontWeight: AppTypography.semiBold,
                          color: AppColors.white,
                          height: AppSpacing.textLineHeightSingle,
                        ),
                      ),
                    if (secondaryLabel.isNotEmpty) ...<Widget>[
                      SizedBox(height: AppSpacing.two),
                      Text(
                        secondaryLabel,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          color: AppColors.white.withValues(alpha: 0.88),
                          height: AppSpacing.textLineHeightCompact,
                        ),
                      ),
                    ] else if (remainingCount > 0) ...<Widget>[
                      SizedBox(height: AppSpacing.two),
                      Text(
                        '还有 $remainingCount 项',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          color: AppColors.white.withValues(alpha: 0.88),
                          height: AppSpacing.textLineHeightCompact,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (recommended)
                Positioned(
                  top: AppSpacing.intraGroupXs,
                  right: AppSpacing.intraGroupXs,
                  child: _RecommendBadge(isDark: widget.isDark),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _personCover(BuildContext context, String url, Color fill) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            AppColors.iosAccent(context).withValues(alpha: 0.16),
            fill,
          ],
        ),
      ),
      child: Center(
        child: Container(
          width: AppSpacing.avatarUserMd,
          height: AppSpacing.avatarUserMd,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: AppColors.iosSystemBackground(context),
              width: AppSpacing.hairline * 2,
            ),
          ),
          child: ClipOval(
            child: url.isEmpty
                ? ColoredBox(
                    color: fill,
                    child: Icon(
                      CupertinoIcons.person_crop_circle_fill,
                      size: AppSpacing.iconMedium,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  )
                : AppCachedNetworkImage(
                    imageUrl: url,
                    fit: BoxFit.cover,
                    errorWidget: ColoredBox(color: fill),
                  ),
          ),
        ),
      ),
    );
  }

  Widget _objectCover(String url, Color fill) {
    if (url.isEmpty) {
      return ColoredBox(color: fill);
    }
    return AppCachedNetworkImage(
      imageUrl: url,
      fit: BoxFit.cover,
      errorWidget: ColoredBox(color: fill),
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
    required int hiddenCount,
    required bool expanded,
  }) {
    final accent = AppColors.iosAccent(context);
    // 混合策略：有 onMoreTap（跳列表页）优先；否则就地展开/收起。
    final goRoute = widget.moreLabel != null && widget.onMoreTap != null;
    final label = goRoute
        ? widget.moreLabel!
        : (expanded
              ? UITextConstants.intersectionCollapse
              : '$hiddenCount ${UITextConstants.intersectionExpandMore}');
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: goRoute
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
              goRoute || !expanded
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

class _IntersectionCta extends StatelessWidget {
  const _IntersectionCta({
    required this.reason,
    required this.isDark,
    this.onTap,
  });

  final IntersectionReason reason;
  final bool isDark;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final label = _ctaLabelFor(reason);
    final subtitle = _ctaSubtitleFor(reason);
    final fg = AppColors.iosAccent(context);
    return GestureDetector(
      key: const ValueKey<String>('object-intersection-primary-cta'),
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: fg.withValues(alpha: isDark ? 0.18 : 0.10),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          child: Row(
            children: <Widget>[
              Icon(
                CupertinoIcons.arrow_right_circle,
                size: AppSpacing.iconSmall,
                color: fg,
              ),
              SizedBox(width: AppSpacing.intraGroupXs),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        fontWeight: AppTypography.semiBold,
                        color: fg,
                      ),
                    ),
                    if (subtitle.isNotEmpty) ...<Widget>[
                      SizedBox(height: AppSpacing.two),
                      Text(
                        subtitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosCaption2,
                          color: AppColors.iosSecondaryLabel(context),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String _ctaLabelFor(IntersectionReason reason) {
  switch (reason.actionType.trim()) {
    case 'follow_author':
      return UITextConstants.objectIntersectionCtaFollowAuthor;
    case 'join_circle':
      return UITextConstants.objectIntersectionCtaJoinCircle;
    case 'add_contact':
      return UITextConstants.objectIntersectionCtaAddContact;
    case 'ask_xiaoqu':
      return UITextConstants.objectIntersectionCtaAskAssistant;
    case 'view_object':
    default:
      return UITextConstants.objectIntersectionCtaView;
  }
}

String _ctaSubtitleFor(IntersectionReason reason) {
  final summary = reason.connectionSummary.trim();
  if (summary.isNotEmpty) return summary;
  final label = reason.label.trim();
  if (label.isNotEmpty) return '因为 $label 推荐给你';
  final displayName = reason.displayName.trim();
  if (displayName.isNotEmpty) return '继续了解 $displayName';
  return '';
}

/// 单行证据组：头像簇 + 短句 + 计数 + 实例 + chevron（≥44 命中区）。
class _EvidenceRow extends StatelessWidget {
  const _EvidenceRow({
    required this.row,
    required this.isDark,
    this.onTap,
    this.highlighted = false,
  });

  final _IntersectionRow row;
  final bool isDark;
  final VoidCallback? onTap;

  /// 旅程高亮（§7.3）：从 post 徽标跳入命中的证据组行加弱底色强调。
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    final group = row.group;
    final labelColor = AppColors.iosLabel(context);
    final secondary = AppColors.iosSecondaryLabel(context);
    final body = ConstrainedBox(
      constraints: BoxConstraints(minHeight: AppSpacing.minInteractiveSize),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Row(
          children: <Widget>[
            _AvatarCluster(
              urls: group.sampleAvatarUrls,
              fallbackKind: group.fallbackIconKind,
              isDark: isDark,
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Row(
                children: <Widget>[
                  Flexible(
                    child: Text(
                      group.label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.medium,
                        color: labelColor,
                      ),
                    ),
                  ),
                  if (group.count > 0) ...<Widget>[
                    SizedBox(width: AppSpacing.intraGroupXs),
                    Text(
                      '${group.count}',
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.semiBold,
                        color: labelColor,
                      ),
                    ),
                  ],
                  if (group.isRecommended) ...<Widget>[
                    SizedBox(width: AppSpacing.intraGroupSm),
                    _RecommendBadge(isDark: isDark),
                  ],
                ],
              ),
            ),
            if (group.sampleText.isNotEmpty) ...<Widget>[
              SizedBox(width: AppSpacing.intraGroupSm),
              ConstrainedBox(
                constraints: BoxConstraints(maxWidth: AppSpacing.oneHundred),
                child: Text(
                  group.sampleText,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.right,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: secondary,
                  ),
                ),
              ),
            ],
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

/// 头像簇（≤3 叠压），真实的人/对象信号；无头像时按对象类型回落图标。
class _AvatarCluster extends StatelessWidget {
  const _AvatarCluster({
    required this.urls,
    required this.fallbackKind,
    required this.isDark,
  });

  final List<String> urls;
  final String fallbackKind;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final size = AppSpacing.avatarUserSm;
    final ringColor = AppColors.iosSystemBackground(context);
    final shown = urls.take(3).toList(growable: false);
    if (shown.isEmpty) {
      return _avatarRing(
        context,
        size: size,
        ringColor: ringColor,
        child: ColoredBox(
          color: AppColors.iosFill(context),
          child: Icon(
            _fallbackIcon(fallbackKind),
            size: AppSpacing.iconSmall,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      );
    }
    final overlap = size * 0.62;
    final width = size + (shown.length - 1) * overlap;
    return SizedBox(
      width: width,
      height: size,
      child: Stack(
        children: <Widget>[
          for (var i = 0; i < shown.length; i++)
            Positioned(
              left: i * overlap,
              child: _avatarRing(
                context,
                size: size,
                ringColor: ringColor,
                child: AppCachedNetworkImage(
                  imageUrl: shown[i],
                  fit: BoxFit.cover,
                  errorWidget: ColoredBox(color: AppColors.iosFill(context)),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _avatarRing(
    BuildContext context, {
    required double size,
    required Color ringColor,
    required Widget child,
  }) {
    return Container(
      width: size,
      height: size,
      padding: EdgeInsets.all(AppSpacing.hairline * 1.5),
      decoration: BoxDecoration(color: ringColor, shape: BoxShape.circle),
      child: ClipOval(child: child),
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
        UITextConstants.intersectionAffinityLabel,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: accent,
        ),
      ),
    );
  }
}
