import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

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
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.16);

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: ProfileIosSectionCard(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.containerSm,
        ),
        backgroundColor: AppColors.iosGroupedSurface(context),
        borderColor: separator,
        child: Row(
          children: <Widget>[
            CircleAvatar(
              radius: 24,
              backgroundImage: coverUrl.isNotEmpty ? NetworkImage(coverUrl) : null,
              backgroundColor: AppColors.iosFill(context),
              onBackgroundImageError: (error, stackTrace) {},
              child: coverUrl.isEmpty
                  ? Icon(CupertinoIcons.group, color: fgSecondary)
                  : null,
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    name,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.semiBold,
                      color: fg,
                      letterSpacing: -0.16,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    '$postCount 创作',
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.normal,
                      color: fgSecondary,
                    ),
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
}
