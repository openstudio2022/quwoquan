import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

class BottomNavigationWidget extends ConsumerWidget {
  final int currentIndex;
  final Function(int) onTap;

  const BottomNavigationWidget({
    super.key,
    required this.currentIndex,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    
    final items = [
      {'icon': Icons.home, 'label': '首页'},
      {'icon': Icons.search, 'label': '搜索'},
      {'icon': Icons.add_circle, 'label': '创建'},
      {'icon': Icons.chat_bubble_outline, 'label': '聊天'}, // 使用聊天气泡图标
      {'icon': Icons.person, 'label': '我的'},
    ];

    return Container(
      height: AppSpacing.bottomNavHeight,
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary), // 使用主背景色（深黑），与原型一致
        // 移除上边框，与原型保持一致
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: items.asMap().entries.map((entry) {
          final index = entry.key;
          final item = entry.value;
          final isSelected = index == currentIndex;
          
          return GestureDetector(
            onTap: () => onTap(index),
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: context.safeGetContainerSpacing(SpacingSize.md),
                vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
              ),
              child: item['icon'] == Icons.chat_bubble_outline 
                ? _buildChatIcon(isSelected, isDark) // 自定义聊天图标
                : Icon(
                    item['icon'] as IconData,
                    size: AppSpacing.iconMedium.sp, // 与一级tab文字大小对应，保持简洁
                    color: isSelected 
                      ? AppColors.primaryColor
                      : (isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary),
                  ),
            ),
          );
        }).toList(),
      ),
    );
  }

  /// 构建自定义聊天图标（两个聊天气泡）
  Widget _buildChatIcon(bool isSelected, bool isDark) {
    final color = isSelected 
      ? AppColors.primaryColor
      : (isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary);
    
    return SizedBox(
      width: 24.sp,
      height: 24.sp,
      child: Stack(
        children: [
          // 第一个聊天气泡（背景）
          Positioned(
            left: 0,
            top: 2.h,
            child: Icon(
              Icons.chat_bubble_outline,
              size: 16.sp,
              color: color.withOpacity(0.6),
            ),
          ),
          // 第二个聊天气泡（前景）
          Positioned(
            right: 0,
            top: 0,
            child: Icon(
              Icons.chat_bubble_outline,
              size: 18.sp,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}