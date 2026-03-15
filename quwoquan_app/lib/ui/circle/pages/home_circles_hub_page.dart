import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_category_tab.dart';
import 'package:quwoquan_app/ui/circle/widgets/my_circles_rail.dart';
import 'package:quwoquan_app/ui/circle/widgets/rectangular_circle_card.dart';

class HomeCirclesHubPage extends ConsumerStatefulWidget {
  const HomeCirclesHubPage({super.key});

  @override
  ConsumerState<HomeCirclesHubPage> createState() => _HomeCirclesHubPageState();
}

class _HomeCirclesHubPageState extends ConsumerState<HomeCirclesHubPage> {
  late List<MapEntry<String, Map<String, dynamic>>> _categories;

  @override
  void initState() {
    super.initState();
    // 'all' is handled as the first tab (Recommend), so we might want to put it first explicitly
    // or just use the map order if 'all' is first.
    // Let's ensure 'all' is first.
    final allConfig = CircleMockData.categoryConfig.entries
        .where((e) => e.key == 'all')
        .toList();
    final otherConfig = CircleMockData.categoryConfig.entries
        .where((e) => e.key != 'all')
        .toList();
    _categories = [...allConfig, ...otherConfig];
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: _categories.length,
      child: NestedScrollView(
        headerSliverBuilder: (context, innerBoxIsScrolled) {
          return [
            // Global Header: My Circles + Recommended Circles
            const SliverToBoxAdapter(
              child: _CirclesGlobalHeader(),
            ),

            // Sticky TabBar (Categories)
            SliverPersistentHeader(
              pinned: true,
              delegate: _StickyTabBarDelegate(
                child: Container(
                  color: AppColors.light.backgroundPrimary,
                  alignment: Alignment.centerLeft,
                  child: TabBar(
                    isScrollable: true,
                    tabAlignment: TabAlignment.start,
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                    ),
                    labelColor: AppColors.primaryColor,
                    unselectedLabelColor: AppColors.light.foregroundSecondary,
                    labelStyle: const TextStyle(
                      fontSize: 15,
                      fontWeight: AppTypography.bold,
                    ),
                    unselectedLabelStyle: const TextStyle(
                      fontSize: 15,
                      fontWeight: AppTypography.medium,
                    ),
                    indicatorColor: AppColors.primaryColor,
                    indicatorSize: TabBarIndicatorSize.label,
                    dividerColor: Colors.transparent,
                    tabs: _categories.map((e) {
                      return Tab(text: e.value['label'] as String);
                    }).toList(),
                  ),
                ),
              ),
            ),
          ];
        },
        body: TabBarView(
          children: _categories.map((e) {
            // All tabs now use the same simplified waterfall layout structure
            return HomeCirclesCategoryTab(
              categoryId: e.key,
              label: e.value['label'] as String,
              subCategories: (e.value['subCategories'] as List<dynamic>)
                  .map((e) => e.toString())
                  .toList(),
            );
          }).toList(),
        ),
      ),
    );
  }
}

class _CirclesGlobalHeader extends StatelessWidget {
  const _CirclesGlobalHeader();

  @override
  Widget build(BuildContext context) {
    // Mock Data for Header
    final myCircles = CircleMockData.circles
        .take(5)
        .map((e) => CircleDto.fromMap(e))
        .toList();
    final featuredCircles = CircleMockData.circles
        .skip(2)
        .take(5)
        .map((e) => CircleDto.fromMap(e))
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: AppSpacing.interGroupSm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                ),
                child: const Text(
                  '我的圈子',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: AppTypography.bold,
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.intraGroupSm),
              SizedBox(
                height: 160,
                child: ListView.separated(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                  ),
                  scrollDirection: Axis.horizontal,
                  itemCount: myCircles.length,
                  separatorBuilder: (_, __) =>
                      const SizedBox(width: AppSpacing.intraGroupMd),
                  itemBuilder: (context, index) {
                    return RectangularCircleCard(
                      width: 260,
                      aspectRatio: 16 / 9,
                      circle: myCircles[index],
                      onTap: () {},
                    );
                  },
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: AppSpacing.interGroupSm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      '推荐圈子',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: AppTypography.bold,
                      ),
                    ),
                    GestureDetector(
                      onTap: () {},
                      child: Text(
                        '更多 >',
                        style: TextStyle(
                          fontSize: 12,
                          color: AppColors.light.foregroundSecondary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.intraGroupSm),
              SizedBox(
                height: 160, // Height for RectangularCircleCard
                child: ListView.separated(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                  ),
                  scrollDirection: Axis.horizontal,
                  itemCount: featuredCircles.length,
                  separatorBuilder: (_, __) =>
                      const SizedBox(width: AppSpacing.intraGroupMd),
                  itemBuilder: (context, index) {
                    return RectangularCircleCard(
                      width: 260,
                      aspectRatio: 16 / 9,
                      circle: featuredCircles[index],
                      onTap: () {},
                    );
                  },
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.interGroupSm),
      ],
    );
  }
}

class _StickyTabBarDelegate extends SliverPersistentHeaderDelegate {
  final Widget child;

  const _StickyTabBarDelegate({required this.child});

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    return child;
  }

  @override
  double get maxExtent => 48;

  @override
  double get minExtent => 48;

  @override
  bool shouldRebuild(covariant _StickyTabBarDelegate oldDelegate) {
    return oldDelegate.child != child;
  }
}
