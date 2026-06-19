import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// Profile header with left-aligned avatar that intrudes 1/3 into the
/// background area above. Display name sits in a Row beside the avatar,
/// aligned to its lower 2/3. No @username is shown.
class ProfileHeader extends StatelessWidget {
  const ProfileHeader({
    super.key,
    required this.isDark,
    this.avatarUrl,
    this.displayName,
    this.identityTags = const <String>[],
    this.verified = false,
    this.showEdit = false,
    this.onEdit,
  });

  final bool isDark;
  final String? avatarUrl;
  final String? displayName;

  /// 主页单行身份标签（云侧 identityTags 直出，端以 · 分隔；与 bio 互补不重复）。
  final List<String> identityTags;

  /// 认证标识（蓝勾）。云侧 verified 直出，端只读展示。
  final bool verified;

  /// 我的主页昵称右侧编辑入口。
  final bool showEdit;
  final VoidCallback? onEdit;

  static const Key verifiedBadgeKey = ValueKey<String>(
    'profile-header-verified-badge',
  );

  static const double avatarRadius = AppSpacing.xl;
  static const double _avatarBorder = AppSpacing.three;
  static double get avatarOuterDiameter => (avatarRadius + _avatarBorder) * 2;
  static double get avatarOverlapPx =>
      avatarOuterDiameter * UserProfileUIConfig.headerLayout.avatarOverlapRatio;
  static double get avatarIntrusion => avatarOverlapPx;

  Widget _buildAvatar(BuildContext context, Color bg, Color fgSecondary) {
    final resolvedAvatarUrl = resolveAvatarImageUrl(avatarUrl);
    final hasAvatar = resolvedAvatarUrl.isNotEmpty;
    return Container(
      key: const ValueKey<String>('profile-header-avatar'),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: bg, width: _avatarBorder),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: isDark ? 0.18 : 0.08),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: hasAvatar
          ? CircleAvatar(
              radius: avatarRadius,
              backgroundColor: AppColors.iosSecondaryFill(context),
              backgroundImage: NetworkImage(resolvedAvatarUrl),
              onBackgroundImageError: (e, s) {},
            )
          : CircleAvatar(
              radius: avatarRadius,
              backgroundColor: AppColors.iosTintedFill(context),
              child: Icon(
                CupertinoIcons.person_crop_circle_fill,
                size: AppSpacing.iconLarge,
                color: AppColors.iosAccent(context),
              ),
            ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bg = SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final tags = identityTags
        .map((tag) => tag.trim())
        .where((tag) => tag.isNotEmpty)
        .toList(growable: false);

    return Stack(
      clipBehavior: Clip.none,
      children: [
        Padding(
          padding: EdgeInsets.only(left: avatarOuterDiameter + AppSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(height: AppSpacing.intraGroupXs),
              Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Flexible(
                    child: Text(
                      displayName ?? '',
                      style: TextStyle(
                        fontSize: AppTypography.iosTitle3,
                        fontWeight: AppTypography.regular,
                        color: fg.withValues(alpha: 0.94),
                        letterSpacing: -0.24,
                        height: AppSpacing.textLineHeightDense,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (verified) ...[
                    SizedBox(width: AppSpacing.intraGroupXs),
                    Icon(
                      key: verifiedBadgeKey,
                      CupertinoIcons.checkmark_seal_fill,
                      size: AppSpacing.iconSmall,
                      color: AppColors.iosAccent(context),
                    ),
                  ],
                  if (showEdit && onEdit != null) ...[
                    SizedBox(width: AppSpacing.intraGroupXs),
                    CupertinoButton(
                      key: const ValueKey<String>('profile-header-edit'),
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.intraGroupXs,
                        vertical: AppSpacing.intraGroupXs,
                      ),
                      minimumSize: const Size(
                        AppSpacing.buttonHeightSm,
                        AppSpacing.buttonHeightSm,
                      ),
                      onPressed: onEdit,
                      child: Icon(
                        CupertinoIcons.square_pencil,
                        size: AppSpacing.iconMedium,
                        color: fg.withValues(alpha: 0.88),
                      ),
                    ),
                  ],
                ],
              ),
              if (tags.isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  key: const ValueKey<String>('profile-header-identity-tags'),
                  tags.join(' · '),
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: fgSecondary,
                    letterSpacing: -0.08,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ],
          ),
        ),
        Positioned(
          top: -avatarOverlapPx,
          left: 0,
          child: _buildAvatar(context, bg, fgSecondary),
        ),
      ],
    );
  }
}
