import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
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
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;

  static const _subTabLabels = {
    LifestyleSubTab.footprint: '足迹',
    LifestyleSubTab.bookMovieMusic: '书影音',
    LifestyleSubTab.taste: '味蕾',
    LifestyleSubTab.loveObject: '爱物',
  };

  static const _subTabCategoryKeys = {
    LifestyleSubTab.footprint: 'footprint',
    LifestyleSubTab.bookMovieMusic: 'soul',
    LifestyleSubTab.taste: 'taste',
    LifestyleSubTab.loveObject: 'private',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notifier = ref.watch(profileNotifierProvider(userId));
    final state = notifier.state;
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final primary = AppColors.primaryColor;
    final tabBarHeight = _profileLifestyleTabBarHeight(context);

    final filteredItems = state.lifeItems.where((item) {
      final key = _subTabCategoryKeys[state.lifestyleSubTab];
      return key == null || item.categoryKey == key;
    }).toList();

    return Column(
      children: [
        SizedBox(
          height: tabBarHeight,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
            children: LifestyleSubTab.values.map((tab) {
              final isActive = tab == state.lifestyleSubTab;
              return GestureDetector(
                onTap: () => notifier.setLifestyleSubTab(tab),
                child: Container(
                  alignment: Alignment.center,
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                  ),
                  child: Text(
                    _subTabLabels[tab]!,
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
        ),
        Expanded(
          child: filteredItems.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.explore_outlined,
                        size: AppSpacing.xl * 2,
                        color: fgSecondary,
                      ),
                      SizedBox(height: AppSpacing.md),
                      Text(
                        mode == ProfileMode.mine ? '还没有生活记录' : 'Ta 还没有生活记录',
                        style: TextStyle(
                          fontSize: AppTypography.md,
                          color: fgSecondary,
                        ),
                      ),
                    ],
                  ),
                )
              : GridView.builder(
                  padding: EdgeInsets.all(AppSpacing.containerSm),
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 3,
                    mainAxisSpacing: AppSpacing.sm,
                    crossAxisSpacing: AppSpacing.sm,
                  ),
                  itemCount: filteredItems.length,
                  itemBuilder: (context, index) {
                    final item = filteredItems[index];
                    return ClipRRect(
                      borderRadius: BorderRadius.circular(
                        AppSpacing.borderRadius,
                      ),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          Image.network(
                            item.coverUrl,
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
                                    Colors.black.withValues(alpha: 0.6),
                                    Colors.transparent,
                                  ],
                                ),
                              ),
                              child: Text(
                                item.name,
                                style: TextStyle(
                                  fontSize: AppTypography.xs,
                                  fontWeight: AppTypography.semiBold,
                                  color: Colors.white,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }
}
