import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 对象页统一交集卡（V3，合规共享层）。
///
/// 三对象页共用同一结构与口径：
/// - 用户主页：`你们的交集`
/// - 地点和事物页：`你和这里的交集`
/// - 圈子/组织页：`你认识的人有 N 个在这`
///
/// 文案口径约束（全局验收 G2 / 军规 R27）：
/// - 标题 [title]、更多入口文案 [moreLabel] 由调用方按对象类型传入（UITextConstants / l10n），
///   组件本身不硬编码业务中文；
/// - 每条交集点通过证据胶囊渲染（维度 + 云侧证据短句），端不本地拼装事实；
/// - 无来源（reasons 为空或无可渲染身份）→ [fromReasons] 返回 null，调用方据此不展示。
class ObjectIntersectionCard extends StatelessWidget {
  const ObjectIntersectionCard({
    super.key,
    required this.title,
    required this.reasons,
    required this.isDark,
    this.sharedCount,
    this.maxVisible = 3,
    this.moreLabel,
    this.onReasonTap,
    this.onMoreTap,
  });

  static const Key cardKey = ValueKey<String>('object-intersection-card');

  final String title;
  final List<IntersectionReason> reasons;
  final bool isDark;

  /// 交集点总数（如「128 个交集点」中的 128），来自云侧；不展示则传 null。
  final int? sharedCount;
  final int maxVisible;

  /// 「查看全部」入口文案（调用方传 UITextConstants）；为空则不展示更多入口。
  final String? moreLabel;
  final void Function(IntersectionReason reason)? onReasonTap;
  final VoidCallback? onMoreTap;

  /// 便捷构造：过滤无可渲染身份（displayName/label/displayText 全空）的来源，
  /// 全空则返回 null（不展示，保证 G2）。
  static Widget? fromReasons({
    required String title,
    required List<IntersectionReason>? reasons,
    required bool isDark,
    int? sharedCount,
    int maxVisible = 3,
    String? moreLabel,
    void Function(IntersectionReason reason)? onReasonTap,
    VoidCallback? onMoreTap,
    Key? key,
  }) {
    final usable = (reasons ?? const <IntersectionReason>[])
        .where(
          (r) =>
              r.displayName.trim().isNotEmpty ||
              r.label.trim().isNotEmpty ||
              r.displayText.trim().isNotEmpty,
        )
        .toList();
    if (usable.isEmpty) return null;
    return ObjectIntersectionCard(
      key: key ?? cardKey,
      title: title,
      reasons: usable,
      isDark: isDark,
      sharedCount: sharedCount,
      maxVisible: maxVisible,
      moreLabel: moreLabel,
      onReasonTap: onReasonTap,
      onMoreTap: onMoreTap,
    );
  }

  @override
  Widget build(BuildContext context) {
    final accent = isDark ? AppColors.iosAccentDark : AppColors.primaryColor;
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final visible = reasons.take(maxVisible).toList();
    final hasMore =
        moreLabel != null && onMoreTap != null && reasons.length > maxVisible;
    final effectiveSharedCount =
        sharedCount ??
        reasons.fold<int>(0, (sum, reason) => sum + reason.totalPointCount);

    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(
                CupertinoIcons.sparkles,
                size: AppSpacing.iconMedium,
                color: accent,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: AppTypography.semiBold,
                    color: fgPrimary,
                  ),
                ),
              ),
              if (effectiveSharedCount > 0)
                Text(
                  '$effectiveSharedCount',
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.bold,
                    color: accent,
                  ),
                ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            _summaryLine(visible),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          Wrap(
            spacing: AppSpacing.intraGroupSm,
            runSpacing: AppSpacing.intraGroupSm,
            children: visible
                .map(
                  (r) => _EvidencePill(
                    reason: r,
                    isDark: isDark,
                    onTap: onReasonTap == null ? null : () => onReasonTap!(r),
                  ),
                )
                .toList(growable: false),
          ),
          if (hasMore) ...[
            SizedBox(height: AppSpacing.intraGroupSm),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onMoreTap,
              child: Text(
                moreLabel!,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.medium,
                  color: accent,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _summaryLine(List<IntersectionReason> visible) {
    final labels = visible
        .map(_evidenceLabel)
        .where((label) => label.trim().isNotEmpty)
        .take(3)
        .toList(growable: false);
    if (labels.isEmpty) return title;
    return labels.join(' · ');
  }
}

class _EvidencePill extends StatelessWidget {
  const _EvidencePill({required this.reason, required this.isDark, this.onTap});

  final IntersectionReason reason;
  final bool isDark;
  final VoidCallback? onTap;

  bool get _isAffinity => reason.intersectionClass == 'affinity';

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    final bg = AppColors.iosSystemBackground(
      context,
    ).withValues(alpha: isDark ? 0.32 : 0.76);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.24 : 0.1);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        constraints: BoxConstraints(maxWidth: AppSpacing.twoHundredTwenty),
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupSm,
        ),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
          border: Border.all(color: border, width: AppSpacing.hairline),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              _dimensionIcon(reason.dimension),
              size: AppSpacing.iconSmall,
              color: _isAffinity
                  ? AppColors.iosSecondaryLabel(context)
                  : accent,
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
            Flexible(
              child: Text(
                '${_dimensionLabel(reason)} ${_pointCountLabel(reason)} ${_evidenceLabel(reason)}'
                    .trim(),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  fontWeight: AppTypography.medium,
                  color: AppColors.iosLabel(context),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _dimensionLabel(IntersectionReason reason) {
  if (reason.intersectionClass == 'affinity') {
    final pointLabel = reason.pointClassLabel.trim();
    if (pointLabel.isNotEmpty) return pointLabel;
    final confidence = reason.confidenceLabel.trim();
    return confidence.isNotEmpty
        ? confidence
        : UITextConstants.intersectionAffinityLabel;
  }
  return UITextConstants.intersectionDimensionShortLabel(reason.dimension);
}

String _evidenceLabel(IntersectionReason reason) {
  final text = reason.displayText.trim();
  if (text.isNotEmpty) return text;
  final label = reason.label.trim();
  if (label.isNotEmpty) return label;
  return reason.displayName.trim();
}

String _pointCountLabel(IntersectionReason reason) {
  final total = reason.totalPointCount;
  if (total <= 0) return '';
  if (reason.recommendedPointCount > 0 && reason.factPointCount == 0) {
    return '$total 个推荐交集点';
  }
  return '$total 个交集点';
}

IconData _dimensionIcon(String dimension) {
  switch (dimension) {
    case 'identity':
      return CupertinoIcons.person_crop_rectangle;
    case 'location':
      return CupertinoIcons.location_solid;
    case 'content':
      return CupertinoIcons.doc_text_fill;
    case 'relationship':
      return CupertinoIcons.person_2_fill;
    case 'interest':
      return CupertinoIcons.sparkles;
    default:
      return CupertinoIcons.circle_grid_hex;
  }
}
