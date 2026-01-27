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
    final currentIsDark = (isDark ?? ref.watch(effectiveIsDarkProvider))!;

    return Container(
      height: AppSpacing.subTabNavigationHeight.h,
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(currentIsDark, ColorType.backgroundPrimary),
        // 移除底部边框，去掉与图片post之间的分割线
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
                  horizontal: AppSpacing.sm.w, // 保持水平间距
                  vertical: 1.h, // 进一步调小垂直间距，减少高度
                ),
                // 移除背景和边框装饰，只使用文字样式区分
                child: Center(
                  child: Text(
                    category['label']!,
                    style: TextStyle(
                      fontSize: 14.sp, // 调小字体，比一级tab小一号
                      fontWeight: isActive ? FontWeight.w600 : FontWeight.normal, // 选中tab加粗
                      color: isActive 
                          ? AppColorsFunctional.getColor(currentIsDark, ColorType.primary) // 选中tab使用主色调
                          : AppColorsFunctional.getColor(currentIsDark, ColorType.foregroundSecondary), // 未选中tab使用次要文字颜色（较浅）
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
