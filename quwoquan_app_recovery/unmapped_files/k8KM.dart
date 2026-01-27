import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 更多功能弹窗 - 响应式适配工具（类型安全版本）
class MoreActionResponsive {
  /// 获取响应式弹窗高度 - 基于类型安全的间距系统
  static double getModalHeight(ResponsiveState responsive) {
    // 使用类型安全的间距系统，不会抛出异常
    final containerSpacing = SafeAppSpacing.getContainerSpacing(
      size: responsive.isDesktop ? SpacingSize.xl : SpacingSize.lg,
      isDesktop: responsive.isDesktop,
      isTablet: responsive.isTablet,
    );
    
    return containerSpacing * 20; // 基于语义间距的倍数计算
  }
  
  /// 获取响应式字体大小 - 基于类型安全的字体系统
  static double getFontSize(ResponsiveState responsive) {
    // 使用类型安全的字体系统，保证返回有效值
    return SafeAppTypography.responsiveFontSize(
      mobile: FontSize.sm,      // 手机端使用小号字体
      tablet: FontSize.base,    // 平板端使用标准字体
      desktop: FontSize.lg,     // 桌面端使用大号字体
      isDesktop: responsive.isDesktop,
      isTablet: responsive.isTablet,
    );
  }
  
  /// 获取响应式图标尺寸 - 基于类型安全的图标系统
  static double getIconSize(ResponsiveState responsive) {
    // 使用类型安全的图标尺寸系统，保证返回有效值
    return SafeAppSpacing.getIconSize(
      isDesktop: responsive.isDesktop,
      isTablet: responsive.isTablet,
    );
  }
  
  /// 获取响应式弹窗内边距 - 基于类型安全的间距系统
  static EdgeInsets getModalPadding(BuildContext context) {
    // 使用类型安全的扩展方法，不会抛出异常
    return EdgeInsets.symmetric(
      horizontal: context.safeGetContainerSpacing(SpacingSize.md),
      vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
    );
  }
  
  /// 获取响应式间距 - 使用类型安全的间距系统
  static double getSpacing(
    BuildContext context, 
    SpacingType spacingType, 
    SpacingSize size
  ) {
    // 使用类型安全的扩展方法，不会抛出异常
    return context.safeGetSpacing(spacingType, size);
  }
  
  /// 便捷方法：获取组内间距
  static double getIntraGroupSpacing(
    BuildContext context, 
    SpacingSize size
  ) {
    return context.safeGetIntraGroupSpacing(size);
  }
  
  /// 便捷方法：获取组间间距
  static double getInterGroupSpacing(
    BuildContext context, 
    SpacingSize size
  ) {
    return context.safeGetInterGroupSpacing(size);
  }
  
  /// 便捷方法：获取容器间距
  static double getContainerSpacing(
    BuildContext context, 
    SpacingSize size
  ) {
    return context.safeGetContainerSpacing(size);
  }

  /// 获取弹窗拖拽指示器宽度
  static double getModalDragHandleWidth(BuildContext context) {
    return 40.0;
  }

  /// 获取弹窗拖拽指示器高度
  static double getModalDragHandleHeight(BuildContext context) {
    return 4.0;
  }

  /// 获取弹窗标题字体大小
  static double getModalTitleFontSize(BuildContext context) {
    return SafeAppTypography.fontSize(FontSize.modalTitle);
  }

  /// 获取弹窗项目宽度
  static double getModalItemWidth(BuildContext context) {
    return 80.0;
  }

  /// 获取弹窗项目尺寸
  static double getModalItemSize(BuildContext context) {
    return 60.0;
  }

  /// 获取弹窗项目图标尺寸
  static double getModalItemIconSize(BuildContext context) {
    return 24.0;
  }

  /// 获取弹窗项目字体大小
  static double getModalItemFontSize(BuildContext context) {
    return SafeAppTypography.fontSize(FontSize.sm);
  }
}
