import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';

/// 手机双列发现卡。
///
/// 同源消费 [PostBaseDto]，只压缩展示密度，不新建第二套 feed 数据。
/// 完整正文、复杂互动和长交集解释留给详情页 / full-span 模块。
class DualColumnDiscoveryPostCard extends StatelessWidget {
  const DualColumnDiscoveryPostCard({
    super.key,
    required this.item,
    required this.isDark,
    required this.isLiked,
    required this.likeCount,
    required this.onTap,
    required this.onUserTap,
    required this.onLikeTap,
  });

  final PostBaseDto item;
  final bool isDark;
  final bool isLiked;
  final int likeCount;
  final VoidCallback onTap;
  final VoidCallback onUserTap;
  final VoidCallback onLikeTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final title = _headline;
    final reasonText = IntersectionReasonChip.primaryText(
      item.intersectionReasons,
    );

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(
            AppSpacing.contentPreviewCornerRadius,
          ),
          border: Border.all(color: border, width: AppSpacing.hairline),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(
            AppSpacing.contentPreviewCornerRadius,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              _Cover(item: item, isDark: isDark),
              Padding(
                padding: EdgeInsets.all(AppSpacing.postPreviewCardPadding),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (reasonText != null) ...[
                      IntersectionReasonChip(text: reasonText, isDark: isDark),
                      SizedBox(height: AppSpacing.intraGroupXs),
                    ],
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.semiBold,
                        color: fg,
                        height: AppSpacing.textLineHeightDense,
                        letterSpacing: -0.16,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupSm),
                    Row(
                      children: [
                        Expanded(
                          child: GestureDetector(
                            onTap: onUserTap,
                            behavior: HitTestBehavior.opaque,
                            child: Text(
                              item.displayName,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: AppTypography.iosCaption1,
                                color: secondary,
                              ),
                            ),
                          ),
                        ),
                        SizedBox(width: AppSpacing.intraGroupXs),
                        _LikeCompactButton(
                          isLiked: isLiked,
                          likeCount: likeCount,
                          color: secondary,
                          onPressed: onLikeTap,
                        ),
                      ],
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

  String get _headline {
    final title = item.normalizedTitle;
    if (title.isNotEmpty) return title;
    final body = item.normalizedBody;
    if (body.isNotEmpty) return body;
    return item.displayName;
  }
}

class _LikeCompactButton extends StatelessWidget {
  const _LikeCompactButton({
    required this.isLiked,
    required this.likeCount,
    required this.color,
    required this.onPressed,
  });

  final bool isLiked;
  final int likeCount;
  final Color color;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final label = formatCompactActionCount(likeCount);
    return LayoutBuilder(
      builder: (context, constraints) {
        final showCount = label.isNotEmpty && constraints.maxWidth >= 54;
        return CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: const Size(28, 28),
          onPressed: onPressed,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
                size: AppSpacing.iconSmall,
                color: isLiked ? AppColors.error : color,
              ),
              if (showCount) ...[
                SizedBox(width: AppSpacing.two),
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.fade,
                    softWrap: false,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption2,
                      color: color,
                    ),
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _Cover extends StatelessWidget {
  const _Cover({required this.item, required this.isDark});

  final PostBaseDto item;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final visual = item.primaryVisualUrl;
    final ratio = item.aspectRatio;
    final aspectRatio = ratio == null || ratio <= 0
        ? 4 / 5
        : ratio.clamp(0.72, 1.45);
    return AspectRatio(
      aspectRatio: aspectRatio.toDouble(),
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (visual.isEmpty)
            DecoratedBox(
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.surfaceMuted,
                ),
              ),
            )
          else
            CachedNetworkImage(
              imageUrl: visual,
              fit: BoxFit.cover,
              placeholder: (context, _) => DecoratedBox(
                decoration: BoxDecoration(
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.surfaceMuted,
                  ),
                ),
              ),
              errorWidget: (context, _, _) => DecoratedBox(
                decoration: BoxDecoration(
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.surfaceMuted,
                  ),
                ),
              ),
            ),
          if (item.isVideoLike)
            Align(
              alignment: Alignment.center,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: AppColors.black.withValues(alpha: 0.32),
                  shape: BoxShape.circle,
                ),
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.intraGroupSm),
                  child: Icon(
                    CupertinoIcons.play_fill,
                    color: AppColors.white,
                    size: AppSpacing.iconMedium,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
