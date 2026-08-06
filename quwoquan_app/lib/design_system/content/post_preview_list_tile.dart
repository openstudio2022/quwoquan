import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// Post 列表预览组件。
///
/// 与内容预览卡片使用同一套材质与间距语义，
/// 适用于列表页、管理页等横向信息布局。
class PostPreviewListTile extends StatelessWidget {
  const PostPreviewListTile({
    super.key,
    required this.isDark,
    required this.title,
    required this.footer,
    required this.onTap,
    this.supportingText = '',
    this.coverUrl = '',
    this.showVideoBadge = false,
    this.thumbnailWidth =
        AppSpacing.followButtonWidth + AppSpacing.intraGroupMd,
    this.thumbnailHeight =
        AppSpacing.followButtonWidth + AppSpacing.intraGroupMd,
    this.eyebrowText = '',
    this.eyebrowColor,
    this.trailing,
    this.thumbnailKey,
    this.hideThumbnailWhenNoCover = false,
    this.supportingTextMaxLines = 2,
  });

  final bool isDark;
  final String title;
  final String supportingText;
  final String coverUrl;
  final bool showVideoBadge;
  final double thumbnailWidth;
  final double thumbnailHeight;
  final String eyebrowText;
  final Color? eyebrowColor;
  final Widget footer;
  final Widget? trailing;
  final Key? thumbnailKey;
  final bool hideThumbnailWhenNoCover;
  final int supportingTextMaxLines;
  final VoidCallback onTap;

  bool get _hasCover => coverUrl.trim().isNotEmpty;

  bool get _hasSupportingText => supportingText.trim().isNotEmpty;

  bool get _hasEyebrow => eyebrowText.trim().isNotEmpty;

  @override
  Widget build(BuildContext context) {
    final cardBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final showThumbnail = _hasCover || !hideThumbnailWhenNoCover;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: borderColor),
        boxShadow: [
          BoxShadow(
            color: AppColorsFunctional.getColor(isDark, ColorType.dropShadow),
            blurRadius: AppSpacing.containerMd,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.postPreviewCardPadding),
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (showThumbnail) ...[
              ClipRRect(
                borderRadius: BorderRadius.circular(
                  AppSpacing.contentPreviewCornerRadius,
                ),
                child: SizedBox(
                  key: thumbnailKey,
                  width: thumbnailWidth,
                  height: thumbnailHeight,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      if (_hasCover)
                        AppCachedNetworkImage(
                          imageUrl: coverUrl,
                          fit: BoxFit.cover,
                          cdnPreset: CdnImagePreset.thumbnail,
                          placeholder: ColoredBox(
                            color: fgSecondary.withValues(alpha: 0.12),
                          ),
                          errorWidget: ColoredBox(
                            color: fgSecondary.withValues(alpha: 0.12),
                            child: Icon(
                              CupertinoIcons.photo,
                              color: fgSecondary,
                            ),
                          ),
                        )
                      else
                        ColoredBox(
                          color: fgSecondary.withValues(alpha: 0.12),
                          child: Icon(CupertinoIcons.photo, color: fgSecondary),
                        ),
                      if (showVideoBadge)
                        Positioned(
                          top: AppSpacing.intraGroupSm,
                          right: AppSpacing.intraGroupSm,
                          child: Icon(
                            CupertinoIcons.play_circle_fill,
                            color: AppColors.white,
                            size: AppSpacing.iconMedium,
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (_hasEyebrow) ...[
                    Text(
                      eyebrowText,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: eyebrowColor ?? AppColors.primaryColor,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                  ],
                  Text(
                    title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.semiBold,
                      color: fgPrimary,
                    ),
                  ),
                  if (_hasSupportingText) ...[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      supportingText,
                      maxLines: supportingTextMaxLines,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: fgSecondary,
                        height: AppTypography.lineHeightRelaxed,
                      ),
                    ),
                  ],
                  SizedBox(height: AppSpacing.intraGroupXs),
                  footer,
                ],
              ),
            ),
            if (trailing case final trailingWidget?) ...[
              SizedBox(width: AppSpacing.containerSm),
              trailingWidget,
            ],
          ],
        ),
      ),
    );
  }
}
