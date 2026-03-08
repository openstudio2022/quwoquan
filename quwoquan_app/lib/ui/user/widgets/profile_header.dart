import 'package:flutter/material.dart';
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
  static const double _avatarBorder = AppSpacing.intraGroupXs;
  static double get avatarOuterDiameter => (avatarRadius + _avatarBorder) * 2;
  static double get avatarIntrusion => avatarRadius * 2 / 3;

  Widget _buildAvatar(Color bg, Color fgSecondary) {
    final hasAvatar = avatarUrl != null && avatarUrl!.isNotEmpty;
    return Container(
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: bg, width: _avatarBorder),
      ),
      child: hasAvatar
          ? CircleAvatar(
              radius: avatarRadius,
              backgroundColor: fgSecondary.withValues(alpha: 0.2),
              backgroundImage: NetworkImage(avatarUrl!),
              onBackgroundImageError: (e, s) {},
            )
          : CircleAvatar(
              radius: avatarRadius,
              backgroundColor: fgSecondary.withValues(alpha: 0.2),
              child: Icon(Icons.person, size: AppSpacing.iconLarge, color: fgSecondary),
            ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);

    return Stack(
      clipBehavior: Clip.none,
      children: [
        Padding(
          padding: EdgeInsets.only(left: avatarOuterDiameter + AppSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                displayName ?? '',
                style: TextStyle(
                  fontSize: AppTypography.xxl,
                  fontWeight: AppTypography.bold,
                  color: fg,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              if (bio != null && bio!.isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  bio!,
                  style: TextStyle(
                    fontSize: AppTypography.md,
                    color: fgSecondary,
                    height: AppTypography.bodyLineHeight,
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
          top: -avatarIntrusion,
          left: 0,
          child: _buildAvatar(bg, fgSecondary),
        ),
      ],
    );
  }
}
