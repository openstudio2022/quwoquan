import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 图片二级导航组件
/// 支持横向滚动和持久化状态
class ImageSubTabNavigation extends ConsumerWidget {
  final String activeCategory;
  final Function(String) onCategoryChange;
  final bool? isDark; // 可选的主题参数

  const ImageSubTabNavigation({
    super.key,
    required this.activeCategory,
    required this.onCategoryChange,
    this.isDark,
  });

  // 图片分类标签
  static const List<Map<String, String>> categories = [
    {'id': 'all', 'label': '全部'},
    {'id': 'landscape', 'label': '风光'},
    {'id': 'portrait', 'label': '人像'},
    {'id': 'documentary', 'label': '纪实'},
    {'id': 'still-life', 'label': '静物'},
    {'id': 'architecture', 'label': '建筑'},
    {'id': 'animal', 'label': '动物'},
    {'id': 'wallpaper', 'label': '壁纸'},
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // 优先使用传入的主题参数，否则使用Provider
    final currentIsDark = isDark ?? ref.watch(effectiveIsDarkProvider);

    return Container(
      height: AppSpacing.subTabNavigationHeight.h,
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(currentIsDark, ColorType.backgroundPrimary),
        border: Border(
          bottom: BorderSide(
            color: AppColorsFunctional.getColor(currentIsDark, ColorType.foregroundTertiary).withValues(alpha: 0.3),
            width: 0.5,
          ),
        ),
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(
          horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
        ),
        child: Row(
          children: categories.map((category) {
            final isActive = category['id'] == activeCategory;
            
            return GestureDetector(
              onTap: () => onCategoryChange(category['id']!),
              child: Container(
                margin: EdgeInsets.only(right: AppSpacing.xs.w),
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.lg.w,
                  vertical: AppSpacing.xs.h,
                ),
                decoration: BoxDecoration(
                  color: isActive 
                      ? AppColorsFunctional.getColor(currentIsDark, ColorType.selectionBackground)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(12.r), // 比fullBorderRadius小一号
                  border: isActive 
                      ? Border.all(
                          color: AppColorsFunctional.getColor(currentIsDark, ColorType.selectionBorder),
                          width: 1.0,
                        )
                      : null,
                ),
                child: Center(
                  child: Text(
                    category['label']!,
                    style: TextStyle(
                      fontSize: 16.sp, // 与一级tab保持一致
                      fontWeight: isActive ? FontWeight.w500 : FontWeight.normal,
                      color: isActive 
                          ? AppColorsFunctional.getColor(currentIsDark, ColorType.selectionForeground)
                          : AppColorsFunctional.getColor(currentIsDark, ColorType.foregroundPrimary),
                    ),
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }
}
