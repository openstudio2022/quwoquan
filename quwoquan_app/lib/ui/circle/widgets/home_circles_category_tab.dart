import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/circle/widgets/rectangular_circle_card.dart';

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
  String _selectedSubCategory = '全部';

  @override
  Widget build(BuildContext context) {
    // Mock data fetching based on category
    // In real implementation, use ref.watch(provider(widget.categoryId))
    // For now, we reuse mock data logic inside build or assume provider availability
    
    return CustomScrollView(
      slivers: [
        // 1. Top Circles in Category (Horizontal List)
        SliverPadding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.interGroupSm),
          sliver: SliverToBoxAdapter(
            child: SizedBox(
              height: 140, // Height for RectangularCircleCard
              child: ListView.separated(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
                scrollDirection: Axis.horizontal,
                itemCount: 5, // Mock count
                separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.intraGroupMd),
                itemBuilder: (context, index) {
                  // Mock Circle
                  return RectangularCircleCard(
                    width: 240,
                    aspectRatio: 16 / 9,
                    circle: CircleDto(
                      id: 'mock_${widget.categoryId}_$index',
                      name: '${widget.label}圈子 $index',
                      description: '这是一个关于${widget.label}的精彩圈子，欢迎加入讨论。',
                      coverUrl: 'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600', // Random
                      ownerId: 'owner',
                      memberCount: 1234,
                      category: widget.categoryId,
                      createdAt: DateTime.now(),
                      updatedAt: DateTime.now(),
                    ),
                    onTap: () {
                      // Navigate to Circle Detail
                    },
                  );
                },
              ),
            ),
          ),
        ),

        // 2. L2 Tags (Sticky Header)
        SliverPersistentHeader(
          pinned: true,
          delegate: _CategoryFilterDelegate(
            subCategories: ['全部', ...widget.subCategories],
            selected: _selectedSubCategory,
            onSelected: (val) {
              setState(() {
                _selectedSubCategory = val;
              });
            },
          ),
        ),

        // 3. Waterfall Feed (Mock)
        SliverPadding(
          padding: const EdgeInsets.all(AppSpacing.containerMd),
          sliver: SliverGrid(
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              mainAxisSpacing: AppSpacing.intraGroupMd,
              crossAxisSpacing: AppSpacing.intraGroupMd,
              childAspectRatio: 0.75, // Waterfall card ratio
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
                              '${widget.label} 动态 #$index',
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
                                  '99',
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

class _CategoryFilterDelegate extends SliverPersistentHeaderDelegate {
  final List<String> subCategories;
  final String selected;
  final ValueChanged<String> onSelected;

  const _CategoryFilterDelegate({
    required this.subCategories,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    return Container(
      color: AppColors.light.backgroundPrimary,
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: ListView.separated(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        scrollDirection: Axis.horizontal,
        itemCount: subCategories.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, index) {
          final tag = subCategories[index];
          final isSelected = tag == selected;
          return ActionChip(
            label: Text(tag),
            backgroundColor: isSelected
                ? AppColors.primaryColor.withOpacity(0.1)
                : AppColors.light.backgroundSecondary,
            labelStyle: TextStyle(
              color: isSelected
                  ? AppColors.primaryColor
                  : AppColors.light.foregroundSecondary,
              fontSize: 12,
              fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
            ),
            padding: const EdgeInsets.symmetric(horizontal: 4),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: BorderSide(
                color: isSelected
                    ? AppColors.primaryColor
                    : Colors.transparent,
                width: 0.5,
              ),
            ),
            onPressed: () => onSelected(tag),
          );
        },
      ),
    );
  }

  @override
  double get maxExtent => 48;

  @override
  double get minExtent => 48;

  @override
  bool shouldRebuild(covariant _CategoryFilterDelegate oldDelegate) {
    return oldDelegate.selected != selected ||
        oldDelegate.subCategories != subCategories;
  }
}
