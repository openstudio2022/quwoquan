import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

/// 私人助理头像：彩色花瓣标识（用于趣聊列表与对话气泡）
class AssistantAvatar extends StatelessWidget {
  const AssistantAvatar({
    super.key,
    this.radius = 20,
    this.onTap,
  });

  final double radius;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final size = radius * 2;
    final box = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: AppColors.primaryColor,
        boxShadow: [
          BoxShadow(
            color: AppColors.primaryColor.withValues(alpha: 0.3),
            blurRadius: 6,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: Center(
        child: _AvatarPetalMark(
          size: radius * 1.0,
        ),
      ),
    );
    if (onTap != null) {
      return GestureDetector(
        onTap: onTap,
        child: box,
      );
    }
    return box;
  }
}

class _AvatarPetalMark extends StatelessWidget {
  const _AvatarPetalMark({
    required this.size,
  });

  final double size;

  static const List<Color> _petalColors = [
    AppColors.welcomePetalOrange,
    AppColors.welcomePetalYellow,
    AppColors.welcomePetalLime,
    AppColors.welcomePetalEmerald,
    AppColors.welcomePetalCyan,
    AppColors.welcomePetalSky,
    AppColors.welcomePetalPurple,
    AppColors.welcomePetalRose,
  ];

  @override
  Widget build(BuildContext context) {
    final petalHeight = size * 0.72;
    final petalWidth = size * 0.26;
    final travel = size * 0.22;

    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          for (var i = 0; i < _petalColors.length; i++)
            Transform.rotate(
              angle: (i * 45) * 3.1415926 / 180,
              child: Transform.translate(
                offset: Offset(0, -travel),
                child: Container(
                  width: petalWidth,
                  height: petalHeight,
                  decoration: BoxDecoration(
                    color: _petalColors[i],
                    borderRadius: BorderRadius.circular(petalWidth),
                  ),
                ),
              ),
            ),
          Container(
            width: size * 0.18,
            height: size * 0.18,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.white,
            ),
          ),
        ],
      ),
    );
  }
}
