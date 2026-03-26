import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';

class CircleHeader extends StatelessWidget {
  const CircleHeader({
    super.key,
    required this.isDark,
    this.avatarUrl,
    required this.name,
    this.description,
    this.tags = const [],
    this.metaLine,
    this.badgeLabel,
  });

  final bool isDark;
  final String? avatarUrl;
  final String name;
  final String? description;
  final List<String> tags;
  final String? metaLine;
  final String? badgeLabel;

  static const double avatarRadius = AppSpacing.xl;
  static const double _avatarBorder = AppSpacing.intraGroupXs;
  static double get avatarOuterDiameter => (avatarRadius + _avatarBorder) * 2;
  static double get avatarIntrusion => avatarOuterDiameter * 0.34;

  Widget _buildAvatar(Color bg, Color fgSecondary) {
    final avatarProvider = circleImageProvider(avatarUrl);
    return Container(
      key: const ValueKey<String>('circle-header-avatar'),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: bg, width: _avatarBorder),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.24 : 0.12),
            blurRadius: AppSpacing.lg,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: avatarProvider != null
          ? CircleAvatar(
              radius: avatarRadius,
              backgroundColor: fgSecondary.withValues(alpha: 0.2),
              backgroundImage: avatarProvider,
              onBackgroundImageError: (e, s) {},
            )
          : CircleAvatar(
              radius: avatarRadius,
              backgroundColor: fgSecondary.withValues(alpha: 0.2),
              child: Icon(
                CupertinoIcons.person_3_fill,
                size: AppSpacing.iconLarge,
                color: fgSecondary,
              ),
            ),
    );
  }

  Widget _buildInfoChip({
    required String label,
    required Color foreground,
    required Color background,
    IconData? icon,
    bool accent = false,
  }) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        border: accent
            ? Border.all(color: AppColors.primaryColor.withValues(alpha: 0.14))
            : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(
              icon,
              size: AppSpacing.iconSmall,
              color: accent ? AppColors.primaryColor : foreground,
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
          ],
          Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.xs,
              fontWeight: AppTypography.semiBold,
              color: accent ? AppColors.primaryColor : foreground,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final tertiary = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundTertiary,
    );

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
                name,
                style: TextStyle(
                  fontSize: AppTypography.xxl,
                  fontWeight: AppTypography.bold,
                  color: fg,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              if (metaLine != null && metaLine!.isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  metaLine!,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgSecondary,
                    height: AppTypography.bodyLineHeight,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
              if (description != null && description!.isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  description!,
                  style: TextStyle(
                    fontSize: AppTypography.md,
                    color: fgSecondary,
                    height: AppTypography.bodyLineHeight,
                  ),
                  textAlign: TextAlign.start,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
              if ((badgeLabel != null && badgeLabel!.isNotEmpty) || tags.isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupSm),
                Wrap(
                  spacing: AppSpacing.xs,
                  runSpacing: AppSpacing.xs,
                  children: [
                    if (badgeLabel != null && badgeLabel!.isNotEmpty)
                      _buildInfoChip(
                        label: badgeLabel!,
                        icon: CupertinoIcons.checkmark_seal_fill,
                        foreground: fgSecondary,
                        background: AppColors.primaryColor.withValues(alpha: 0.08),
                        accent: true,
                      ),
                    ...tags.map(
                      (tag) => _buildInfoChip(
                        label: tag,
                        foreground: fgSecondary,
                        background: tertiary,
                      ),
                    ),
                  ],
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
