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
    this.memberAvatarUrls = const <String>[],
    this.onTagTap,
  });

  final bool isDark;
  final String? avatarUrl;
  final String name;
  final String? description;
  final List<String> tags;
  final String? metaLine;
  final String? badgeLabel;

  /// 头部成员头像簇（圈子里你认识的人，最多展示前若干个）；为空则不展示。
  final List<String> memberAvatarUrls;
  final ValueChanged<String>? onTagTap;

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
            color: AppColors.black.withValues(alpha: isDark ? 0.24 : 0.12),
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

  /// 成员头像簇：叠加展示前若干位成员头像，传达「圈子里有真实的人」。
  Widget _buildMemberCluster(Color bg, Color fgSecondary) {
    final urls = memberAvatarUrls
        .where((u) => u.trim().isNotEmpty)
        .take(4)
        .toList(growable: false);
    if (urls.isEmpty) {
      return const SizedBox.shrink();
    }
    const double diameter = AppSpacing.avatarUserXs;
    const double step = diameter - AppSpacing.sm;
    return SizedBox(
      key: const ValueKey<String>('circle-header-member-cluster'),
      height: diameter,
      width: diameter + step * (urls.length - 1),
      child: Stack(
        children: [
          for (var i = 0; i < urls.length; i++)
            Positioned(
              left: i * step,
              child: Container(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: bg, width: AppSpacing.hairline * 2),
                ),
                child: CircleAvatar(
                  radius: diameter / 2,
                  backgroundColor: fgSecondary.withValues(alpha: 0.2),
                  backgroundImage: circleImageProvider(urls[i]),
                  onBackgroundImageError: (e, s) {},
                ),
              ),
            ),
        ],
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
              if (memberAvatarUrls.any((u) => u.trim().isNotEmpty)) ...[
                SizedBox(height: AppSpacing.intraGroupSm),
                _buildMemberCluster(bg, fgSecondary),
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
                      (tag) => GestureDetector(
                        onTap: onTagTap != null ? () => onTagTap!(tag) : null,
                        child: _buildInfoChip(
                          label: tag,
                          foreground: fgSecondary,
                          background: tertiary,
                        ),
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
