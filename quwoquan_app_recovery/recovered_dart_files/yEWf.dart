import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/tokens/design_tokens.dart';

class AppSpacing {
  static const double xs = 4.0;
  static const double sm = 8.0;
  static const double md = 16.0;
  static const double lg = 24.0;
  static const double xl = 32.0;
  static const double xxl = 48.0;
  
  static const double iconSmall = 16.0;
  static const double iconMedium = 24.0;
  static const double iconLarge = 32.0;
  
  // 组件尺寸语义标签
  static const double avatarSize = 40.0;
  static const double buttonSize = 32.0;
  static const double smallButtonSize = 24.0;
  static const double largeButtonSize = 48.0;
  
  // 圆角语义标签
  static const double borderRadius = 8.0;
  static const double smallBorderRadius = 4.0;
  static const double largeBorderRadius = 12.0;
  static const double extraLargeBorderRadius = 16.0;
  static const double circularBorderRadius = 20.0;
  
  // 布局高度语义标签
  static const double tabNavigationHeight = 48.0;
  static const double bottomNavHeight = 56.0;
  static const double modalHeaderHeight = 60.0;
  static const double storyHeight = 105.0;
  
  // 内容间距语义标签（用于post内容内部间距）
  static const double contentSpacingXs = 2.0;  // 8/4
  static const double contentSpacingSm = 4.0;  // 8/2
  static const double contentSpacingMd = 8.0;  // 16/2
  static const double contentSpacingLg = 12.0; // 24/2
  static const double contentSpacingXl = 16.0; // 32/2
  
  // Post间距语义标签（用于post之间的间距）
  static const double postSpacingXs = 6.0;   // 比sm小一点
  static const double postSpacingSm = 8.0;   // 与contentSpacingMd相同
  static const double postSpacingMd = 12.0;  // 比sm大一点
  static const double postSpacingLg = 16.0;  // 比md大一点
  static const double postSpacingXl = 20.0;  // 比lg大一点
}

extension AppSpacingExtension on BuildContext {
  double safeGetContainerSpacing(SpacingSize size) {
    switch (size) {
      case SpacingSize.xs: return AppSpacing.xs;
      case SpacingSize.sm: return AppSpacing.sm;
      case SpacingSize.md: return AppSpacing.md;
      case SpacingSize.lg: return AppSpacing.lg;
      case SpacingSize.xl: return AppSpacing.xl;
    }
  }
  
  double safeGetIntraGroupSpacing(SpacingSize size) {
    return safeGetContainerSpacing(size);
  }
  
  double safeGetInterGroupSpacing(SpacingSize size) {
    return safeGetContainerSpacing(size) * 1.5;
  }
  
  // 添加缺失的扩展方法
  double safeGetSpacing(SpacingType spacingType, SpacingSize size) {
    switch (spacingType) {
      case SpacingType.container:
        return safeGetContainerSpacing(size);
      case SpacingType.intraGroup:
        return safeGetIntraGroupSpacing(size);
      case SpacingType.interGroup:
        return safeGetInterGroupSpacing(size);
    }
  }
  
  ScreenType get safeScreenType {
    final width = MediaQuery.of(this).size.width;
    if (width >= 1024) {
      return ScreenType.desktop;
    } else if (width >= 768) {
      return ScreenType.tablet;
    } else {
      return ScreenType.mobile;
    }
  }
}

enum SpacingSize { xs, sm, md, lg, xl }
