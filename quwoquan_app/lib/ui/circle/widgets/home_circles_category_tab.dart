import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

class HomeCirclesCategoryTab extends ConsumerWidget {
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
  Widget build(BuildContext context, WidgetRef ref) {
    final posts = CircleMockData.circleFeedItems;
    final isDark = ref.watch(effectiveIsDarkProvider);
    final cardBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    return SliverPadding(
      padding: const EdgeInsets.all(AppSpacing.containerMd),
      sliver: SliverMasonryGrid.count(
        crossAxisCount: 2,
        mainAxisSpacing: AppSpacing.intraGroupMd,
        crossAxisSpacing: AppSpacing.intraGroupMd,
        childCount: posts.length * 3,
        itemBuilder: (context, index) {
          final post = posts[index % posts.length];
          final random = Random(categoryId.hashCode + index);
          final heightFactor = 1.0 + random.nextDouble() * 0.6;

          return Container(
            decoration: BoxDecoration(
              color: cardBg,
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
                      imageUrl:
                          post['coverUrl']?.toString() ??
                          post['thumbnailUrl']?.toString() ??
                          '',
                      fit: BoxFit.cover,
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.all(AppSpacing.sm),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '$label 动态 #$index\n这是一段多行文本测试，瀑布流高度自适应。',
                        style: const TextStyle(
                          fontSize: AppTypography.smPlus,
                          fontWeight: AppTypography.medium,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      Row(
                        children: [
                          Container(
                            width: AppSpacing.md,
                            height: AppSpacing.md,
                            decoration: BoxDecoration(
                              color: fgSecondary.withValues(alpha: 0.2),
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: AppSpacing.xs),
                          Expanded(
                            child: Text(
                              '用户 $index',
                              style: TextStyle(
                                fontSize: AppTypography.caption,
                                color: fgSecondary,
                              ),
                              maxLines: 1,
                            ),
                          ),
                          Icon(
                            Icons.favorite_border,
                            size: AppSpacing.iconSmall,
                            color: fgSecondary,
                          ),
                          const SizedBox(width: AppSpacing.intraGroupXs / 2),
                          Text(
                            '${post['likeCount'] ?? 99}',
                            style: TextStyle(
                              fontSize: AppTypography.caption,
                              color: fgSecondary,
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
    );
  }
}
