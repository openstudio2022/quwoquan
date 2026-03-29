import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 单选导航行（转让群主、群成员搜索进资料）。
class MemberListNavigateTile extends StatelessWidget {
  const MemberListNavigateTile({
    super.key,
    required this.isDark,
    required this.member,
    required this.onTap,
    this.subtitleText,
  });

  final bool isDark;
  final Map<String, dynamic> member;
  final VoidCallback onTap;
  final String? subtitleText;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final name =
        member['displayName'] as String? ??
        member['name'] as String? ??
        '';
    final avatar =
        member['avatarUrl'] as String? ?? member['avatar'] as String? ?? '';
    final subtitle = subtitleText?.trim() ?? '';
    return CupertinoListTile(
      backgroundColor: Colors.transparent,
      onTap: onTap,
      padding: EdgeInsets.symmetric(
        horizontal: SettingsSemanticConstants.blockHorizontalPadding,
        vertical: AppSpacing.sm,
      ),
      leading: RoundedSquareAvatar(
        size: AppSpacing.largeButtonSize,
        imageUrl: avatar,
        name: name,
        backgroundColor: SettingsSemanticConstants.blockBackground(isDark),
      ),
      title: Text(
        name,
        style: TextStyle(
          fontSize: AppTypography.lg,
          color: fgPrimary,
        ),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: subtitle.isNotEmpty
          ? Text(
              subtitle,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundSecondary,
                ),
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            )
          : null,
      trailing: Icon(
        CupertinoIcons.chevron_forward,
        size: AppSpacing.iconMedium,
        color: SettingsSemanticConstants.selectionChevronColor(isDark),
      ),
    );
  }
}

/// 多选行（群管理员）。
class MemberListMultiSelectTile extends StatelessWidget {
  const MemberListMultiSelectTile({
    super.key,
    required this.isDark,
    required this.member,
    required this.isSelected,
    required this.onTap,
  });

  final bool isDark;
  final Map<String, dynamic> member;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final name =
        member['displayName'] as String? ??
        member['name'] as String? ??
        '';
    final avatar =
        member['avatarUrl'] as String? ?? member['avatar'] as String? ?? '';
    final nickname = (member['nickname'] as String?)?.trim() ?? '';
    final isAdmin = member['role'] == 'admin';

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 56),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: SettingsSemanticConstants.blockHorizontalPadding,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              Icon(
                isSelected
                    ? CupertinoIcons.check_mark_circled_solid
                    : CupertinoIcons.circle,
                color: isSelected
                    ? AppColors.primaryColor
                    : SettingsSemanticConstants.checkboxUnselectedBorderColor(
                        isDark,
                      ),
                size: AppSpacing.iconMedium,
              ),
              SizedBox(width: AppSpacing.interGroupSm),
              RoundedSquareAvatar(
                size: AppSpacing.largeButtonSize,
                imageUrl: avatar,
                name: name,
                backgroundColor:
                    SettingsSemanticConstants.blockBackground(isDark),
              ),
              SizedBox(width: AppSpacing.interGroupSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            name,
                            style: TextStyle(
                              fontSize: AppTypography.lg,
                              color: fgPrimary,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (isAdmin) ...[
                          SizedBox(width: AppSpacing.xs),
                          Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.xs,
                              vertical: AppSpacing.one,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.primaryColor.withValues(
                                alpha: 0.12,
                              ),
                              borderRadius: BorderRadius.circular(
                                AppSpacing.borderRadius,
                              ),
                            ),
                            child: Text(
                              UITextConstants.admin,
                              style: TextStyle(
                                fontSize: AppTypography.xs,
                                color: AppColors.primaryColor,
                                fontWeight: AppTypography.medium,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    if (nickname.isNotEmpty)
                      Text(
                        nickname,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
