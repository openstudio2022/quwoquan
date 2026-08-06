import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

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
    final separator =
        SettingsSemanticConstants.conversationSheetCardBorderColor(isDark);
    final coverFallback = ColoredBox(
      color: AppColors.iosFill(context),
      child: Center(child: Icon(CupertinoIcons.group, color: fgSecondary)),
    );
    final coverSize = AppSpacing.avatarSize + AppSpacing.sm;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: ProfileIosSectionCard(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.containerSm,
        ),
        backgroundColor: SettingsSemanticConstants.conversationSheetCardSurface(
          isDark,
        ),
        borderColor: separator,
        child: Row(
          children: <Widget>[
            ClipOval(
              child: SizedBox.square(
                dimension: coverSize,
                child: coverUrl.trim().isEmpty
                    ? coverFallback
                    : AppCachedNetworkImage(
                        imageUrl: coverUrl,
                        fit: BoxFit.cover,
                        cdnPreset: CdnImagePreset.cover,
                        placeholder: coverFallback,
                        errorWidget: coverFallback,
                      ),
              ),
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
