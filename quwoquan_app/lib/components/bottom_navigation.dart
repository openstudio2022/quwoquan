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
      {'icon': Icons.explore_outlined, 'iconSelected': Icons.explore, 'label': AppConceptConstants.discovery},
      {'icon': Icons.group_outlined, 'iconSelected': Icons.group, 'label': AppConceptConstants.circles},
      {'icon': Icons.add_circle_outline, 'iconSelected': Icons.add_circle, 'label': AppConceptConstants.create},
      {'icon': Icons.chat_bubble_outline, 'iconSelected': Icons.chat_bubble, 'label': AppConceptConstants.chat},
      {'icon': Icons.person_outline, 'iconSelected': Icons.person, 'label': AppConceptConstants.profile},
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
              child: _buildIcon(
                icon: item['icon'] as IconData,
                iconSelected: item['iconSelected'] as IconData,
                isSelected: isSelected,
                isDark: isDark,
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  /// 构建图标（支持深色/浅色模式，未选中时使用更细的线条）
  Widget _buildIcon({
    required IconData icon,
    required IconData iconSelected,
    required bool isSelected,
    required bool isDark,
  }) {
    final color = isSelected 
      ? AppColors.primaryColor
      : (isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary);
    
    return Icon(
      isSelected ? iconSelected : icon,
      size: AppSpacing.iconMedium.sp, // 与一级tab文字大小对应，保持简洁
      color: color,
      // 使用IconTheme来确保主题支持，虽然不能直接改变线条粗细，
      // 但可以通过主题系统确保深色/浅色模式正确显示
    );
  }


}