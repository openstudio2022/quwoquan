import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 圈子紧凑卡片：头像（或封面）+ 名称 + 创作数，横向布局。
class CircleCompactCard extends StatelessWidget {
  const CircleCompactCard({
    super.key,
    required this.name,
    required this.coverUrl,
    required this.postCount,
    required this.isDark,
    this.onTap,
  });

  final String name;
  final String coverUrl;
  final int postCount;
  final bool isDark;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: Border.all(color: border.withValues(alpha: 0.2)),
        ),
        child: Row(
          children: [
            CircleAvatar(
              radius: 24,
              backgroundImage: coverUrl.isNotEmpty ? NetworkImage(coverUrl) : null,
              onBackgroundImageError: (_, __) {},
              child: coverUrl.isEmpty
                  ? Icon(Icons.group, color: fgSecondary)
                  : null,
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    name,
                    style: TextStyle(
                      fontSize: AppTypography.md,
                      fontWeight: AppTypography.semiBold,
                      color: fg,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    '$postCount 创作',
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      fontWeight: AppTypography.normal,
                      color: fgSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
