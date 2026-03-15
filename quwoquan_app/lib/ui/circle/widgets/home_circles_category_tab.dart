import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'dart:math';

class HomeCirclesCategoryTab extends ConsumerStatefulWidget {
  final String categoryId;
  final String label;
  final List<String> subCategories;

  const HomeCirclesCategoryTab({
    super.key,
    required this.categoryId,
    required this.label,
    required this.subCategories,
  });

  @override
  ConsumerState<HomeCirclesCategoryTab> createState() =>
      _HomeCirclesCategoryTabState();
}

class _HomeCirclesCategoryTabState
    extends ConsumerState<HomeCirclesCategoryTab> {
  final Random _random = Random();

  @override
  Widget build(BuildContext context) {
    final posts = CircleMockData.circleFeedItems;
    
    return CustomScrollView(
      slivers: [
        SliverPadding(
          padding: const EdgeInsets.all(AppSpacing.containerMd),
          sliver: SliverMasonryGrid.count(
            crossAxisCount: 2,
            mainAxisSpacing: AppSpacing.intraGroupMd,
            crossAxisSpacing: AppSpacing.intraGroupMd,
            childCount: posts.length * 3, // Multiply to show more
            itemBuilder: (context, index) {
              final post = posts[index % posts.length];
              // Aspect ratio constraint: between 0.75 (4:3) and 1.33 (3:4 approx), 
              // but user said "don't exceed 16:9 high/wide ratio" -> 1.77.
              // Let's use a random height factor between 1.0 (square) and 1.6 (tall).
              // 16:9 is 1.777.
              final heightFactor = 1.0 + _random.nextDouble() * 0.6;
              
              return Container(
                decoration: BoxDecoration(
                  color: AppColors.light.backgroundSecondary,
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ClipRRect(
                      borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(AppSpacing.borderRadius),
                      ),
                      child: AspectRatio(
                        aspectRatio: 1 / heightFactor,
                        child: AppCachedNetworkImage(
                          imageUrl: post['coverUrl']?.toString() ?? post['thumbnailUrl']?.toString() ?? '',
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.all(8.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${widget.label} 动态 #$index\n这是一段多行文本测试，瀑布流高度自适应。',
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
                                '${post['likeCount'] ?? 99}',
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
          ),
        ),
      ],
    );
  }
}
