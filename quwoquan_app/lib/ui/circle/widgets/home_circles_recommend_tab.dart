import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/circle/widgets/my_circles_rail.dart';
import 'package:quwoquan_app/ui/circle/widgets/rectangular_circle_card.dart';

@Deprecated('遗留首页圈子推荐实现，统一改用 HomeCirclesHubPage。')
class HomeCirclesRecommendTab extends ConsumerStatefulWidget {
  const HomeCirclesRecommendTab({super.key});

  @override
  ConsumerState<HomeCirclesRecommendTab> createState() =>
      _HomeCirclesRecommendTabState();
}

class _HomeCirclesRecommendTabState
    extends ConsumerState<HomeCirclesRecommendTab> {
  @override
  Widget build(BuildContext context) {
    // Mock Data
    final myCircles = CircleMockData.circles
        .take(5)
        .map((e) => CircleDto.fromMap(e))
        .toList();
    final featuredCircles = CircleMockData.circles
        .skip(2)
        .take(5)
        .map((e) => CircleDto.fromMap(e))
        .toList();

    return CustomScrollView(
      slivers: [
        // 1. My Circles
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.only(top: AppSpacing.interGroupSm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                  ),
                  child: Text(
                    '我的圈子',
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: AppTypography.bold,
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.intraGroupSm),
                MyCirclesRail(
                  circles: myCircles,
                  onCircleTap: (circle) {
                    // Navigate
                  },
                ),
              ],
            ),
          ),
        ),

        // 2. Featured Circles (Rectangular)
        SliverToBoxAdapter(
          child: Padding(
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
        ),

        // 3. Trending Feed Header
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.interGroupMd,
              AppSpacing.containerMd,
              AppSpacing.intraGroupSm,
            ),
            child: const Text(
              '热门动态',
              style: TextStyle(
                fontSize: 16,
                fontWeight: AppTypography.bold,
              ),
            ),
          ),
        ),

        // 4. Waterfall Feed (Mock)
        SliverPadding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
          sliver: SliverGrid(
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              mainAxisSpacing: AppSpacing.intraGroupMd,
              crossAxisSpacing: AppSpacing.intraGroupMd,
              childAspectRatio: 0.7,
            ),
            delegate: SliverChildBuilderDelegate(
              (context, index) {
                return Container(
                  decoration: BoxDecoration(
                    color: AppColors.light.backgroundSecondary,
                    borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: ClipRRect(
                          borderRadius: const BorderRadius.vertical(
                            top: Radius.circular(AppSpacing.borderRadius),
                          ),
                          child: Container(
                            color: Colors.grey[300],
                            child: const Center(
                              child: Icon(Icons.image, color: Colors.grey),
                            ),
                          ),
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.all(8.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '热门动态标题 #$index',
                              style: const TextStyle(
                                fontSize: 13,
                                fontWeight: AppTypography.medium,
                              ),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                            const SizedBox(height: 4),
                            Row(
                              children: [
                                const CircleAvatar(
                                  radius: 8,
                                  backgroundColor: Colors.grey,
                                ),
                                const SizedBox(width: 4),
                                Expanded(
                                  child: Text(
                                    '用户 $index',
                                    style: TextStyle(
                                      fontSize: 10,
                                      color: AppColors.light.foregroundSecondary,
                                    ),
                                    maxLines: 1,
                                  ),
                                ),
                                Icon(
                                  Icons.favorite_border,
                                  size: 12,
                                  color: AppColors.light.foregroundSecondary,
                                ),
                                const SizedBox(width: 2),
                                Text(
                                  '1.2k',
                                  style: TextStyle(
                                    fontSize: 10,
                                    color: AppColors.light.foregroundSecondary,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                );
              },
              childCount: 10,
            ),
          ),
        ),
      ],
    );
  }
}
