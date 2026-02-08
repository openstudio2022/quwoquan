import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

/// Tab 项定义
class TabItem {
  final String id;
  final String label;

  const TabItem({required this.id, required this.label});
}

class TabNavigationWidget extends ConsumerWidget {
  final String activeTab;
  final Function(String) onTabChange;
  final bool? isDark;
  /// 可选：自定义 Tab 列表。不传则使用默认（发现页：推荐/图片/视频/文章）
  final List<TabItem>? tabs;

  const TabNavigationWidget({
    super.key,
    required this.activeTab,
    required this.onTabChange,
    this.isDark,
    this.tabs,
  });

  static const List<TabItem> discoveryTabs = [
    TabItem(id: 'recommended', label: '推荐'),
    TabItem(id: 'images', label: '图片'),
    TabItem(id: 'video', label: '视频'),
    TabItem(id: 'articles', label: '文章'),
  ];

  static const List<TabItem> defaultTabs = [
    TabItem(id: 'following', label: '关注'),
    TabItem(id: 'recommended', label: '推荐'),
    TabItem(id: 'images', label: '图片'),
    TabItem(id: 'video', label: '视频'),
    TabItem(id: 'articles', label: '文章'),
    TabItem(id: 'moments', label: '动态'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final currentIsDark = (isDark ?? ref.watch(effectiveIsDarkProvider))!;
    final tabList = tabs ?? defaultTabs;

    return Container(
      height: AppSpacing.tabNavigationHeight,
      decoration: BoxDecoration(
        // 与主背景色完全一致，实现侵入式体验
        color: AppColorsFunctional.getColor(currentIsDark, ColorType.backgroundPrimary),
        // 移除底部边框，去掉与二级tab之间的分割线
      ),
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween, // 均匀分布，第一个和最后一个贴边
        children: tabList.map((tab) {
          final isActive = tab.id == activeTab;

          return GestureDetector(
            onTap: () => onTabChange(tab.id),
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.xs.w,
                vertical: 2.h, // 保持对称的垂直padding，避免留白过大
              ),
              decoration: const BoxDecoration(), // 移除原来的Border下划线
              child: Stack(
                alignment: Alignment.center,
                children: [
                  // 文字始终在中心位置
                  Text(
                    tab.label,
                    style: TextStyle(fontSize: AppTypography.lg).copyWith( // 使用大号字体
                      color: isActive 
                        ? AppColorsFunctional.getColor(currentIsDark, ColorType.foregroundPrimary) // 选中时使用主文字颜色（黑色/白色粗体），与二级tab保持一致
                        : AppColorsFunctional.getColor(currentIsDark, ColorType.foregroundSecondary), // 未选中时使用次要文字颜色（较浅），与二级tab保持一致
                      fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
                      fontSize: 16.sp, // 明确设置大号字体
                    ),
                  ),
                  // 下划线作为背景层，不影响文字位置，使用主题色
                  // 使用Positioned的bottom值精确控制下划线与文字的距离
                  // 确保下划线与字体保持适当距离，符合业界最佳实践（4-6px间距）
                  if (isActive)
                    Positioned(
                      bottom: 4.h, // 下划线在字体底部，保持适当间距（4px），符合业界最佳实践
                      left: 0,
                      right: 0,
                      child: Center(
                        child: Container(
                          width: 16.w, // 下划线宽度比文字短，固定宽度
                          height: 2.h, // 下划线高度：2px（与原型一致）
                          decoration: BoxDecoration(
                            color: AppColorsFunctional.getColor(currentIsDark, ColorType.primary), // 下划线使用主题色
                            borderRadius: BorderRadius.circular(1.h), // 圆角与高度匹配
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}