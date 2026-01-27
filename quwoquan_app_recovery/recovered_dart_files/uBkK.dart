import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import '../../../core/design_system/tokens/design_tokens.dart' as tokens;

class TabNavigationWidget extends ConsumerWidget {
  final String activeTab;
  final Function(String) onTabChange;

  const TabNavigationWidget({
    super.key,
    required this.activeTab,
    required this.onTabChange,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    
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
        // 与状态栏背景色保持一致
        color: isDark 
          ? AppColors.dark.backgroundPrimary
          : Colors.white, // 白天模式使用纯白色
        border: Border(
          bottom: BorderSide(
            // 淡化分割线颜色
            color: isDark 
              ? AppColors.dark.foregroundTertiary.withValues(alpha: 0.3)
              : AppColors.light.foregroundTertiary.withValues(alpha: 0.3),
            width: 0.5,
          ),
        ),
      ),
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
            padding: EdgeInsets.symmetric(horizontal: context.safeGetContainerSpacing(SpacingSize.lg)),
        itemCount: tabs.length,
        itemBuilder: (context, index) {
          final tab = tabs[index];
          final isActive = tab['id'] == activeTab;
          
          return GestureDetector(
            onTap: () => onTabChange(tab['id']!),
            child: Container(
              padding: EdgeInsets.symmetric(
                    horizontal: context.safeGetContainerSpacing(SpacingSize.lg),
                vertical: 2.h, // 进一步减少垂直padding
              ),
              margin: EdgeInsets.only(right: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
              decoration: const BoxDecoration(), // 移除原来的Border下划线
              child: Stack(
                alignment: Alignment.center,
                children: [
                  // 文字始终在中心位置
                  Text(
                    tab['label']!,
                    style: AppTextStyles.labelLarge.copyWith( // 使用大号字体
                      color: isActive 
                        ? AppColors.primaryColor // 选中时使用主色调
                        : (isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary),
                      fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
                      fontSize: 16.sp, // 明确设置大号字体
                    ),
                  ),
                  // 下划线作为背景层，不影响文字位置
                  if (isActive)
                    Positioned(
                      bottom: 0,
                      left: 0,
                      right: 0,
                      child: Center(
                        child: Container(
                          width: 16.w, // 下划线宽度比文字短，固定宽度
                          height: 2.h, // 下划线高度
                          decoration: BoxDecoration(
                            color: AppColors.primaryColor,
                            borderRadius: BorderRadius.circular(1.h), // 圆角
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}