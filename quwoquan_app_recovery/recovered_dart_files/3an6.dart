import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

class TabNavigationWidget extends ConsumerWidget {
  final String activeTab;
  final Function(String) onTabChange;
  final bool? isDark; // 可选的主题参数

  const TabNavigationWidget({
    super.key,
    required this.activeTab,
    required this.onTabChange,
    this.isDark,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // 优先使用传入的主题参数，否则使用Provider
    final currentIsDark = (isDark ?? ref.watch(effectiveIsDarkProvider))!;
    
    final tabs = [
      {'id': 'following', 'label': '关注'},
      {'id': 'recommended', 'label': '推荐'},
      {'id': 'images', 'label': '图片'},
      {'id': 'video', 'label': '视频'},
      {'id': 'articles', 'label': '文章'},
      {'id': 'moments', 'label': '动态'},
    ];

    return Container(
      height: AppSpacing.tabNavigationHeight,
      decoration: BoxDecoration(
        // 与主背景色完全一致，实现侵入式体验
        color: AppColorsFunctional.getColor(currentIsDark, ColorType.backgroundPrimary),
        // 移除底部边框，去掉与二级tab之间的分割线
      ),
      padding: EdgeInsets.symmetric(horizontal: context.safeGetContainerSpacing(SpacingSize.sm)),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween, // 均匀分布，第一个和最后一个贴边
        children: tabs.map((tab) {
          final isActive = tab['id'] == activeTab;
          
          return GestureDetector(
            onTap: () => onTabChange(tab['id']!),
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.xs.w,
                vertical: 2.h, // 保持对称的垂直padding，避免留白过大
              ),
              decoration: const BoxDecoration(), // 移除原来的Border下划线
              child: Stack(
                alignment: Alignment.center,
                clipBehavior: Clip.none, // 允许下划线超出Stack范围
                children: [
                  // 文字始终在中心位置
                  Text(
                    tab['label']!,
                    style: AppTextStyles.labelLarge.copyWith( // 使用大号字体
                      color: isActive 
                        ? AppColorsFunctional.getColor(currentIsDark, ColorType.foregroundPrimary) // 选中时使用主文字颜色（黑色/白色粗体），与二级tab保持一致
                        : AppColorsFunctional.getColor(currentIsDark, ColorType.foregroundSecondary), // 未选中时使用次要文字颜色（较浅），与二级tab保持一致
                      fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
                      fontSize: 16.sp, // 明确设置大号字体
                    ),
                  ),
                  // 下划线作为背景层，不影响文字位置，使用主题色
                  // 使用Positioned的bottom值精确控制下划线与文字的距离
                  // bottom值越小（或负值），下划线越靠近Container底部，与文字的间距越大
                  if (isActive)
                    Positioned(
                      bottom: -2.h, // 负值让下划线超出Stack底部，更靠近Container底部，增大与文字的间距
                      left: 0,
                      right: 0,
                      child: Center(
                        child: Container(
                          width: 16.w, // 下划线宽度比文字短，固定宽度
                          height: 3.h, // 下划线高度：3px（更粗，符合业界标准）
                          decoration: BoxDecoration(
                            color: AppColorsFunctional.getColor(currentIsDark, ColorType.primary), // 下划线使用主题色
                            borderRadius: BorderRadius.circular(1.5.h), // 圆角与高度匹配
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