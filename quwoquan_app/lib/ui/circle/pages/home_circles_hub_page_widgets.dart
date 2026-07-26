part of 'home_circles_hub_page.dart';

class _CirclesGlobalHeader extends StatelessWidget {
  const _CirclesGlobalHeader({
    required this.isDark,
    required this.activeModuleTab,
    required this.circles,
    required this.stories,
    required this.onStoryTap,
    required this.onModuleTabChanged,
    required this.onSeeMoreTap,
  });

  final bool isDark;
  final _HomeCirclesModuleTab activeModuleTab;
  final List<CircleDto> circles;
  final List<_HomeCircleStoryItem> stories;
  final void Function(
    _HomeCircleStoryItem item,
    List<_HomeCircleStoryItem> items,
  )
  onStoryTap;
  final ValueChanged<_HomeCirclesModuleTab> onModuleTabChanged;
  final VoidCallback onSeeMoreTap;

  double _circleCardWidth(BuildContext context) {
    return AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.bottomNavHeight * 1.7,
      regular: AppSpacing.bottomNavHeight * 1.9,
      expanded: AppSpacing.bottomNavHeight * 2.1,
    );
  }

  double _circleRailHeight(BuildContext context) {
    final cardWidth = _circleCardWidth(context);
    final coverHeight = cardWidth / _homeCircleCoverAspectRatio;
    final titleHeight = _measureSingleLineTextHeight(
      context,
      _homeCircleRailTitleTextStyle(),
    );
    final metaHeight = _measureSingleLineTextHeight(
      context,
      _homeCircleRailMetaTextStyle(),
    );
    final verticalPadding = AppSpacing.intraGroupXs * 2;
    final contentSpacing =
        AppSpacing.intraGroupXs + (AppSpacing.intraGroupXs / 2);
    return coverHeight +
        verticalPadding +
        contentSpacing +
        titleHeight +
        metaHeight +
        1;
  }

  @override
  Widget build(BuildContext context) {
    final cardSurface = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final horizontal = AppSpacing.feedContentHorizontal(context);
    final circleCardWidth = _circleCardWidth(context);

    return Container(
      color: cardSurface,
      padding: EdgeInsets.fromLTRB(
        horizontal,
        AppSpacing.containerXs,
        horizontal,
        AppSpacing.containerSm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  UITextConstants.circlesRecommendedTitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    fontWeight: AppTypography.medium,
                    color: fgSecondary.withValues(alpha: 0.78),
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              CupertinoButton(
                onPressed: onSeeMoreTap,
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                child: Text(
                  UITextConstants.seeMore,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: AppColors.primaryColor,
                    fontWeight: AppTypography.medium,
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          CupertinoSlidingSegmentedControl<_HomeCirclesModuleTab>(
            groupValue: activeModuleTab,
            children: <_HomeCirclesModuleTab, Widget>{
              _HomeCirclesModuleTab.recommended: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                ),
                child: Text(UITextConstants.circleScenarioRecommended),
              ),
              _HomeCirclesModuleTab.mine: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                ),
                child: Text(UITextConstants.circleScenarioMine),
              ),
            },
            onValueChanged: (value) {
              if (value != null) {
                onModuleTabChanged(value);
              }
            },
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          SizedBox(
            height: _circleRailHeight(context),
            child: ListView.separated(
              key: TestKeys.homeCirclesRecommendationRail,
              scrollDirection: Axis.horizontal,
              // 即使暂无推荐圈子也保留「查看全部」卡，避免空轨导致测试/首屏无法触达广场入口。
              itemCount: circles.length + 1,
              separatorBuilder: (context, index) =>
                  SizedBox(width: AppSpacing.intraGroupMd),
              itemBuilder: (context, index) {
                if (index == circles.length) {
                  return _HomeCircleViewAllCard(
                    width: circleCardWidth,
                    isDark: isDark,
                    onTap: onSeeMoreTap,
                  );
                }
                final circle = circles[index];
                return _HomeCircleRailCard(
                  circle: circle,
                  width: circleCardWidth,
                  isDark: isDark,
                  onTap: () => context.push(
                    AppRoutePaths.circleDetail(id: circle.id),
                    extra: const CircleDetailPageRouteExtra(
                      referralSource: ReferralSource.organicFeed,
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _StickyTabBarDelegate extends SliverPersistentHeaderDelegate {
  const _StickyTabBarDelegate({required this.child, required this.extent});

  final Widget child;
  final double extent;

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    return child;
  }

  @override
  double get maxExtent => extent;

  @override
  double get minExtent => extent;

  @override
  bool shouldRebuild(covariant _StickyTabBarDelegate oldDelegate) {
    return oldDelegate.child != child || oldDelegate.extent != extent;
  }
}

class _CirclesPrimaryCategoryTabBar extends StatelessWidget {
  const _CirclesPrimaryCategoryTabBar({
    required this.isDark,
    required this.categories,
    required this.activeCategoryId,
    required this.onCategoryTap,
    this.onHorizontalDragEnd,
  });

  final bool isDark;
  final List<MapEntry<String, CircleCategoryTabConfigDto>> categories;
  final String activeCategoryId;
  final ValueChanged<int> onCategoryTap;
  final GestureDragEndCallback? onHorizontalDragEnd;

  @override
  Widget build(BuildContext context) {
    final tabs = categories
        .map(
          (entry) => TabItem(
            id: entry.key,
            label: entry.value.label.isNotEmpty ? entry.value.label : entry.key,
          ),
        )
        .toList(growable: false);

    return CenteredScrollableTabBar(
      tabs: tabs,
      activeTab: activeCategoryId,
      onTabChange: (tabId) {
        final nextIndex = categories.indexWhere((entry) => entry.key == tabId);
        if (nextIndex < 0) {
          return;
        }
        onCategoryTap(nextIndex);
      },
      isDark: isDark,
      onHorizontalDragEnd: onHorizontalDragEnd,
      leftAlignedCompactMode: true,
    );
  }
}

class _CirclesSubCategoryBar extends StatelessWidget {
  const _CirclesSubCategoryBar({
    required this.isDark,
    required this.categoryId,
    required this.subCategories,
    required this.activeSubCategoryId,
    required this.onSubCategoryTap,
  });

  final bool isDark;
  final String categoryId;
  final List<String> subCategories;
  final String activeSubCategoryId;
  final ValueChanged<String> onSubCategoryTap;

  static double extent(BuildContext context) {
    final verticalPadding = AppSpacing.secondaryTabBarVerticalPadding(context);
    final chipVerticalPadding = AppSpacing.secondaryTabChipVerticalPadding(
      context,
    );
    final painter = TextPainter(
      text: TextSpan(
        text: 'Hg',
        style: TextStyle(
          fontSize: AppTypography.secondaryTabLabelResponsive(context),
          fontWeight: AppTypography.secondaryTabSelectedWeight,
        ),
      ),
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
      maxLines: 1,
    )..layout();
    final measuredBarHeight =
        painter.height + (verticalPadding * 2) + (chipVerticalPadding * 2);
    final barHeight = measuredBarHeight > AppSpacing.subTabNavigationHeight
        ? measuredBarHeight
        : AppSpacing.subTabNavigationHeight;
    return barHeight + AppSpacing.xs + AppSpacing.containerXs;
  }

  @override
  Widget build(BuildContext context) {
    final activeIndex = subCategories.indexWhere(
      (subCategory) => subCategory == activeSubCategoryId,
    );
    final horizontal = AppSpacing.feedContentHorizontal(context);

    return Container(
      key: ValueKey<String>('circles-sub-category-$categoryId'),
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      padding: EdgeInsets.fromLTRB(
        horizontal,
        AppSpacing.xs,
        horizontal,
        AppSpacing.containerXs,
      ),
      child: SecondaryCapsuleTabBar(
        isDark: isDark,
        tabs: subCategories,
        activeIndex: activeIndex < 0 ? 0 : activeIndex,
        onTap: (index) {
          if (index < 0 || index >= subCategories.length) {
            return;
          }
          onSubCategoryTap(subCategories[index]);
        },
        horizontalPadding: 0,
        variant: SecondaryCapsuleTabBarVariant.inlineMuted,
      ),
    );
  }
}

class _HomeCircleRailCard extends StatelessWidget {
  const _HomeCircleRailCard({
    required this.circle,
    required this.width,
    required this.isDark,
    required this.onTap,
  });

  final CircleDto circle;
  final double width;
  final bool isDark;
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
    final borderColor =
        SettingsSemanticConstants.conversationSheetCardBorderColor(isDark);
    final cardSurface = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final titleStyle = _homeCircleRailTitleTextStyle().copyWith(
      color: fgPrimary,
    );
    final metaStyle = _homeCircleRailMetaTextStyle().copyWith(
      color: fgSecondary,
    );
    return SizedBox(
      width: width,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: cardSurface,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: borderColor),
            boxShadow: [
              BoxShadow(
                color: AppColors.black.withValues(alpha: isDark ? 0.16 : 0.05),
                blurRadius: AppSpacing.md,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          padding: EdgeInsets.all(AppSpacing.intraGroupXs),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.max,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(
                  AppSpacing.contentPreviewCornerRadius,
                ),
                child: AspectRatio(
                  aspectRatio: _homeCircleCoverAspectRatio,
                  child: AppMediaImage(
                    imageSource: circle.coverUrl ?? '',
                    fit: BoxFit.cover,
                  ),
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Expanded(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        circle.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: titleStyle,
                      ),
                      SizedBox(height: AppSpacing.intraGroupXs / 2),
                      Text(
                        '${circle.memberCount} ${UITextConstants.circleMembers}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: metaStyle,
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _HomeCircleViewAllCard extends StatelessWidget {
  const _HomeCircleViewAllCard({
    required this.width,
    required this.isDark,
    required this.onTap,
  });

  final double width;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cardSurface = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final borderColor =
        SettingsSemanticConstants.conversationSheetCardBorderColor(isDark);
    return SizedBox(
      width: width,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: cardSurface,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: borderColor),
            boxShadow: [
              BoxShadow(
                color: AppColors.black.withValues(alpha: isDark ? 0.16 : 0.05),
                blurRadius: AppSpacing.md,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          padding: EdgeInsets.all(AppSpacing.intraGroupXs),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.primaryColor.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.contentPreviewCornerRadius,
                    ),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        CupertinoIcons.square_grid_2x2,
                        size: AppSpacing.iconMedium,
                        color: AppColors.primaryColor,
                      ),
                      SizedBox(height: AppSpacing.intraGroupXs),
                      Text(
                        UITextConstants.homeCirclesViewAll,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          fontWeight: AppTypography.semiBold,
                          color: fgPrimary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _HomeCircleStoryItem {
  _HomeCircleStoryItem({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.imageUrl,
    required this.circleId,
    required this.categoryId,
    required this.typeLabel,
    required this.isMine,
    required this.feedEntry,
  });

  final String id;
  final String title;
  final String subtitle;
  final String imageUrl;
  final String circleId;
  final String categoryId;
  final String typeLabel;
  final bool isMine;
  final CircleHubFeedPostEntry feedEntry;
}

class _CirclesHubTopBar extends StatelessWidget {
  const _CirclesHubTopBar({
    required this.isDark,
    required this.onSearchTap,
    required this.onAssistantTap,
  });

  final bool isDark;
  final VoidCallback onSearchTap;
  final VoidCallback onAssistantTap;

  @override
  Widget build(BuildContext context) {
    final chromeBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
    );
    final fieldBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final horizontal = AppSpacing.feedContentHorizontal(context);
    final topInset = AppSpacing.appChromeTopSafeInset(
      MediaQuery.viewPaddingOf(context).top,
      context,
    );

    return Container(
      color: chromeBackground,
      padding: EdgeInsets.only(top: topInset),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: AppSpacing.appChromeTopBarHeight(context),
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: horizontal),
              child: Row(
                children: [
                  Expanded(
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: Size.zero,
                      onPressed: onSearchTap,
                      child: IgnorePointer(
                        child: AppSearchField(
                          placeholder: UITextConstants.circlesSearchHint,
                          backgroundColor: fieldBackground,
                          elevated: false,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                  GlobalAssistantEntryButton(
                    semanticLabel: AssistantText.assistantEntryXiaoqu,
                    onTap: onAssistantTap,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
