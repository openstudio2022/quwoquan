part of 'search_network_results_page.dart';

class _SearchPageFlatCard extends StatelessWidget {
  const _SearchPageFlatCard({
    required this.item,
    required this.isDark,
    required this.onTap,
  });

  final SearchPageResultItem item;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final primary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final detail = item.subtitle?.trim().isNotEmpty == true
        ? item.subtitle!.trim()
        : item.snippet?.trim();
    final thumbnail = item.thumbnailUrl?.trim() ?? '';
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: CupertinoButton(
        key: ValueKey<String>('search_page_result_action_${item.objectRef}'),
        padding: EdgeInsets.all(AppSpacing.containerSm),
        minimumSize: const Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.minInteractiveSize,
        ),
        onPressed: onTap,
        child: Row(
          children: <Widget>[
            SizedBox.square(
              dimension: AppSpacing.avatarUserLg,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.containerXs),
                child: mediaDeliveryImage(
                  binding: MediaDeliveryBinding(
                    assetId: item.thumbnailAssetId?.trim() ?? '',
                    accessMode: item.thumbnailAccessMode,
                    publicUrl: thumbnail,
                  ),
                  kind: MediaDeliveryKind.image,
                  fit: BoxFit.cover,
                  absentWidget: ColoredBox(
                    color: AppColors.primaryColor.withValues(alpha: 0.08),
                    child: Icon(
                      CupertinoIcons.search,
                      color: AppColors.primaryColor,
                      size: AppSpacing.iconMedium,
                    ),
                  ),
                  publicBuilder: (context, publicUrl) => AppCachedNetworkImage(
                    imageUrl: publicUrl,
                    fit: BoxFit.cover,
                    cdnPreset: CdnImagePreset.thumbnail,
                    placeholder: const SizedBox.shrink(),
                    errorWidget: const SizedBox.shrink(),
                  ),
                ),
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    item.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: primary,
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                  if (detail != null && detail.isNotEmpty) ...<Widget>[
                    SizedBox(height: AppSpacing.two),
                    Text(
                      detail,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: secondary,
                        fontSize: AppTypography.iosCaption1,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
            Icon(
              CupertinoIcons.chevron_forward,
              color: secondary,
              size: AppSpacing.iconSmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _IntersectionCardPlaceholder extends StatelessWidget {
  const _IntersectionCardPlaceholder({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.primaryColor.withValues(alpha: 0.08),
      child: Center(
        child: Icon(
          icon,
          color: AppColors.primaryColor,
          size: AppSpacing.iconLarge,
        ),
      ),
    );
  }
}

class _IntersectionCard extends StatelessWidget {
  const _IntersectionCard({
    required this.model,
    required this.isDark,
    required this.onTap,
  });

  final _IntersectionCardModel model;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
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
    final hasCover = model.coverUrl.trim().isNotEmpty;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(
              aspectRatio: 16 / 10,
              child: ClipRRect(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(AppSpacing.contentPreviewCornerRadius),
                ),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    if (hasCover)
                      mediaDeliveryImage(
                        binding: model.coverBinding.hasRenderableSource
                            ? model.coverBinding
                            : MediaDeliveryBinding(
                                assetId: '',
                                accessMode: null,
                                publicUrl: model.coverUrl,
                              ),
                        kind: MediaDeliveryKind.image,
                        fit: BoxFit.cover,
                        publicBuilder: (context, publicUrl) =>
                            AppCachedNetworkImage(
                              imageUrl: publicUrl,
                              fit: BoxFit.cover,
                              cdnPreset: CdnImagePreset.cover,
                              placeholder: _IntersectionCardPlaceholder(
                                icon: model.categoryIcon,
                              ),
                              errorWidget: _IntersectionCardPlaceholder(
                                icon: model.categoryIcon,
                              ),
                            ),
                        absentWidget: _IntersectionCardPlaceholder(
                          icon: model.categoryIcon,
                        ),
                      )
                    else
                      _IntersectionCardPlaceholder(icon: model.categoryIcon),
                    Positioned(
                      top: AppSpacing.postPreviewCardPadding,
                      left: AppSpacing.postPreviewCardPadding,
                      child: _MediaCategoryBadge(label: model.categoryLabel),
                    ),
                    if (model.showVideoBadge)
                      Positioned(
                        top: AppSpacing.postPreviewCardPadding,
                        right: AppSpacing.postPreviewCardPadding,
                        child: Icon(
                          CupertinoIcons.play_circle_fill,
                          color: AppColors.white,
                          size: AppSpacing.iconLarge - AppSpacing.xs,
                        ),
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
                    model.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.medium,
                      color: fgPrimary,
                    ),
                  ),
                  // §3：交集句只在有云侧文案时展示；无 primaryText 不渲染句行、不占位。
                  if (model.reasonText.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Row(
                      children: [
                        Icon(
                          model.reasonIcon,
                          size: AppSpacing.iconSmall,
                          color: AppColors.primaryColor,
                        ),
                        SizedBox(width: AppSpacing.two),
                        Expanded(
                          child: Text(
                            model.reasonText,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.iosCaption1,
                              color: AppColors.primaryColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                  SizedBox(height: AppSpacing.two),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          model.footerText,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosCaption1,
                            color: fgSecondary,
                          ),
                        ),
                      ),
                      if (model.metricLabel != null) ...[
                        SizedBox(width: AppSpacing.intraGroupXs),
                        ContentCardMetric(
                          icon: model.metricIcon ?? CupertinoIcons.heart,
                          label: model.metricLabel!,
                          color: fgSecondary,
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _UserSearchResultCard extends StatelessWidget {
  const _UserSearchResultCard({
    required this.hit,
    required this.isDark,
    required this.onTap,
  });

  final SearchHit hit;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final user = hit.asUserProfileItem;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final reason = _SearchNetworkResultsPageState._hitIntersectionPrimaryText(
      hit,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        minimumSize: const Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.minInteractiveSize,
        ),
        onPressed: onTap,
        child: Row(
          children: <Widget>[
            Container(
              width: AppSpacing.avatarUserLg,
              height: AppSpacing.avatarUserLg,
              decoration: BoxDecoration(
                color: AppColors.primaryColor.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(
                CupertinoIcons.person_fill,
                size: AppSpacing.iconMedium,
                color: AppColors.primaryColor,
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    user?.displayName ?? hit.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                      color: fgPrimary,
                    ),
                  ),
                  if ((user?.bio ?? hit.snippet ?? '').trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.two),
                    Text(
                      (user?.bio ?? hit.snippet ?? '').trim(),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                  if (reason.isNotEmpty) ...[
                    SizedBox(height: AppSpacing.two),
                    Text(
                      reason,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: fgSecondary,
            ),
          ],
        ),
      ),
    );
  }
}

class _EntityTopResultCard extends StatelessWidget {
  const _EntityTopResultCard({
    required this.entity,
    required this.isDark,
    required this.onTap,
  });

  final _EntityTopResultModel entity;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
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
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Row(
          children: [
            Container(
              width: AppSpacing.avatarUserLg,
              height: AppSpacing.avatarUserLg,
              decoration: BoxDecoration(
                color: AppColors.primaryColor.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(
                CupertinoIcons.building_2_fill,
                size: AppSpacing.iconMedium,
                color: AppColors.primaryColor,
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          entity.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: _SearchResultTokens.sectionTitleSize,
                            fontWeight: _SearchResultTokens.sectionTitleWeight,
                            color: fgPrimary,
                          ),
                        ),
                      ),
                      SizedBox(width: AppSpacing.intraGroupSm),
                      Text(
                        entity.badge,
                        style: TextStyle(
                          fontSize: _SearchResultTokens.captionSize,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpacing.two),
                  Text(
                    entity.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: _SearchResultTokens.captionSize,
                      color: fgSecondary,
                    ),
                  ),
                  if (entity.connectionReason != null &&
                      entity.connectionReason!.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.two),
                    Text(
                      entity.connectionReason!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.captionSize,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  ],
                  if (entity.description.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.two),
                    Text(
                      entity.description,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.captionSize,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                  if (entity.meta.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.two),
                    Text(
                      entity.meta,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.captionSize,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            if (entity.actionLabel != null) ...[
              DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  border: Border.all(color: AppColors.primaryColor),
                ),
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  child: Text(
                    entity.actionLabel!,
                    style: TextStyle(
                      fontSize: _SearchResultTokens.captionSize,
                      color: AppColors.primaryColor,
                    ),
                  ),
                ),
              ),
            ] else
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconSmall,
                color: fgSecondary,
              ),
          ],
        ),
      ),
    );
  }
}

class _LocationPlaceTopResultCard extends StatelessWidget {
  const _LocationPlaceTopResultCard({
    required this.place,
    required this.isDark,
    required this.onTap,
  });

  final SearchLocationPlaceHitView place;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final primary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Row(
          children: <Widget>[
            Icon(
              CupertinoIcons.location_solid,
              size: AppSpacing.iconMedium,
              color: AppColors.primaryColor,
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    place.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                      color: primary,
                    ),
                  ),
                  SizedBox(height: AppSpacing.two),
                  Text(
                    place.address?.trim().isNotEmpty == true
                        ? place.address!
                        : SearchText.searchCategoryLocation,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: secondary,
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: secondary,
            ),
          ],
        ),
      ),
    );
  }
}

class _RelatedSearchCard extends StatelessWidget {
  const _RelatedSearchCard({
    required this.card,
    required this.isDark,
    required this.onTap,
  });

  final RelatedSearchTermCardView card;
  final bool isDark;
  final ValueChanged<NetworkSearchSuggestion> onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
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
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              SearchText.searchRelatedTitle,
              style: TextStyle(
                fontSize: _SearchResultTokens.cardTitleSize,
                fontWeight: _SearchResultTokens.sectionTitleWeight,
                color: fgPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            for (var i = 0; i < card.terms.length; i++)
              Padding(
                padding: EdgeInsets.only(
                  bottom: i == card.terms.length - 1
                      ? 0
                      : AppSpacing.intraGroupSm,
                ),
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: () => onTap(card.terms[i]),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      card.terms[i].displayTitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.bodySize,
                        fontWeight: _SearchResultTokens.bodyWeight,
                        color: fgPrimary,
                      ),
                    ),
                  ),
                ),
              ),
            if (card.terms.isEmpty)
              Text(
                SearchText.searchRelatedEmpty,
                style: TextStyle(
                  fontSize: _SearchResultTokens.captionSize,
                  color: fgSecondary,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
