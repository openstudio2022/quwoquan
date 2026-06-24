// ignore_for_file: unnecessary_underscores
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 圆角方形头像组件（替代 CircleAvatar）
///
/// 与微信一致的圆角方形头像，支持网络图片、占位首字母、点击回调。
class RoundedSquareAvatar extends StatelessWidget {
  const RoundedSquareAvatar({
    super.key,
    required this.size,
    this.imageUrl,
    this.name,
    this.borderRadius,
    this.onTap,
    this.backgroundColor,
    this.fallbackIcon,
  });

  final double size;
  final String? imageUrl;
  final String? name;
  final double? borderRadius;
  final VoidCallback? onTap;
  final Color? backgroundColor;
  final IconData? fallbackIcon;

  @override
  Widget build(BuildContext context) {
    final radius = borderRadius ?? AppSpacing.contentPreviewCornerRadius;
    final imageCandidates = resolveAvatarImageUrlCandidates(imageUrl);
    final hasImage = imageCandidates.isNotEmpty;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;

    Widget avatar = ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: hasImage
          ? AppCachedNetworkImage(
              imageUrl: imageCandidates.first,
              imageUrlCandidates: imageCandidates,
              width: size,
              height: size,
              fit: BoxFit.cover,
              cdnPreset: CdnImagePreset.avatar,
              placeholder: _buildLoadingPlaceholder(radius, isDark),
              errorWidget: _buildFallback(radius, isDark),
            )
          : _buildFallback(radius, isDark),
    );

    if (onTap != null) {
      avatar = GestureDetector(onTap: onTap, child: avatar);
    }

    return avatar;
  }

  Widget _buildLoadingPlaceholder(double radius, bool isDark) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color:
            backgroundColor ??
            AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
        borderRadius: BorderRadius.circular(radius),
      ),
    );
  }

  Widget _buildFallback(double radius, bool isDark) {
    final initial = _getInitial(name ?? '');
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color:
            backgroundColor ??
            AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
        borderRadius: BorderRadius.circular(radius),
      ),
      alignment: Alignment.center,
      child: fallbackIcon == null
          ? Text(
              initial,
              style: TextStyle(
                fontSize: size * 0.4,
                fontWeight: FontWeight.w600,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundSecondary,
                ),
              ),
            )
          : Icon(
              fallbackIcon,
              size: size * 0.5,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundSecondary,
              ),
            ),
    );
  }

  static String _getInitial(String name) {
    if (name.isEmpty) return '?';
    return name[0].toUpperCase();
  }
}
