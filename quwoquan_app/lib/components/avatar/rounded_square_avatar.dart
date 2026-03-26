// ignore_for_file: unnecessary_underscores
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

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
  });

  final double size;
  final String? imageUrl;
  final String? name;
  final double? borderRadius;
  final VoidCallback? onTap;
  final Color? backgroundColor;

  @override
  Widget build(BuildContext context) {
    final radius = borderRadius ?? AppSpacing.contentPreviewCornerRadius;
    final hasImage = imageUrl != null && imageUrl!.isNotEmpty;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    Widget avatar = ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: hasImage
          ? Image.network(
              imageUrl!,
              width: size,
              height: size,
              fit: BoxFit.cover,
              errorBuilder: (_, __, _) => _buildFallback(radius, isDark),
            )
          : _buildFallback(radius, isDark),
    );

    if (onTap != null) {
      avatar = GestureDetector(onTap: onTap, child: avatar);
    }

    return avatar;
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
      child: Text(
        initial,
        style: TextStyle(
          fontSize: size * 0.4,
          fontWeight: FontWeight.w600,
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.foregroundSecondary,
          ),
        ),
      ),
    );
  }

  static String _getInitial(String name) {
    if (name.isEmpty) return '?';
    return name[0].toUpperCase();
  }
}
