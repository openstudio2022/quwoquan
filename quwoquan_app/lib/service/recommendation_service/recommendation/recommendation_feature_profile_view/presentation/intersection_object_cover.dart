import 'package:flutter/cupertino.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

/// 槽③ 交集对象封面/缩略图（canonical 交集设计 · 单行交集卡 trailing）。
///
/// 只读消费云侧 [IntersectionReason.objectVisual]——结论句所指向的「那一个对象」的封面：
/// 内容用 cover/thumbnail（小圆角矩形），圈子/校/企用 circleAvatar/emblem/logo（圆形），
/// 地点用 cover。禁用户头像冒充非人对象（由云侧 `assetKind` 约束，端按形状渲染）。
///
/// 可叠加 [lifecycleBadge]（槽④弱标）在右上角作 overlay；[onTap] 命中进对象页。
/// `objectVisual` 为空或 `imageUrl` 为空时回退为对象类型占位图标，不留白、不造假。
class IntersectionObjectCover extends StatelessWidget {
  const IntersectionObjectCover({
    super.key,
    required this.visual,
    this.size,
    this.lifecycleBadge,
    this.onTap,
  });

  final IntersectionVisual visual;
  final double? size;

  /// 槽④生命周期弱标（右上角 overlay）；传 null 不叠加。
  final Widget? lifecycleBadge;
  final VoidCallback? onTap;

  bool get _isCircle {
    switch (visual.assetKind.trim()) {
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

  IconData get _fallbackIcon {
    switch (visual.assetKind.trim()) {
      case 'avatar':
        return CupertinoIcons.person_crop_circle_fill;
      case 'circleAvatar':
        return CupertinoIcons.person_3_fill;
      case 'emblem':
        return CupertinoIcons.book_fill;
      case 'logo':
        return CupertinoIcons.building_2_fill;
      default:
        return CupertinoIcons.photo_fill;
    }
  }

  @override
  Widget build(BuildContext context) {
    final diameter = size ?? AppSpacing.avatarUserMd;
    final radius = _isCircle
        ? BorderRadius.circular(diameter)
        : BorderRadius.circular(AppSpacing.radiusTen);
    final accent = AppColors.iosAccent(context);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fallback = Container(
      width: diameter,
      height: diameter,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: accent.withValues(alpha: isDark ? 0.22 : 0.1),
        borderRadius: radius,
      ),
      child: Icon(_fallbackIcon, size: diameter * 0.5, color: accent),
    );
    final url = visual.imageUrl.trim();
    final cover = url.isEmpty
        ? fallback
        : ClipRRect(
            borderRadius: radius,
            child: AppCachedNetworkImage(
              imageUrl: url,
              width: diameter,
              height: diameter,
              fit: BoxFit.cover,
              cdnPreset: _isCircle
                  ? CdnImagePreset.avatar
                  : CdnImagePreset.thumbnail,
              errorWidget: fallback,
            ),
          );

    Widget content = cover;
    if (lifecycleBadge != null) {
      content = Stack(
        clipBehavior: Clip.none,
        children: <Widget>[
          cover,
          Positioned(
            top: -AppSpacing.intraGroupXs,
            right: -AppSpacing.intraGroupXs,
            child: lifecycleBadge!,
          ),
        ],
      );
    }

    final label = visual.displayName.trim();
    if (onTap == null) {
      return Semantics(label: label, child: content);
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Semantics(label: label, button: true, child: content),
    );
  }
}
