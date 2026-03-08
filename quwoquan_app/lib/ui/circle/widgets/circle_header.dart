import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class CircleHeader extends StatelessWidget {
  const CircleHeader({
    super.key,
    required this.isDark,
    this.avatarUrl,
    required this.name,
    this.description,
    this.tags = const [],
  });

  final bool isDark;
  final String? avatarUrl;
  final String name;
  final String? description;
  final List<String> tags;

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
              child: Icon(Icons.group, size: AppSpacing.iconLarge, color: fgSecondary),
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
                name,
                style: TextStyle(
                  fontSize: AppTypography.xxxl,
                  fontWeight: AppTypography.bold,
                  color: fg,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              if (description != null && description!.isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  description!,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: fgSecondary,
                    height: AppTypography.bodyLineHeight,
                  ),
                  textAlign: TextAlign.start,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
              if (tags.isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupSm),
                Wrap(
                  spacing: AppSpacing.xs,
                  runSpacing: AppSpacing.xs,
                  children: tags.map((tag) {
                    return Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.sm,
                        vertical: AppSpacing.intraGroupXs,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.primaryColor.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
                      ),
                      child: Text(
                        tag,
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          fontWeight: AppTypography.medium,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    );
                  }).toList(),
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
