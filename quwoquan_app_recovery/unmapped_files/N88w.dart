import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/tokens/design_tokens.dart';

/// 应用字体系统
/// 基于Instagram风格的字体定义，支持响应式字体大小
class AppTypography {
  // 字体族
  static const String fontFamily = 'system-ui';
  static const List<String> fontFamilyFallback = [
    '-apple-system',
    'BlinkMacSystemFont',
    'Segoe UI',
    'Roboto',
    'Helvetica Neue',
    'Arial',
    'sans-serif'
  ];
  
  static const String fontFamilyMono = 'SF Mono';
  static const List<String> fontFamilyMonoFallback = [
    'Monaco',
    'Inconsolata',
    'Fira Code',
    'monospace'
  ];

  // 字重
  static const FontWeight light = FontWeight.w300;
  static const FontWeight normal = FontWeight.w400;
  static const FontWeight medium = FontWeight.w500;
  static const FontWeight semibold = FontWeight.w600;
  static const FontWeight bold = FontWeight.w700;

  // 基础字体大小 (移动端)
  static const double xs = 11.0;      // 极小号 - 时间戳、标签
  static const double sm = 12.0;      // 小号 - 辅助信息
  static const double base = 14.0;    // 标准 - 正文内容
  static const double lg = 16.0;      // 大号 - 重要信息
  static const double xl = 18.0;      // 超大号 - 标题

  // 标题字体大小
  static const double headingSm = 16.0;   // 小标题
  static const double headingMd = 18.0;   // 中标题
  static const double headingLg = 20.0;   // 大标题
  static const double headingXl = 22.0;   // 超大标题
  static const double heading2xl = 28.0;  // 特大标题

  // 显示字体大小 (用于特殊场景)
  static const double displaySm = 32.0;
  static const double displayMd = 36.0;
  static const double displayLg = 48.0;

  // 行高
  static const double lineHeightTight = 1.2;
  static const double lineHeightNormal = 1.4;
  static const double lineHeightRelaxed = 1.6;
  static const double lineHeightLoose = 1.8;

  // 字母间距
  static const double letterSpacingTight = -0.025;
  static const double letterSpacingNormal = 0.0;
  static const double letterSpacingWide = 0.025;

  // 响应式字体大小 (平板端)
  static const double tabletXs = 12.0;
  static const double tabletSm = 13.0;
  static const double tabletBase = 15.0;
  static const double tabletLg = 17.0;
  static const double tabletXl = 19.0;
  static const double tabletHeadingSm = 17.0;
  static const double tabletHeadingMd = 19.0;
  static const double tabletHeadingLg = 21.0;
  static const double tabletHeadingXl = 24.0;
  static const double tabletHeading2xl = 32.0;

  // 响应式字体大小 (桌面端)
  static const double desktopXs = 12.0;
  static const double desktopSm = 14.0;
  static const double desktopBase = 16.0;
  static const double desktopLg = 18.0;
  static const double desktopXl = 20.0;
  static const double desktopHeadingSm = 18.0;
  static const double desktopHeadingMd = 20.0;
  static const double desktopHeadingLg = 22.0;
  static const double desktopHeadingXl = 24.0;
  static const double desktopHeading2xl = 36.0;
}

/// 文本样式预设
class AppTextStyles {
  // 正文文本样式
  static const TextStyle bodyPrimary = TextStyle(
    fontSize: AppTypography.base,
    fontWeight: AppTypography.normal,
    height: AppTypography.lineHeightNormal,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  static const TextStyle bodySecondary = TextStyle(
    fontSize: AppTypography.sm,
    fontWeight: AppTypography.normal,
    height: AppTypography.lineHeightNormal,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  static const TextStyle bodySmall = TextStyle(
    fontSize: AppTypography.xs,
    fontWeight: AppTypography.normal,
    height: AppTypography.lineHeightNormal,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  // 标题文本样式
  static const TextStyle heading1 = TextStyle(
    fontSize: AppTypography.heading2xl,
    fontWeight: AppTypography.semibold,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingTight,
  );

  static const TextStyle heading2 = TextStyle(
    fontSize: AppTypography.headingXl,
    fontWeight: AppTypography.semibold,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingTight,
  );

  static const TextStyle heading3 = TextStyle(
    fontSize: AppTypography.headingLg,
    fontWeight: AppTypography.semibold,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  static const TextStyle heading4 = TextStyle(
    fontSize: AppTypography.headingMd,
    fontWeight: AppTypography.semibold,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  static const TextStyle heading5 = TextStyle(
    fontSize: AppTypography.headingSm,
    fontWeight: AppTypography.semibold,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  // 标签文本样式
  static const TextStyle labelLarge = TextStyle(
    fontSize: AppTypography.lg,
    fontWeight: AppTypography.medium,
    height: AppTypography.lineHeightNormal,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  static const TextStyle labelMedium = TextStyle(
    fontSize: AppTypography.base,
    fontWeight: AppTypography.medium,
    height: AppTypography.lineHeightNormal,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  static const TextStyle labelSmall = TextStyle(
    fontSize: AppTypography.sm,
    fontWeight: AppTypography.medium,
    height: AppTypography.lineHeightNormal,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  // 按钮文本样式
  static const TextStyle buttonLarge = TextStyle(
    fontSize: AppTypography.lg,
    fontWeight: AppTypography.medium,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  static const TextStyle buttonMedium = TextStyle(
    fontSize: AppTypography.base,
    fontWeight: AppTypography.medium,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  static const TextStyle buttonSmall = TextStyle(
    fontSize: AppTypography.sm,
    fontWeight: AppTypography.medium,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  // 说明文本样式
  static const TextStyle captionLarge = TextStyle(
    fontSize: AppTypography.sm,
    fontWeight: AppTypography.normal,
    height: AppTypography.lineHeightNormal,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  static const TextStyle captionMedium = TextStyle(
    fontSize: AppTypography.xs,
    fontWeight: AppTypography.normal,
    height: AppTypography.lineHeightNormal,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  static const TextStyle captionSmall = TextStyle(
    fontSize: 10.0,
    fontWeight: AppTypography.normal,
    height: AppTypography.lineHeightNormal,
    letterSpacing: AppTypography.letterSpacingNormal,
  );

  // 显示文本样式
  static const TextStyle displaySmall = TextStyle(
    fontSize: AppTypography.displaySm,
    fontWeight: AppTypography.bold,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingTight,
  );

  static const TextStyle displayMedium = TextStyle(
    fontSize: AppTypography.displayMd,
    fontWeight: AppTypography.bold,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingTight,
  );

  static const TextStyle displayLarge = TextStyle(
    fontSize: AppTypography.displayLg,
    fontWeight: AppTypography.bold,
    height: AppTypography.lineHeightTight,
    letterSpacing: AppTypography.letterSpacingTight,
  );
}

/// 响应式文本样式
class ResponsiveTextStyles {
  /// 根据屏幕尺寸获取响应式文本样式
  static TextStyle getBodyPrimary(BuildContext context) {
    final screenType = SafeAppSpacing.getScreenType(MediaQuery.of(context).size.width);
    
    if (screenType == ScreenType.desktop) {
      // 桌面端
      return AppTextStyles.bodyPrimary.copyWith(fontSize: AppTypography.desktopBase);
    } else if (screenType == ScreenType.tablet) {
      // 平板端
      return AppTextStyles.bodyPrimary.copyWith(fontSize: AppTypography.tabletBase);
    } else {
      // 移动端
      return AppTextStyles.bodyPrimary;
    }
  }

  static TextStyle getBodySecondary(BuildContext context) {
    final screenType = SafeAppSpacing.getScreenType(MediaQuery.of(context).size.width);
    
    if (screenType == ScreenType.desktop) {
      return AppTextStyles.bodySecondary.copyWith(fontSize: AppTypography.desktopSm);
    } else if (screenType == ScreenType.tablet) {
      return AppTextStyles.bodySecondary.copyWith(fontSize: AppTypography.tabletSm);
    } else {
      return AppTextStyles.bodySecondary;
    }
  }

  static TextStyle getHeading1(BuildContext context) {
    final screenType = SafeAppSpacing.getScreenType(MediaQuery.of(context).size.width);
    
    if (screenType == ScreenType.desktop) {
      return AppTextStyles.heading1.copyWith(fontSize: AppTypography.desktopHeading2xl);
    } else if (screenType == ScreenType.tablet) {
      return AppTextStyles.heading1.copyWith(fontSize: AppTypography.tabletHeading2xl);
    } else {
      return AppTextStyles.heading1;
    }
  }

  static TextStyle getHeading2(BuildContext context) {
    final screenType = SafeAppSpacing.getScreenType(MediaQuery.of(context).size.width);
    
    if (screenType == ScreenType.desktop) {
      return AppTextStyles.heading2.copyWith(fontSize: AppTypography.desktopHeadingXl);
    } else if (screenType == ScreenType.tablet) {
      return AppTextStyles.heading2.copyWith(fontSize: AppTypography.tabletHeadingXl);
    } else {
      return AppTextStyles.heading2;
    }
  }

  static TextStyle getHeading3(BuildContext context) {
    final screenType = SafeAppSpacing.getScreenType(MediaQuery.of(context).size.width);
    
    if (screenType == ScreenType.desktop) {
      return AppTextStyles.heading3.copyWith(fontSize: AppTypography.desktopHeadingLg);
    } else if (screenType == ScreenType.tablet) {
      return AppTextStyles.heading3.copyWith(fontSize: AppTypography.tabletHeadingLg);
    } else {
      return AppTextStyles.heading3;
    }
  }

  static TextStyle getHeading4(BuildContext context) {
    final screenType = SafeAppSpacing.getScreenType(MediaQuery.of(context).size.width);
    
    if (screenType == ScreenType.desktop) {
      return AppTextStyles.heading4.copyWith(fontSize: AppTypography.desktopHeadingMd);
    } else if (screenType == ScreenType.tablet) {
      return AppTextStyles.heading4.copyWith(fontSize: AppTypography.tabletHeadingMd);
    } else {
      return AppTextStyles.heading4;
    }
  }

  static TextStyle getHeading5(BuildContext context) {
    final screenType = SafeAppSpacing.getScreenType(MediaQuery.of(context).size.width);
    
    if (screenType == ScreenType.desktop) {
      return AppTextStyles.heading5.copyWith(fontSize: AppTypography.desktopHeadingSm);
    } else if (screenType == ScreenType.tablet) {
      return AppTextStyles.heading5.copyWith(fontSize: AppTypography.tabletHeadingSm);
    } else {
      return AppTextStyles.heading5;
    }
  }
}

/// 字体扩展，提供便捷的访问方法
extension AppTypographyExtension on BuildContext {
  /// 获取应用字体系统
  AppTypography get typography => AppTypography();
  
  /// 获取文本样式预设
  AppTextStyles get textStyles => AppTextStyles();
  
  /// 获取响应式文本样式
  ResponsiveTextStyles get responsiveTextStyles => ResponsiveTextStyles();
  
  /// 根据屏幕尺寸获取响应式字体大小
  double getResponsiveFontSize(double mobileSize, {double? tabletSize, double? desktopSize}) {
    final screenType = SafeAppSpacing.getScreenType(MediaQuery.of(this).size.width);
    
    if (screenType == ScreenType.desktop && desktopSize != null) {
      return desktopSize;
    } else if (screenType == ScreenType.tablet && tabletSize != null) {
      return tabletSize;
    } else {
      return mobileSize;
    }
  }
  
  /// 获取设备类型
  String getDeviceType() {
    final screenType = SafeAppSpacing.getScreenType(MediaQuery.of(this).size.width);
    
    if (screenType == ScreenType.desktop) {
      return 'desktop';
    } else if (screenType == ScreenType.tablet) {
      return 'tablet';
    } else {
      return 'mobile';
    }
  }
}

