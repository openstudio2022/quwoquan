part of 'global_search_page.dart';

class _SearchHomeTabBar extends StatelessWidget {
  const _SearchHomeTabBar({
    required this.activeTab,
    required this.availableTabs,
    required this.onChanged,
    this.onRefresh,
  });

  final _SearchHomeTab activeTab;
  final Set<_SearchHomeTab> availableTabs;
  final ValueChanged<_SearchHomeTab> onChanged;
  final VoidCallback? onRefresh;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final tabs = <_SearchHomeTab, String>{
      _SearchHomeTab.guess: SearchText.searchHomeGuessTitle,
      _SearchHomeTab.circles: SearchText.searchHomeDiscoverCirclesTitle,
      _SearchHomeTab.locations: SearchText.searchHomeDiscoverLocationsTitle,
    };
    return Row(
      children: [
        for (final entry in tabs.entries.where(
          (entry) => availableTabs.contains(entry.key),
        )) ...[
          _SearchHomeTabButton(
            label: entry.value,
            selected: entry.key == activeTab,
            isDark: isDark,
            onTap: () => onChanged(entry.key),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
        ],
        const Spacer(),
        if (onRefresh != null)
          CupertinoButton(
            key: const ValueKey<String>('search_home_guess_refresh_button'),
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
            onPressed: onRefresh,
            child: Icon(
              CupertinoIcons.refresh,
              size: AppSpacing.iconMedium,
              color: AppColors.primaryColor,
            ),
          ),
      ],
    );
  }
}

class _SearchHomeTabButton extends StatelessWidget {
  const _SearchHomeTabButton({
    required this.label,
    required this.selected,
    required this.isDark,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: selected
              ? AppColors.primaryColor.withValues(alpha: 0.1)
              : CupertinoColors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupXs,
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: selected
                  ? AppTypography.medium
                  : _SearchTokens.bodyWeight,
              color: selected ? AppColors.primaryColor : fgSecondary,
            ),
          ),
        ),
      ),
    );
  }
}

class _GuessKeywordSection extends StatelessWidget {
  const _GuessKeywordSection({
    required this.terms,
    required this.isDark,
    this.showHeader = true,
    required this.onTap,
  });

  final List<NetworkSearchSuggestion> terms;
  final bool isDark;
  final bool showHeader;
  final ValueChanged<NetworkSearchSuggestion> onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (showHeader) ...[
          const _SearchSectionHeader(title: SearchText.searchHomeGuessTitle),
          SizedBox(height: _SearchTokens.headerContentGap),
        ],
        GridView.builder(
          shrinkWrap: true,
          padding: EdgeInsets.zero,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: terms.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            mainAxisExtent: AppSpacing.buttonHeightMd,
            crossAxisSpacing: _SearchTokens.historyColumnGap,
            mainAxisSpacing: _SearchTokens.historyRowGap,
          ),
          itemBuilder: (context, index) {
            final term = terms[index];
            return CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              onPressed: () => onTap(term),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  term.displayTitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: _SearchTokens.bodySize,
                    fontWeight: _SearchTokens.bodyWeight,
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundPrimary,
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ],
    );
  }
}

enum _DiscoverEntityImageStyle { avatar, cover }

class _DiscoverEntityListSection extends StatelessWidget {
  const _DiscoverEntityListSection({
    required this.title,
    required this.items,
    required this.isDark,
    this.showHeader = true,
    required this.fallbackIcon,
    required this.imageStyle,
    required this.onTap,
  });

  final String title;
  final List<SearchInspirationCardView> items;
  final bool isDark;
  final bool showHeader;
  final IconData fallbackIcon;
  final _DiscoverEntityImageStyle imageStyle;
  final ValueChanged<SearchInspirationCardView> onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (showHeader) ...[
          _SearchSectionHeader(title: title),
          SizedBox(height: _SearchTokens.headerContentGap),
        ],
        for (var i = 0; i < items.length; i++) ...[
          _DiscoverEntityListTile(
            item: items[i],
            isDark: isDark,
            fallbackIcon: fallbackIcon,
            imageStyle: imageStyle,
            onTap: () => onTap(items[i]),
          ),
          if (i != items.length - 1) SizedBox(height: AppSpacing.intraGroupSm),
        ],
      ],
    );
  }
}

class _DiscoverEntityListTile extends StatelessWidget {
  const _DiscoverEntityListTile({
    required this.item,
    required this.isDark,
    required this.fallbackIcon,
    required this.imageStyle,
    required this.onTap,
  });

  final SearchInspirationCardView item;
  final bool isDark;
  final IconData fallbackIcon;
  final _DiscoverEntityImageStyle imageStyle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
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
      ColorType.backgroundSecondary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final imageUrl = (item.coverUrl ?? '').trim();
    final imageSize = imageStyle == _DiscoverEntityImageStyle.avatar
        ? AppSpacing.avatarUserMd
        : AppSpacing.avatarUserLg;
    final categoryLabel = imageStyle == _DiscoverEntityImageStyle.avatar
        ? SearchText.searchCategoryCircle
        : SearchText.searchCategoryLocation;
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      onPressed: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(
            AppSpacing.contentPreviewCornerRadius,
          ),
          border: Border.all(color: border),
        ),
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(
                  imageStyle == _DiscoverEntityImageStyle.avatar
                      ? imageSize / 2
                      : AppSpacing.smallBorderRadius,
                ),
                child: SizedBox.square(
                  dimension: imageSize,
                  child: imageUrl.isEmpty
                      ? Icon(
                          fallbackIcon,
                          size: AppSpacing.iconMedium,
                          color: fgSecondary,
                        )
                      : AppCachedNetworkImage(
                          imageUrl: imageUrl,
                          fit: BoxFit.cover,
                          width: imageSize,
                          height: imageSize,
                          cdnPreset:
                              imageStyle == _DiscoverEntityImageStyle.avatar
                              ? CdnImagePreset.avatar
                              : CdnImagePreset.cover,
                          errorWidget: Icon(
                            fallbackIcon,
                            size: AppSpacing.iconMedium,
                            color: fgSecondary,
                          ),
                        ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            item.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: _SearchTokens.bodySize,
                              fontWeight: _SearchTokens.bodyWeight,
                              color: fgPrimary,
                            ),
                          ),
                        ),
                        SizedBox(width: AppSpacing.intraGroupSm),
                        DecoratedBox(
                          decoration: BoxDecoration(
                            color: AppColorsFunctional.getColor(
                              isDark,
                              ColorType.backgroundTertiary,
                            ),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.fullBorderRadius,
                            ),
                          ),
                          child: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.intraGroupSm,
                              vertical: AppSpacing.two,
                            ),
                            child: Text(
                              categoryLabel,
                              style: TextStyle(
                                fontSize: _SearchTokens.captionSize,
                                color: fgSecondary,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: AppSpacing.two),
                    Text(
                      item.subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchTokens.captionSize,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconSmall,
                color: fgSecondary,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
