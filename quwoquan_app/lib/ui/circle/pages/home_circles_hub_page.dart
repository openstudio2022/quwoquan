import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_category_tab.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_recommend_tab.dart';

class HomeCirclesHubPage extends ConsumerStatefulWidget {
  const HomeCirclesHubPage({super.key});

  @override
  ConsumerState<HomeCirclesHubPage> createState() => _HomeCirclesHubPageState();
}

class _HomeCirclesHubPageState extends ConsumerState<HomeCirclesHubPage>
    with TickerProviderStateMixin {
  late TabController _tabController;
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

    _tabController = TabController(length: _categories.length, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // L1 Category Tabs
        Container(
          color: AppColors.light.backgroundPrimary,
          width: double.infinity,
          alignment: Alignment.centerLeft,
          child: TabBar(
            controller: _tabController,
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
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

        // Content
        Expanded(
          child: TabBarView(
            controller: _tabController,
            children: _categories.map((e) {
              if (e.key == 'all') {
                return const HomeCirclesRecommendTab();
              }
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
      ],
    );
  }
}
