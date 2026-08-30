part of 'homepage_detail_shell.dart';

class HomepageIdentityHeader extends StatelessWidget {
  const HomepageIdentityHeader({
    super.key,
    required this.title,
    required this.subtitle,
    required this.metaLine,
    this.coverBinding = const MediaDeliveryBinding.absent(),
    this.trailing,
  });

  final String title;
  final String subtitle;
  final String metaLine;

  /// 对象主页 hero 封面的 typed 交付绑定（DEC-033）。绑定由投影的
  /// coverAssetId/coverAccessMode 交出，本组件不从 URL 形态推断交付形态。
  final MediaDeliveryBinding coverBinding;
  final Widget? trailing;

  static const double _coverBorder = AppSpacing.three;
  static const double coverExtent = AppSpacing.avatarUserXl;
  static const double coverRadius = AppSpacing.radiusTwentyFour;
  static const double _coverOverlapRatio = 0.34;

  static double get coverOuterExtent => coverExtent + (_coverBorder * 2);
  static double get coverIntrusion => coverOuterExtent * _coverOverlapRatio;

  Widget _buildCover(BuildContext context) {
    final fallback = DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(coverRadius),
      ),
      child: Icon(
        CupertinoIcons.photo_fill_on_rectangle_fill,
        size: AppSpacing.iconLarge,
        color: AppColors.iosSecondaryLabel(context),
      ),
    );

    final image = mediaDeliveryImage(
      binding: coverBinding,
      kind: MediaDeliveryKind.image,
      fit: BoxFit.cover,
      placeholder: fallback,
      errorWidget: fallback,
      absentWidget: fallback,
      publicBuilder: (context, publicUrl) => AppMediaImage(
        imageSource: publicUrl,
        fit: BoxFit.cover,
        placeholder: fallback,
        errorWidget: fallback,
      ),
    );

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(coverRadius + _coverBorder),
        border: Border.all(
          color: AppColors.iosProfileSurface(context),
          width: _coverBorder,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.12),
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(coverRadius),
        child: SizedBox(width: coverExtent, height: coverExtent, child: image),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        Padding(
          padding: EdgeInsets.only(left: coverOuterExtent + AppSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Expanded(
                    child: Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosTitle2,
                        fontWeight: AppTypography.bold,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                  ),
                  if (trailing != null) ...<Widget>[
                    SizedBox(width: AppSpacing.containerSm),
                    trailing!,
                  ],
                ],
              ),
              if (subtitle.trim().isNotEmpty) ...<Widget>[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  subtitle,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    color: AppColors.iosSecondaryLabel(context),
                    height: AppSpacing.textLineHeightBody,
                  ),
                ),
              ],
              if (metaLine.trim().isNotEmpty) ...<Widget>[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  metaLine,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: AppColors.iosSecondaryLabel(context),
                    height: AppSpacing.textLineHeightBody,
                  ),
                ),
              ],
            ],
          ),
        ),
        Positioned(top: -coverIntrusion, left: 0, child: _buildCover(context)),
      ],
    );
  }
}

class _HomepageReviewCard extends StatelessWidget {
  const _HomepageReviewCard({
    required this.summary,
    required this.fallbackAverageRating,
    required this.fallbackRatingCount,
  });

  final HomepageReviewSummaryData? summary;
  final double? fallbackAverageRating;
  final int fallbackRatingCount;

  @override
  Widget build(BuildContext context) {
    final averageRating = summary?.averageRating ?? fallbackAverageRating ?? 0;
    final ratingCount = summary?.ratingCount ?? fallbackRatingCount;
    final highlightTags = summary?.highlightTags ?? const [];

    return ProfileIosSectionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            UITextConstants.homepageRatingScore(
              averageRating.toStringAsFixed(1),
            ),
            style: TextStyle(
              fontSize: AppTypography.iosLargeTitle,
              fontWeight: AppTypography.bold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            UITextConstants.homepageRatingCount(ratingCount),
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          if (highlightTags.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.containerSm),
            Wrap(
              spacing: AppSpacing.intraGroupXs,
              runSpacing: AppSpacing.intraGroupXs,
              children: highlightTags
                  .map(
                    (tag) =>
                        _HomepageSummaryChipWidget(label: tag, accent: true),
                  )
                  .toList(growable: false),
            ),
          ],
        ],
      ),
    );
  }
}
