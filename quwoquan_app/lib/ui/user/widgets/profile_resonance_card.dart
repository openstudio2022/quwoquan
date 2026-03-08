import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';

class ProfileResonanceCard extends StatelessWidget {
  const ProfileResonanceCard({
    super.key,
    required this.mode,
    required this.isDark,
    this.resonanceCount = 0,
    this.onTap,
  });

  final ProfileMode mode;
  final bool isDark;
  final int resonanceCount;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final primary = AppColors.primaryColor;

    final text = mode == ProfileMode.mine
        ? '本周有 $resonanceCount 位趣友与你有交集'
        : '你们有 $resonanceCount 个交集点';

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: primary.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.bubble_chart, size: AppSpacing.iconMedium, color: primary),
            SizedBox(width: AppSpacing.sm),
            Flexible(
              child: Text(
                text,
                style: TextStyle(
                  fontSize: AppTypography.md,
                  fontWeight: AppTypography.semiBold,
                  color: primary,
                ),
              ),
            ),
            SizedBox(width: AppSpacing.xs),
            Icon(Icons.chevron_right, size: AppSpacing.iconSmall, color: primary),
          ],
        ),
      ),
    );
  }
}
