import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/content_post_media_aspect_ratio.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';

/// 组件库中的 Post 预览卡片骨架。
///
/// 统一承载封面、标题、配文与卡片材质，底部信息通过 [footer]
/// 作为插槽注入，便于后续扩展不同形态的 post 卡片。
class PostPreviewCard extends StatelessWidget {
  const PostPreviewCard({
    super.key,
    required this.isDark,
    required this.title,
    required this.footer,
    required this.onTap,
    this.supportingText = '',
    this.coverUrl = '',
    this.coverBinding = const MediaDeliveryBinding.absent(),
    this.mediaAspectRatio = 1.0,
    this.showVideoBadge = false,
    this.mediaContent,
    this.mediaOverlay,
    this.header,
    this.onHorizontalDragEnd,
    this.supportingTextMaxLines = 2,
  });

  final bool isDark;
  final String title;
  final String supportingText;
  final String coverUrl;

  /// 封面的 typed 交付绑定（DEC-033）。绑定在场即由唯一分流入口决定走私有短签
  /// 还是公开候选；缺席时退回 [coverUrl] 的公开路，本骨架不从 URL 形态反推。
  final MediaDeliveryBinding coverBinding;
  final double mediaAspectRatio;
  final bool showVideoBadge;
  final Widget? mediaContent;
  final Widget? mediaOverlay;

  /// 卡内顶部插槽（封面下、标题上）：统一记录卡范式的「唯一交集句」位。
  final Widget? header;
  final Widget footer;
  final VoidCallback? onTap;
  final GestureDragEndCallback? onHorizontalDragEnd;
  final int supportingTextMaxLines;

  bool get _hasCover => coverUrl.trim().isNotEmpty;

  bool get _hasSupportingText => supportingText.trim().isNotEmpty;

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

    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onHorizontalDragEnd: onHorizontalDragEnd,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: cardBg,
          borderRadius: BorderRadius.circular(
            AppSpacing.contentPreviewCornerRadius,
          ),
          border: Border.all(color: borderColor),
          boxShadow: [
            BoxShadow(
              color: AppColors.black.withValues(alpha: isDark ? 0.14 : 0.05),
              blurRadius: AppSpacing.containerMd,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: Size.zero,
          onPressed: onTap,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_hasCover)
                AspectRatio(
                  aspectRatio: clampContentPostMediaAspectRatio(
                    mediaAspectRatio,
                    min: 9.0 / 16.0,
                    max: 16.0 / 9.0,
                  ),
                  child: ClipRRect(
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(
                        AppSpacing.contentPreviewCornerRadius,
                      ),
                    ),
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        mediaContent ??
                            mediaDeliveryImage(
                              binding: coverBinding.hasRenderableSource
                                  ? coverBinding
                                  : MediaDeliveryBinding.legacyPublic(
                                      publicUrl: coverUrl,
                                    ),
                              kind: MediaDeliveryKind.image,
                              fit: BoxFit.cover,
                              placeholder: ColoredBox(
                                color: fgSecondary.withValues(alpha: 0.12),
                              ),
                              errorWidget: ColoredBox(
                                color: fgSecondary.withValues(alpha: 0.12),
                              ),
                              absentWidget: ColoredBox(
                                color: fgSecondary.withValues(alpha: 0.12),
                              ),
                              publicBuilder: (context, publicUrl) =>
                                  AppCachedNetworkImage(
                                    imageUrl: publicUrl,
                                    fit: BoxFit.cover,
                                    cdnPreset: CdnImagePreset.cover,
                                    placeholder: ColoredBox(
                                      color: fgSecondary.withValues(
                                        alpha: 0.12,
                                      ),
                                    ),
                                    errorWidget: ColoredBox(
                                      color: fgSecondary.withValues(
                                        alpha: 0.12,
                                      ),
                                    ),
                                  ),
                            ),
                        if (showVideoBadge)
                          Positioned(
                            top: AppSpacing.postPreviewCardPadding,
                            right: AppSpacing.postPreviewCardPadding,
                            child: Icon(
                              CupertinoIcons.play_circle_fill,
                              color: AppColors.white,
                              size: AppSpacing.iconLarge - AppSpacing.xs,
                            ),
                          ),
                        if (mediaOverlay case final overlay?)
                          Positioned(
                            top: AppSpacing.postPreviewCardPadding,
                            left: AppSpacing.postPreviewCardPadding,
                            child: overlay,
                          ),
                      ],
                    ),
                  ),
                ),
              Padding(
                padding: EdgeInsets.all(AppSpacing.postPreviewCardPadding),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (header case final header?) ...[
                      header,
                      SizedBox(height: AppSpacing.intraGroupXs),
                    ],
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.medium,
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
                    const SizedBox(height: AppSpacing.xs),
                    footer,
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

/// Post 卡片底部使用的紧凑操作指标。
class PostCardMetric extends StatelessWidget {
  const PostCardMetric({
    super.key,
    required this.icon,
    required this.label,
    required this.color,
    this.iconSize = AppSpacing.iconSmall,
    this.textStyle,
    this.iconColor,
  });

  final IconData icon;
  final String label;
  final Color color;
  final double iconSize;
  final TextStyle? textStyle;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    final effectiveTextStyle =
        textStyle ??
        TextStyle(fontSize: AppTypography.iosCaption1, color: color);

    return FittedBox(
      fit: BoxFit.scaleDown,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: iconSize, color: iconColor ?? color),
          SizedBox(width: AppSpacing.intraGroupXs / 2),
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: effectiveTextStyle,
          ),
        ],
      ),
    );
  }
}
