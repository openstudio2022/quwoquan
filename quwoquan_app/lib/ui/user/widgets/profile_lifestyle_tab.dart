import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart'
    show UserLifeItem;
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';

double _profileLifestyleTabBarHeight(BuildContext context) {
  final painter = TextPainter(
    text: const TextSpan(
      text: 'Hg',
      style: TextStyle(
        fontSize: AppTypography.md,
        fontWeight: AppTypography.semiBold,
      ),
    ),
    textDirection: Directionality.of(context),
    textScaler: MediaQuery.textScalerOf(context),
    maxLines: 1,
  )..layout();
  final adaptiveHeight =
      painter.height + (AppSpacing.intraGroupSm * 2) + AppSpacing.intraGroupXs;
  return adaptiveHeight > AppSpacing.subTabNavigationHeight
      ? adaptiveHeight
      : AppSpacing.subTabNavigationHeight;
}

class ProfileLifestyleTab extends ConsumerWidget {
  const ProfileLifestyleTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
    this.inlineScroll = false,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;

  /// 置于外层可滚动壳层（ProfileShell inline tab）时为 true：网格 shrinkWrap、
  /// 禁用内部滚动，避免在无界高度约束下使用 Expanded 触发 unbounded constraints。
  final bool inlineScroll;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(profileNotifierProvider(userId));
    final notifier = ref.read(profileNotifierProvider(userId).notifier);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    // 子页清单 + 各子页对应的 LifeItemCategory 由 codegen lifestyleSubTabs 驱动，
    // 过滤直接比对 item.category == subTab.lifeCategory（与后端契约同枚举值）。
    final activeCategory = state.lifestyleSubTab;
    final filteredItems = state.lifeItems
        .where((item) => item.category == activeCategory)
        .toList();

    final tabBar = _buildSubTabBar(context, notifier, activeCategory);

    if (inlineScroll) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          tabBar,
          if (filteredItems.isEmpty)
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupXl),
              child: _buildEmptyState(fgSecondary),
            )
          else
            Padding(
              padding: EdgeInsets.all(AppSpacing.postPreviewSectionPadding),
              child: GridView.builder(
                shrinkWrap: true,
                primary: false,
                physics: const NeverScrollableScrollPhysics(),
                padding: EdgeInsets.zero,
                gridDelegate: _gridDelegate(context),
                itemCount: filteredItems.length,
                itemBuilder: (context, index) =>
                    _buildItemCard(filteredItems[index], fgSecondary),
              ),
            ),
        ],
      );
    }

    return Column(
      children: [
        tabBar,
        Expanded(
          child: filteredItems.isEmpty
              ? Center(child: _buildEmptyState(fgSecondary))
              : GridView.builder(
                  padding: EdgeInsets.all(AppSpacing.postPreviewSectionPadding),
                  gridDelegate: _gridDelegate(context),
                  itemCount: filteredItems.length,
                  itemBuilder: (context, index) =>
                      _buildItemCard(filteredItems[index], fgSecondary),
                ),
        ),
      ],
    );
  }

  Widget _buildSubTabBar(
    BuildContext context,
    ProfileNotifier notifier,
    String activeCategory,
  ) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final primary = AppColors.primaryColor;
    return SizedBox(
      key: const ValueKey<String>('profile-lifestyle-secondary-tabs'),
      height: _profileLifestyleTabBarHeight(context),
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        children: UserProfileUIConfig.lifestyleSubTabs.map((tab) {
          final category = tab.lifeCategory ?? '';
          final isActive = category == activeCategory;
          return GestureDetector(
            onTap: () => notifier.setLifestyleSubTab(category),
            child: Container(
              alignment: Alignment.center,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
              child: Text(
                UITextConstants.contentLabelForKey(tab.labelKey),
                style: TextStyle(
                  fontSize: AppTypography.md,
                  fontWeight: isActive
                      ? AppTypography.semiBold
                      : AppTypography.normal,
                  color: isActive ? primary : fgSecondary,
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  SliverGridDelegateWithFixedCrossAxisCount _gridDelegate(
    BuildContext context,
  ) {
    return SliverGridDelegateWithFixedCrossAxisCount(
      crossAxisCount: AppSpacing.responsiveGridColumns(context),
      mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
      crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
    );
  }

  Widget _buildEmptyState(Color fgSecondary) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.explore_outlined, size: AppSpacing.xl * 2, color: fgSecondary),
        SizedBox(height: AppSpacing.md),
        Text(
          mode == ProfileMode.mine ? '还没有生活记录' : 'Ta 还没有生活记录',
          style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
        ),
      ],
    );
  }

  Widget _buildItemCard(UserLifeItem item, Color fgSecondary) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      child: Stack(
        fit: StackFit.expand,
        children: [
          Image.network(
            item.imageUrl,
            fit: BoxFit.cover,
            errorBuilder: (_, _, _) => Container(
              color: fgSecondary.withValues(alpha: 0.1),
              child: Icon(Icons.image, color: fgSecondary),
            ),
          ),
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: Container(
              padding: EdgeInsets.all(AppSpacing.intraGroupSm),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [
                    AppColors.black.withValues(alpha: 0.6),
                    AppColors.transparent,
                  ],
                ),
              ),
              child: Text(
                item.title,
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.white,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
