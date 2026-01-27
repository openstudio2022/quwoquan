import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 图片分类二级Tab组件
/// 用于在图片Tab下显示不同的摄影分类
class ImageCategoryTabs extends ConsumerStatefulWidget {
  final String activeCategory;
  final Function(String) onCategoryChange;

  const ImageCategoryTabs({
    super.key,
    required this.activeCategory,
    required this.onCategoryChange,
  });

  @override
  ConsumerState<ImageCategoryTabs> createState() => _ImageCategoryTabsState();
}

class _ImageCategoryTabsState extends ConsumerState<ImageCategoryTabs> {
  final ScrollController _scrollController = ScrollController();

  // 图片分类定义
  static const List<Map<String, String>> categories = [
    {'id': TabConstants.all, 'label': UITextConstants.all},
    {'id': TabConstants.portrait, 'label': UITextConstants.portrait},
    {'id': TabConstants.landscape, 'label': UITextConstants.landscape},
    {'id': TabConstants.street, 'label': UITextConstants.street},
    {'id': TabConstants.food, 'label': UITextConstants.food},
    {'id': TabConstants.travel, 'label': UITextConstants.travel},
    {'id': TabConstants.fashion, 'label': UITextConstants.fashion},
    {'id': TabConstants.nature, 'label': UITextConstants.nature},
    {'id': TabConstants.architecture, 'label': UITextConstants.architecture},
    {'id': TabConstants.abstract, 'label': UITextConstants.abstract},
  ];

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    
    final backgroundColor = isDark ? AppColors.dark.backgroundPrimary : AppColors.light.backgroundPrimary;
    // 使用中性色作为选中状态，不使用主色调
    final selectedBackgroundColor = isDark ? AppColors.dark.backgroundSecondary : AppColors.light.backgroundSecondary;
    final selectedTextColor = isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary;
    final unselectedTextColor = isDark ? AppColors.dark.foregroundTertiary : AppColors.light.foregroundTertiary;

    return Container(
      height: (AppSpacing.avatarSize * 0.9).h, // 降低高度
      color: backgroundColor, // 去掉边框线，直接使用背景色
      child: SingleChildScrollView(
        controller: _scrollController,
        scrollDirection: Axis.horizontal,
        child: Row(
          children: categories.map((category) => _buildCategoryTab(
            category['id']!,
            category['label']!,
            selectedBackgroundColor,
            selectedTextColor,
            unselectedTextColor,
            isDark,
          )).toList(),
        ),
      ),
    );
  }

  Widget _buildCategoryTab(String categoryId, String label, Color selectedBackgroundColor, Color selectedTextColor, Color unselectedTextColor, bool isDark) {
    final isActive = widget.activeCategory == categoryId;
    
    return GestureDetector(
      onTap: () => widget.onCategoryChange(categoryId),
      child: Container(
        margin: EdgeInsets.symmetric(horizontal: (AppSpacing.sm * 0.75).w),
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm.w, vertical: (AppSpacing.sm * 0.75).h), // 减小padding
        decoration: BoxDecoration(
          color: isActive ? selectedBackgroundColor : Colors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.md.r), // 减小圆角
        ),
        child: Center(
          child: Text(
            label,
            style: TextStyle(
              fontSize: (AppTypography.sm - 1).sp, // 减小字体
              fontWeight: isActive ? FontWeight.w600 : FontWeight.w400,
              color: isActive ? selectedTextColor : unselectedTextColor,
            ),
          ),
        ),
      ),
    );
  }
}
