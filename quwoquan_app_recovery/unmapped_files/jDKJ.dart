import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/tokens/design_tokens.dart';

/// 设计一致性校准说明
/// 
/// 此文件中的颜色值直接来自 design_tokens.dart 中的定义，
/// 已转换为 Flutter Color 常量以便在 Android Studio 中显示颜色预览。
/// 
/// 颜色来源映射：
/// - LightColors: 来自 DesignTokens.light
/// - DarkColors: 来自 DesignTokens.dark  
/// - 功能色: 来自 DesignTokens.light.functional
/// - 按钮色: 来自 DesignTokens.button
/// 
/// 如需修改颜色，请同时更新 design_tokens.dart 和此文件中的对应值。

/// 应用颜色系统
class AppColors {
  // 主色调
  static const Color primaryColor = Color(0xFF1877F2);
  static const Color secondaryColor = Color(0xFF42A5F5);
  static const Color accentColor = Color(0xFF26A69A);

  // 功能色
  static const Color success = Color(0xFF4CAF50);
  static const Color warning = Color(0xFFFF9800);
  static const Color error = Color(0xFFF44336);
  static const Color info = Color(0xFF2196F3);

  // 特殊功能色
  static const Color linkColor = Color(0xFF1976D2);

  // 覆盖层颜色语义标签
  static const Color overlayLight = Color(0x1A000000); // 0.1透明度
  static const Color overlayMedium = Color(0x4D000000); // 0.3透明度
  static const Color overlayDark = Color(0x80000000); // 0.5透明度
  static const Color overlayStrong = Color(0xB3000000); // 0.7透明度

  // 基础颜色语义标签
  static const Color white = Color(0xFFFFFFFF);
  static const Color black = Color(0xFF000000);
  static const Color grey600 = Color(0xFF757575);

  // 浅色主题
  static const LightColors light = LightColors();

  // 深色主题
  static const DarkColors dark = DarkColors();
}

class LightColors {
  const LightColors();

  // 背景色 - 来自design_tokens.light.background
  Color get backgroundPrimary => const Color(0xFFFFFFFF); // #FFFFFF - 主背景
  Color get backgroundSecondary => const Color(0xFFFAFAFA); // #FAFAFA - 次要背景
  Color get backgroundTertiary => const Color(0xFFF5F5F5); // #F5F5F5 - 三级背景

  // 前景色 - 来自design_tokens.light.foreground
  Color get foregroundPrimary => const Color(0xFF262626); // #262626 - 主文字颜色
  Color get foregroundSecondary => const Color(0xFF737373); // #737373 - 次要文字颜色
  Color get foregroundTertiary => const Color(0xFFC7C7C7); // #C7C7C7 - 辅助文字颜色
  Color get foregroundInverse => const Color(0xFFFFFFFF); // #FFFFFF - 反色文字

  // 边框色 - 来自design_tokens.light.border
  Color get borderPrimary => const Color(0xFFDBDBDB); // #DBDBDB - 主边框
  Color get borderSecondary => const Color(0xFFEFEFEF); // #EFEFEF - 次要边框
  Color get borderTertiary => const Color(0xFFF5F5F5); // #F5F5F5 - 三级边框
}

class DarkColors {
  const DarkColors();

  // 背景色 - 来自design_tokens.dark.background
  Color get backgroundPrimary => const Color(0xFF000000); // #000000 - 主背景
  Color get backgroundSecondary => const Color(0xFF121212); // #121212 - 次要背景
  Color get backgroundTertiary => const Color(0xFF262626); // #262626 - 三级背景

  // 前景色 - 来自design_tokens.dark.foreground
  Color get foregroundPrimary => const Color(0xFFFFFFFF); // #FFFFFF - 主文字颜色
  Color get foregroundSecondary => const Color(0xFFA8A8A8); // #A8A8A8 - 次要文字颜色
  Color get foregroundTertiary => const Color(0xFF737373); // #737373 - 辅助文字颜色
  Color get foregroundInverse => const Color(0xFF000000); // #000000 - 反色文字

  // 边框色 - 来自design_tokens.dark.border
  Color get borderPrimary => const Color(0xFF363636); // #363636 - 主边框
  Color get borderSecondary => const Color(0xFF262626); // #262626 - 次要边框
  Color get borderTertiary => const Color(0xFF1C1C1C); // #1C1C1C - 三级边框
}

// 功能色扩展
extension AppColorsFunctional on AppColors {
  // 功能色 - 来自design_tokens.light.functional
  static const Color functionalSuccess = Color(0xFF00BA7C); // #00BA7C - 成功色
  static const Color functionalWarning = Color(0xFFFF9500); // #FF9500 - 警告色
  static const Color functionalError = Color(0xFFED4956); // #ED4956 - 错误色
  static const Color functionalInfo = Color(0xFF1877F2); // #1877F2 - 信息色
  
  /// 语义化颜色获取方法
  /// 根据主题模式和颜色类型返回对应的颜色值
  /// 避免重复的 isDark ? ... : ... 判断
  static Color getColor(bool isDark, ColorType colorType) {
    switch (colorType) {
      // 背景色
      case ColorType.backgroundPrimary:
        return isDark ? AppColors.dark.backgroundPrimary : AppColors.light.backgroundPrimary;
      case ColorType.backgroundSecondary:
        return isDark ? AppColors.dark.backgroundSecondary : AppColors.light.backgroundSecondary;
      case ColorType.backgroundTertiary:
        return isDark ? AppColors.dark.backgroundTertiary : AppColors.light.backgroundTertiary;
        
      // 前景色
      case ColorType.foregroundPrimary:
        return isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary;
      case ColorType.foregroundSecondary:
        return isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary;
      case ColorType.foregroundTertiary:
        return isDark ? AppColors.dark.foregroundTertiary : AppColors.light.foregroundTertiary;
      case ColorType.foregroundInverse:
        return isDark ? AppColors.dark.foregroundInverse : AppColors.light.foregroundInverse;
        
      // 边框色
      case ColorType.borderPrimary:
        return isDark ? AppColors.dark.borderPrimary : AppColors.light.borderPrimary;
      case ColorType.borderSecondary:
        return isDark ? AppColors.dark.borderSecondary : AppColors.light.borderSecondary;
      case ColorType.borderTertiary:
        return isDark ? AppColors.dark.borderTertiary : AppColors.light.borderTertiary;
        
      // 功能色（主题无关）
      case ColorType.primary:
        return AppColors.primaryColor;
      case ColorType.secondary:
        return AppColors.secondaryColor;
      case ColorType.accent:
        return AppColors.accentColor;
      case ColorType.success:
        return AppColors.success;
      case ColorType.warning:
        return AppColors.warning;
      case ColorType.error:
        return AppColors.error;
      case ColorType.info:
        return AppColors.info;
      case ColorType.link:
        return AppColors.linkColor;
        
      // 基础色（主题无关）
      case ColorType.white:
        return AppColors.white;
      case ColorType.black:
        return AppColors.black;
      case ColorType.grey600:
        return AppColors.grey600;
        
      // 覆盖层色（主题无关）
      case ColorType.overlayLight:
        return AppColors.overlayLight;
      case ColorType.overlayMedium:
        return AppColors.overlayMedium;
      case ColorType.overlayDark:
        return AppColors.overlayDark;
      case ColorType.overlayStrong:
        return AppColors.overlayStrong;
        
      // 按钮颜色（新增支持）- 来自design_tokens.button
      case ColorType.buttonPrimaryBackground:
        return const Color(0xFF1877F2); // #1877F2 - primary.background
      case ColorType.buttonPrimaryForeground:
        return const Color(0xFFFFFFFF); // #FFFFFF - primary.foreground
      case ColorType.buttonSecondaryBackground:
        return Colors.transparent; // transparent - secondary.background
      case ColorType.buttonSecondaryForeground:
        return const Color(0xFF262626); // #262626 - secondary.foreground
      case ColorType.buttonTertiaryBackground:
        return Colors.transparent; // transparent - tertiary.background
      case ColorType.buttonTertiaryForeground:
        return const Color(0xFF1877F2); // #1877F2 - tertiary.foreground
      case ColorType.buttonDestructiveBackground:
        return const Color(0xFFED4956); // #ED4956 - destructive.background
      case ColorType.buttonDestructiveForeground:
        return const Color(0xFFFFFFFF); // #FFFFFF - destructive.foreground
    }
  }
}

/// 颜色类型枚举
/// 定义所有可用的颜色类型，用于语义化颜色获取
enum ColorType {
  // 背景色
  backgroundPrimary,
  backgroundSecondary,
  backgroundTertiary,
  
  // 前景色
  foregroundPrimary,
  foregroundSecondary,
  foregroundTertiary,
  foregroundInverse,
  
  // 边框色
  borderPrimary,
  borderSecondary,
  borderTertiary,
  
  // 功能色
  primary,
  secondary,
  accent,
  success,
  warning,
  error,
  info,
  link,
  
  // 基础色
  white,
  black,
  grey600,
  
  // 覆盖层色
  overlayLight,
  overlayMedium,
  overlayDark,
  overlayStrong,
  
  // 按钮颜色（新增支持）
  buttonPrimaryBackground,
  buttonPrimaryForeground,
  buttonSecondaryBackground,
  buttonSecondaryForeground,
  buttonTertiaryBackground,
  buttonTertiaryForeground,
  buttonDestructiveBackground,
  buttonDestructiveForeground,
}
