import 'package:flutter/cupertino.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 统一交集样本视觉簇（统一交互子契约 · A–E 横切复用，Phase 0 §20.7）。
///
/// 只读消费云侧 [IntersectionVisual] 列表，按 `assetKind` 渲染头像簇 / 圈子封面 / 校徽 /
/// logo / 缩略图，最多 [maxVisuals] 个（默认 3），超出以「+N」计数收口。
/// 形状由 `assetKind` 决定（avatar/circleAvatar/emblem 等圆形，cover/thumbnail 等圆角矩形），
/// 禁用用户头像冒充非用户对象——非用户视觉走对象级资产或对应占位图标。
/// 片段携带 `target` 时可点击进对象页（命中 [onVisualTap]）。`visuals` 为空时隐藏。
class IntersectionVisualCluster extends StatelessWidget {
  const IntersectionVisualCluster({
    super.key,
    required this.visuals,
    this.maxVisuals = 3,
    this.size,
    this.onVisualTap,
  });

  final List<IntersectionVisual> visuals;
  final int maxVisuals;
  final double? size;
  final void Function(IntersectionVisual visual)? onVisualTap;

  @override
  Widget build(BuildContext context) {
    final shown = visuals.take(maxVisuals).toList(growable: false);
    if (shown.isEmpty) {
      return const SizedBox.shrink();
    }
    final remaining = visuals.length - shown.length;
    final diameter = size ?? AppSpacing.avatarUserSm;
    // 32% 重叠：相邻视觉左缘步进 = 直径 * 0.68。
    final step = diameter * 0.68;
    final badgeCount = shown.length + (remaining > 0 ? 1 : 0);
    final width = diameter + (badgeCount - 1) * step;
    final ringColor = AppColors.iosSystemBackground(context);

    return SizedBox(
      width: width,
      height: diameter,
      child: Stack(
        clipBehavior: Clip.none,
        children: <Widget>[
          for (var i = 0; i < shown.length; i += 1)
            Positioned(
              left: i * step,
              child: _VisualBadge(
                visual: shown[i],
                size: diameter,
                ringColor: ringColor,
                onTap: onVisualTap == null
                    ? null
                    : () => onVisualTap!(shown[i]),
              ),
            ),
          if (remaining > 0)
            Positioned(
              left: shown.length * step,
              child: _MoreBadge(
                count: remaining,
                size: diameter,
                ringColor: ringColor,
              ),
            ),
        ],
      ),
    );
  }
}

bool _isCircleShape(String assetKind) {
  switch (assetKind.trim()) {
    case 'avatar':
    case 'circleAvatar':
    case 'emblem':
    case 'logo':
    case 'icon':
      return true;
    default:
      return false;
  }
}

IconData _iconForAssetKind(String assetKind) {
  switch (assetKind.trim()) {
    case 'avatar':
      return CupertinoIcons.person_crop_circle_fill;
    case 'circleAvatar':
      return CupertinoIcons.person_3_fill;
    case 'emblem':
      return CupertinoIcons.book_fill;
    case 'logo':
      return CupertinoIcons.building_2_fill;
    case 'cover':
    case 'coverImage':
    case 'thumbnail':
      return CupertinoIcons.photo_fill;
    default:
      return CupertinoIcons.circle_fill;
  }
}

class _VisualBadge extends StatelessWidget {
  const _VisualBadge({
    required this.visual,
    required this.size,
    required this.ringColor,
    this.onTap,
  });

  final IntersectionVisual visual;
  final double size;
  final Color ringColor;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final circle = _isCircleShape(visual.assetKind);
    final radius = circle
        ? BorderRadius.circular(size)
        : BorderRadius.circular(AppSpacing.radiusTen);
    final accent = AppColors.iosAccent(context);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fallback = Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: accent.withValues(alpha: isDark ? 0.22 : 0.1),
        borderRadius: radius,
      ),
      child: Icon(
        _iconForAssetKind(visual.assetKind),
        size: size * 0.5,
        color: accent,
      ),
    );
    final url = visual.imageUrl.trim();
    final inner = url.isEmpty
        ? fallback
        : ClipRRect(
            borderRadius: radius,
            child: AppCachedNetworkImage(
              imageUrl: url,
              width: size,
              height: size,
              fit: BoxFit.cover,
              cdnPreset: circle
                  ? CdnImagePreset.avatar
                  : CdnImagePreset.thumbnail,
              errorWidget: fallback,
            ),
          );
    final ringed = Container(
      decoration: BoxDecoration(
        borderRadius: radius,
        border: Border.all(color: ringColor, width: AppSpacing.two),
      ),
      child: inner,
    );
    if (onTap == null) {
      return Semantics(label: visual.displayName.trim(), child: ringed);
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Semantics(
        label: visual.displayName.trim(),
        button: true,
        child: ringed,
      ),
    );
  }
}

class _MoreBadge extends StatelessWidget {
  const _MoreBadge({
    required this.count,
    required this.size,
    required this.ringColor,
  });

  final int count;
  final double size;
  final Color ringColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(size),
        border: Border.all(color: ringColor, width: AppSpacing.two),
      ),
      child: Text(
        '+$count',
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}
