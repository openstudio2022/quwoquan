import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/components/object_page/intersection_object_kind.dart';

/// 交集统一原子 [IntersectionEntity] 的展示密度。
///
/// - [rail]：首页/频道横滑紧凑卡（固定宽度，纵向头像在上）。
/// - [row]：inbox / 列表行（头像在左，信息在右，尾随箭头）。
enum IntersectionEntityDensity { rail, row }

/// 交集统一原子：人/地点事物/圈子/组织共用同一视觉语言。
///
/// 只读消费 [IntersectionReason]：真实头像（[IntersectionReason.avatarUrl]）+
/// 名字（[IntersectionReason.displayName]）+ 维度短标签 chip + 共同点安静 chip；
/// 概率（affinity）交集额外标注「推荐」，不伪装事实、不显示大行动按钮。
/// 导航由父层经 [onTap] 提供，本原子不直接路由 / 埋点。
class IntersectionEntity extends StatelessWidget {
  const IntersectionEntity({
    super.key,
    required this.reason,
    required this.isDark,
    this.density = IntersectionEntityDensity.row,
    this.onTap,
  });

  final IntersectionReason reason;
  final bool isDark;
  final IntersectionEntityDensity density;
  final VoidCallback? onTap;

  bool get _isAffinity => reason.intersectionClass == 'affinity';

  String get _name {
    final name = reason.displayName.trim();
    if (name.isNotEmpty) return name;
    final label = reason.label.trim();
    if (label.isNotEmpty) return label;
    // 兜底：对象页旧事实理由可能仅带 displayText（短证据句），用作名字占位。
    return reason.displayText.trim();
  }

  @override
  Widget build(BuildContext context) {
    switch (density) {
      case IntersectionEntityDensity.rail:
        return _buildRail(context);
      case IntersectionEntityDensity.row:
        return _buildRow(context);
    }
  }

  Widget _buildRow(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
        child: Row(
          children: <Widget>[
            _Avatar(
              avatarUrl: reason.avatarUrl,
              relationKind: reason.relationKind,
              size: AppSpacing.avatarUserMd,
              isDark: isDark,
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    _name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Wrap(
                    spacing: AppSpacing.intraGroupXs,
                    runSpacing: AppSpacing.intraGroupXs,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: _chips(context),
                  ),
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: AppColors.iosTertiaryLabel(context),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRail(BuildContext context) {
    final surface = AppColors.iosProfileSurface(context);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.24 : 0.1);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        width: AppSpacing.homeObjectCardMaxWidth,
        padding: EdgeInsets.all(AppSpacing.containerSm),
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
          border: Border.all(color: border, width: AppSpacing.hairline),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Row(
              children: <Widget>[
                _Avatar(
                  avatarUrl: reason.avatarUrl,
                  relationKind: reason.relationKind,
                  size: AppSpacing.avatarUserSm,
                  isDark: isDark,
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                Expanded(
                  child: Text(
                    _name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Wrap(
              spacing: AppSpacing.intraGroupXs,
              runSpacing: AppSpacing.intraGroupXs,
              children: _chips(context),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _chips(BuildContext context) {
    final chips = <Widget>[
      _Chip(
        label: UITextConstants.intersectionDimensionShortLabel(
          reason.dimension,
        ),
        tone: _ChipTone.dimension,
      ),
    ];
    if (_isAffinity) {
      chips.add(
        _Chip(
          label: reason.confidenceLabel.trim().isNotEmpty
              ? reason.confidenceLabel.trim()
              : UITextConstants.intersectionAffinityLabel,
          tone: _ChipTone.affinity,
        ),
      );
    } else if (reason.sharedCount > 0) {
      chips.add(
        _Chip(
          label: UITextConstants.intersectionSharedChip(reason.sharedCount),
          tone: _ChipTone.quiet,
        ),
      );
    }
    return chips;
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({
    required this.avatarUrl,
    required this.relationKind,
    required this.size,
    required this.isDark,
  });

  final String avatarUrl;
  final String relationKind;
  final double size;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final kind = UnifiedObjectKind.fromRelationKind(relationKind);
    final accent = AppColors.iosAccent(context);
    final radius = kind == UnifiedObjectKind.person
        ? BorderRadius.circular(size)
        : BorderRadius.circular(AppSpacing.radiusTen);
    final url = avatarUrl.trim();
    final fallback = Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: accent.withValues(alpha: isDark ? 0.22 : 0.1),
        borderRadius: radius,
      ),
      child: Icon(_iconFor(kind), size: AppSpacing.eighteen, color: accent),
    );
    if (url.isEmpty) return fallback;
    return ClipRRect(
      borderRadius: radius,
      child: Image.network(
        url,
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (_, _, _) => fallback,
      ),
    );
  }

  IconData _iconFor(UnifiedObjectKind kind) {
    switch (kind) {
      case UnifiedObjectKind.person:
        return CupertinoIcons.person_crop_circle_fill;
      case UnifiedObjectKind.place:
        return CupertinoIcons.location_solid;
      case UnifiedObjectKind.circle:
        return CupertinoIcons.person_3_fill;
      case UnifiedObjectKind.org:
        return CupertinoIcons.building_2_fill;
    }
  }
}

enum _ChipTone { dimension, quiet, affinity }

class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.tone});

  final String label;
  final _ChipTone tone;

  @override
  Widget build(BuildContext context) {
    final Color fg;
    final Color bg;
    switch (tone) {
      case _ChipTone.dimension:
        fg = AppColors.iosAccent(context);
        bg = AppColors.iosAccent(context).withValues(alpha: 0.1);
      case _ChipTone.affinity:
        fg = AppColors.iosSecondaryLabel(context);
        bg = AppColors.iosSeparator(context).withValues(alpha: 0.16);
      case _ChipTone.quiet:
        fg = AppColors.iosSecondaryLabel(context);
        bg = AppColors.iosSystemBackground(context).withValues(alpha: 0.0);
    }
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosCaption1,
          fontWeight: AppTypography.medium,
          color: fg,
        ),
      ),
    );
  }
}
