import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

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
    this.mediaAspectRatio = 1.0,
    this.showVideoBadge = false,
    this.mediaOverlay,
    this.onHorizontalDragEnd,
  });

  final bool isDark;
  final String title;
  final String supportingText;
  final String coverUrl;
  final double mediaAspectRatio;
  final bool showVideoBadge;
  final Widget? mediaOverlay;
  final Widget footer;
  final VoidCallback onTap;
  final GestureDragEndCallback? onHorizontalDragEnd;

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
              color: Colors.black.withValues(alpha: isDark ? 0.14 : 0.05),
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
                  aspectRatio: mediaAspectRatio.clamp(9.0 / 16.0, 16.0 / 9.0),
                  child: ClipRRect(
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(
                        AppSpacing.contentPreviewCornerRadius,
                      ),
                    ),
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        CachedNetworkImage(
                          imageUrl: coverUrl,
                          fit: BoxFit.cover,
                          placeholder: (context, url) => ColoredBox(
                            color: fgSecondary.withValues(alpha: 0.12),
                          ),
                          errorWidget: (context, url, error) => ColoredBox(
                            color: fgSecondary.withValues(alpha: 0.12),
                          ),
                        ),
                        if (showVideoBadge)
                          Positioned(
                            top: AppSpacing.postPreviewCardPadding,
                            right: AppSpacing.postPreviewCardPadding,
                            child: Icon(
                              CupertinoIcons.play_circle_fill,
                              color: Colors.white,
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
                        maxLines: 2,
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
