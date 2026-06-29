part of 'homepage_detail_shell.dart';

class HomepageIdentityHeader extends StatelessWidget {
  const HomepageIdentityHeader({
    super.key,
    required this.title,
    required this.subtitle,
    required this.metaLine,
    this.coverUrl,
    this.trailing,
  });

  final String title;
  final String subtitle;
  final String metaLine;
  final String? coverUrl;
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

    final image = (coverUrl ?? '').trim().isEmpty
        ? fallback
        : AppMediaImage(
            imageSource: coverUrl!,
            fit: BoxFit.cover,
            placeholder: fallback,
            errorWidget: fallback,
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

class _HomepageActionBar extends StatelessWidget {
  const _HomepageActionBar({
    required this.isFollowing,
    required this.onToggleFollow,
    required this.onPublishRecord,
  });

  final bool isFollowing;
  final VoidCallback onToggleFollow;
  final VoidCallback? onPublishRecord;

  @override
  Widget build(BuildContext context) {
    Widget filled({
      required String label,
      required IconData icon,
      required VoidCallback? onPressed,
    }) {
      return ProfileIosActionButton(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: ProfileIosActionStyle.filled,
        labelFontWeight: AppTypography.medium,
      );
    }

    Widget outlined({
      required String label,
      required IconData icon,
      required VoidCallback? onPressed,
    }) {
      return ProfileIosActionButton(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: ProfileIosActionStyle.outlined,
        backgroundColor: AppColors.iosSecondaryFill(context),
        foregroundColor: AppColors.iosLabel(context),
        borderColor: AppColors.iosSeparator(context).withValues(alpha: 0.14),
        labelFontWeight: AppTypography.medium,
      );
    }

    Widget followAction() {
      if (isFollowing) {
        return outlined(
          label: UITextConstants.following,
          icon: CupertinoIcons.check_mark,
          onPressed: onToggleFollow,
        );
      }
      return filled(
        label: UITextConstants.follow,
        icon: CupertinoIcons.add,
        onPressed: onToggleFollow,
      );
    }

    return Row(
      children: <Widget>[
        Expanded(child: followAction()),
        SizedBox(width: AppSpacing.sm),
        Expanded(
          child: outlined(
            label: UITextConstants.entityActionPublishRecord,
            icon: CupertinoIcons.pencil,
            onPressed: onPublishRecord,
          ),
        ),
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
    final dimensionScores = summary?.dimensionScores ?? const [];
    final highlightTags = summary?.highlightTags ?? const [];

    return ProfileIosSectionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            '${averageRating.toStringAsFixed(1)} 分',
            style: TextStyle(
              fontSize: AppTypography.iosLargeTitle,
              fontWeight: AppTypography.bold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            '$ratingCount 条评分',
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          if (dimensionScores.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.containerSm),
            for (
              var index = 0;
              index < dimensionScores.length;
              index += 1
            ) ...<Widget>[
              if (index > 0)
                Padding(
                  padding: EdgeInsets.symmetric(
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  child: Divider(
                    height: AppSpacing.one,
                    color: AppColors.iosSeparator(
                      context,
                    ).withValues(alpha: 0.12),
                  ),
                ),
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      dimensionScores[index].label,
                      style: TextStyle(
                        fontSize: AppTypography.iosBody,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                  ),
                  Text(
                    dimensionScores[index].score.toStringAsFixed(1),
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.medium,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                ],
              ),
            ],
          ],
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
