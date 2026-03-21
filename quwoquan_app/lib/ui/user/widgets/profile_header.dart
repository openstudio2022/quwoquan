import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
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
    this.bio,
  });

  final bool isDark;
  final String? avatarUrl;
  final String? displayName;
  final String? bio;

  static const double avatarRadius = AppSpacing.xl;
  static const double _avatarBorder = AppSpacing.three;
  static double get avatarOuterDiameter => (avatarRadius + _avatarBorder) * 2;
  static double get avatarOverlapPx =>
      avatarOuterDiameter * UserProfileUIConfig.headerLayout.avatarOverlapRatio;
  static double get avatarIntrusion => avatarOverlapPx;

  Widget _buildAvatar(BuildContext context, Color bg, Color fgSecondary) {
    final hasAvatar = avatarUrl != null && avatarUrl!.isNotEmpty;
    return Container(
      key: const ValueKey<String>('profile-header-avatar'),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: bg, width: _avatarBorder),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.18 : 0.08),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: hasAvatar
          ? CircleAvatar(
              radius: avatarRadius,
              backgroundColor: AppColors.iosSecondaryFill(context),
              backgroundImage: NetworkImage(avatarUrl!),
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
    final bg = AppColors.iosSystemBackground(context);
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);

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
              Text(
                displayName ?? '',
                style: TextStyle(
                  fontSize: AppTypography.iosProfileTitle,
                  fontWeight: AppTypography.semiBold,
                  color: fg,
                  letterSpacing: -0.72,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              if (bio != null && bio!.isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  bio!,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    color: fgSecondary,
                    height: 1.35,
                    letterSpacing: -0.16,
                  ),
                  textAlign: TextAlign.start,
                  maxLines: 2,
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
