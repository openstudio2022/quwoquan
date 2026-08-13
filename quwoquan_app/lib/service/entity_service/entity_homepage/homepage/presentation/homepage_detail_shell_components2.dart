part of 'homepage_detail_shell.dart';

class _HomepagePreviewCell extends StatelessWidget {
  const _HomepagePreviewCell({
    required this.title,
    required this.subtitle,
    required this.label,
    required this.icon,
  });

  final String title;
  final String subtitle;
  final String label;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final leading = _HomepagePreviewCover(coverUrl: null, icon: icon);
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerSm,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          leading,
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                _HomepageSummaryChipWidget(label: label, accent: false),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: AppTypography.medium,
                    color: AppColors.iosLabel(context),
                    height: AppSpacing.textLineHeightBody,
                  ),
                ),
                if (subtitle.trim().isNotEmpty) ...<Widget>[
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
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
        ],
      ),
    );
  }
}

class _HomepagePreviewCover extends StatelessWidget {
  const _HomepagePreviewCover({required this.coverUrl, required this.icon});

  final String? coverUrl;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final fallback = DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyFour),
      ),
      child: Icon(
        icon,
        size: AppSpacing.iconMedium,
        color: AppColors.iosSecondaryLabel(context),
      ),
    );

    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyFour),
      child: SizedBox(
        width: AppSpacing.oneHundred - AppSpacing.twentyEight,
        height: AppSpacing.oneHundred - AppSpacing.twentyEight,
        child: (coverUrl ?? '').trim().isEmpty
            ? fallback
            : AppMediaImage(
                imageSource: coverUrl!,
                fit: BoxFit.cover,
                placeholder: fallback,
                errorWidget: fallback,
              ),
      ),
    );
  }
}

class _HomepageRelatedCircleCard extends StatelessWidget {
  const _HomepageRelatedCircleCard({required this.group});

  final HomepageRelatedGroupSummary group;

  @override
  Widget build(BuildContext context) {
    final title = group.name.trim().isNotEmpty
        ? group.name.trim()
        : ObjectHomepageText.objectTabRelatedCircles;
    final linkedTitle = (group.linkedHomepageTitle ?? '').trim();
    final reason = linkedTitle.isNotEmpty
        ? HomepageDetailText.relatedGroupReasonFor(linkedTitle)
        : HomepageDetailText.relatedGroupDefaultReason;
    final memberLine = group.memberCount > 0
        ? HomepageDetailText.relatedGroupMemberLine(
            formatCompactActionCount(group.memberCount),
          )
        : '';
    final accent = AppColors.iosAccent(context);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Container(
          width: AppSpacing.buttonHeight,
          height: AppSpacing.buttonHeight,
          decoration: BoxDecoration(
            color: accent.withValues(alpha: isDark ? 0.18 : 0.10),
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyFour),
          ),
          child: Icon(
            CupertinoIcons.person_3_fill,
            size: AppSpacing.iconMedium,
            color: accent,
          ),
        ),
        SizedBox(width: AppSpacing.containerSm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosLabel(context),
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                reason,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosSecondaryLabel(context),
                  height: AppSpacing.textLineHeightBody,
                ),
              ),
              SizedBox(height: AppSpacing.containerSm),
              Row(
                children: <Widget>[
                  if (memberLine.isNotEmpty)
                    Expanded(
                      child: Text(
                        memberLine,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosCaption1,
                          color: AppColors.iosTertiaryLabel(context),
                        ),
                      ),
                    )
                  else
                    const Spacer(),
                  _HomepageSummaryChipWidget(
                    label: HomepageDetailText.relatedGroupOpenAction,
                    accent: true,
                  ),
                ],
              ),
            ],
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Icon(
          CupertinoIcons.chevron_forward,
          size: AppSpacing.iconXSmall,
          color: AppColors.iosTertiaryLabel(context),
        ),
      ],
    );
  }
}

class _HomepageBottomActionBar extends StatelessWidget {
  const _HomepageBottomActionBar({
    required this.enabled,
    required this.onPressed,
  });

  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        MediaQuery.paddingOf(context).bottom + AppSpacing.containerMd,
      ),
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context),
        border: Border(
          top: BorderSide(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.14),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: SizedBox(
        width: double.infinity,
        height: AppSpacing.buttonHeight,
        child: CupertinoButton.filled(
          key: TestKeys.homepageDetailAttachButton,
          onPressed: enabled ? onPressed : null,
          child: Text(
            enabled
                ? ObjectHomepageText.homepageAttachPublishEnabled
                : ObjectHomepageText.homepageAttachPublishDisabled,
          ),
        ),
      ),
    );
  }
}

class _HomepageSummaryChipWidget extends StatelessWidget {
  const _HomepageSummaryChipWidget({required this.label, required this.accent});

  final String label;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final accentColor = AppColors.iosAccent(context);
    final background = accent
        ? accentColor.withValues(alpha: 0.12)
        : AppColors.iosSecondaryFill(context);
    final foreground = accent
        ? accentColor
        : AppColors.iosSecondaryLabel(context);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: foreground,
        ),
      ),
    );
  }
}

class _HomepagePrimaryTabSpec {
  const _HomepagePrimaryTabSpec({required this.id, required this.label});

  final String id;
  final String label;
}

enum _HomepageMoreAction { share, claim, maintain, report }

String _contentTypeLabel(String contentType) {
  switch (contentType.trim()) {
    case 'article':
      return ObjectHomepageText.homepageContentTypeArticle;
    case 'video':
      return ObjectHomepageText.homepageContentTypeVideo;
    case 'image':
      return ObjectHomepageText.homepageContentTypeImage;
    case 'review':
      return ObjectHomepageText.homepageContentTypeOpinion;
    case 'question':
      return ObjectHomepageText.homepageContentTypeQuestion;
    default:
      return ObjectHomepageText.homepageContentTypeDefault;
  }
}
