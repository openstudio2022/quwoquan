import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 私人助理悬浮球
///
/// 星火图标，底部悬浮，点击可唤起助理半屏面板（后续实现）。
class AssistantFloatingBall extends ConsumerWidget {
  const AssistantFloatingBall({
    super.key,
    this.onTap,
    this.bottom = 100,
    this.right = 16,
  });

  final VoidCallback? onTap;
  final double bottom;
  final double right;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Positioned(
      right: right,
      bottom: bottom + MediaQuery.of(context).padding.bottom,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap ?? () {},
          borderRadius: BorderRadius.circular(AppSpacing.avatarUserLg / 2),
          child: Container(
            width: AppSpacing.avatarUserLg,
            height: AppSpacing.avatarUserLg,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.primaryColor,
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.2),
                  blurRadius: 12,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Icon(
              Icons.auto_awesome,
              size: AppSpacing.iconLarge,
              color: Colors.white,
            ),
          ),
        ),
      ),
    );
  }
}
