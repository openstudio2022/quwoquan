import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/tokens/design_tokens.dart';

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

  // 背景色 - 侵入式体验，所有组件使用统一背景色
  Color get backgroundPrimary => const Color(0xFFE0E0E0); // 主背景色
  Color get backgroundSecondary => const Color(0xFFB3B3B3); // 次背景色
  Color get backgroundTertiary => const Color(0xFF757575); // 三级背景色

  // 前景色
  Color get foregroundPrimary => const Color(0xFF212121);
  Color get foregroundSecondary => const Color(0xFF757575);
  Color get foregroundTertiary => const Color(0xFFBDBDBD);
  Color get foregroundInverse => const Color(0xFFFFFFFF);

  // 边框色. TODO：是否要比主背景色要稍微浅一点，目前跟主背景一致
  Color get borderPrimary => const Color(0xFFE0E0E0);
  Color get borderSecondary => const Color(0xFFB3B3B3);
  Color get borderTertiary => const Color(0xFF757575);
}

class DarkColors {
  const DarkColors();

  // 背景色 - 侵入式体验，所有组件使用统一背景色
  Color get backgroundPrimary => const Color(0xFF000000); // 主背景色，纯黑色
  Color get backgroundSecondary => const Color(0xFF1A1A1A); // 次背景色
  Color get backgroundTertiary => const Color(0xFF1A1A1A); // 三级背景色

  // 前景色 - 降低对比度，保护眼睛
  Color get foregroundPrimary => const Color(0xFFE0E0E0); // 稍微浅一点的白色
  Color get foregroundSecondary => const Color(0xFFB3B3B3);
  Color get foregroundTertiary => const Color(0xFF757575);
  Color get foregroundInverse => const Color(0xFF000000);

  // 边框色
  Color get borderPrimary => const Color(0xFF363636);
  Color get borderSecondary => const Color(0xFF262626);
  Color get borderTertiary => const Color(0xFF1C1C1C);
}

// 功能色扩展
extension AppColorsFunctional on AppColors {
  static const Color functionalSuccess = Color(0xFF4CAF50);
  static const Color functionalWarning = Color(0xFFFF9800);
  static const Color functionalError = Color(0xFFF44336);
  static const Color functionalInfo = Color(0xFF2196F3);
  
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
}
