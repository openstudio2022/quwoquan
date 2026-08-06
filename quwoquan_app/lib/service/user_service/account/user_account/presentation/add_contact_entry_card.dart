import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 添加联系人主页的入口行（扫一扫 / 手机联系人）：iOS 分组卡内的一行，
/// 左侧 halo 圆底图标 + 标题/副标题 + 右侧 chevron。
class AddContactEntryCard extends StatelessWidget {
  const AddContactEntryCard({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.showDivider = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool showDivider;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Column(
        children: <Widget>[
          Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerMd,
              vertical: AppSpacing.containerSm,
            ),
            child: Row(
              children: <Widget>[
                Container(
                  width: AppSpacing.avatarUserSm,
                  height: AppSpacing.avatarUserSm,
                  decoration: BoxDecoration(
                    color: accent.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
                  ),
                  alignment: Alignment.center,
                  child: Icon(icon, size: AppSpacing.iconMedium, color: accent),
                ),
                SizedBox(width: AppSpacing.containerSm),
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosBody,
                          fontWeight: AppTypography.regular,
                          color: AppColors.iosLabel(context),
                        ),
                      ),
                      SizedBox(height: AppSpacing.intraGroupXs),
                      Text(
                        subtitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          fontWeight: AppTypography.regular,
                          color: AppColors.iosSecondaryLabel(context),
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(width: AppSpacing.containerSm),
                Icon(
                  CupertinoIcons.chevron_forward,
                  size: AppSpacing.iconSmall,
                  color: AppColors.iosTertiaryLabel(context),
                ),
              ],
            ),
          ),
          if (showDivider)
            Padding(
              padding: EdgeInsets.only(
                left:
                    AppSpacing.containerMd +
                    AppSpacing.avatarUserSm +
                    AppSpacing.containerSm,
              ),
              child: Container(
                height: AppSpacing.hairline,
                color: AppColors.iosSeparator(context).withValues(alpha: 0.36),
              ),
            ),
        ],
      ),
    );
  }
}
