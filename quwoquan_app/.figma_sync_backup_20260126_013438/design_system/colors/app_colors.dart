import 'package:flutter/material.dart';

class AppColors {
  // Placeholder colors
  static const Color primaryColor = Colors.blue;
  static const Color secondaryColor = Colors.purple;
  static const Color error = Colors.red;
  static const Color success = Colors.green;
  static const Color warning = Colors.orange;
  static const Color white = Colors.white;
  static const Color black = Colors.black;
  static const Color overlayMedium = Color(0x80000000); // 50% 黑色遮罩
  static const Color overlayStrong = Color(0xB3000000); // 70% 黑色遮罩（强遮罩）
  static const Color overlayDark = Color(0xCC000000); // 80% 黑色遮罩（深色遮罩）
  static const Color overlayLight = Color(0x4D000000); // 30% 黑色遮罩（浅色遮罩）
  
  static final AppColorsTheme dark = AppColorsTheme(isDark: true);
  static final AppColorsTheme light = AppColorsTheme(isDark: false);
}

class AppColorsTheme {
  final bool isDark;
  
  AppColorsTheme({required this.isDark});
  
      // 深色模式背景色与原型保持一致：
      // backgroundPrimary: #1a1a1a (深黑 - 用于状态栏、顶部tab、post列表、底部工具栏、更多按钮页)
      // backgroundSecondary: #262626 (稍微明亮一点的黑色 - 用于post卡片)
      // 浅色模式：post列表使用backgroundSecondary（浅灰），post卡片使用backgroundPrimary（乳白色/白色）
      Color get backgroundPrimary => isDark ? const Color(0xFF1A1A1A) : Colors.white;
      Color get backgroundSecondary => isDark ? const Color(0xFF262626) : Colors.grey[100]!;
      Color get backgroundTertiary => isDark ? const Color(0xFF333333) : Colors.grey[50]!;
  Color get foregroundPrimary => isDark ? Colors.white : Colors.black;
  Color get foregroundSecondary => isDark ? Colors.grey[300]! : Colors.grey[700]!;
  Color get foregroundTertiary => isDark ? Colors.grey[400]! : Colors.grey[600]!;
  Color get foregroundInverse => isDark ? Colors.black : Colors.white;
}



class AppColorsFunctional {
  static Color getColor(bool isDark, ColorType colorType) {
    // 背景色与原型保持一致
    switch (colorType) {
      case ColorType.foregroundTertiary:
        return isDark ? Colors.grey[400]! : Colors.grey[600]!;
      case ColorType.foregroundSecondary:
        return isDark ? Colors.grey[300]! : Colors.grey[700]!;
      case ColorType.backgroundTertiary:
        return isDark ? const Color(0xFF333333) : Colors.grey[100]!;
      case ColorType.backgroundSecondary:
        // 深色模式：稍微明亮一点的黑色 #262626 (用于post卡片)
        return isDark ? const Color(0xFF262626) : Colors.grey[200]!;
      case ColorType.backgroundPrimary:
        // 深色模式：深黑 #1a1a1a (用于状态栏、顶部tab、post列表、底部工具栏、更多按钮页)
        return isDark ? const Color(0xFF1A1A1A) : Colors.white;
      case ColorType.borderPrimary:
        return isDark ? Colors.grey[700]! : Colors.grey[300]!;
      case ColorType.borderSecondary:
        return isDark ? Colors.grey[600]! : Colors.grey[400]!;
      case ColorType.foregroundPrimary:
        return isDark ? Colors.white : Colors.black;
      case ColorType.foregroundInverse:
        return isDark ? Colors.black : Colors.white;
      case ColorType.primary:
        return AppColors.primaryColor;
      case ColorType.white:
        return Colors.white;
      case ColorType.black:
        return Colors.black;
      case ColorType.selectionBackground:
        return isDark ? Colors.blue[900]! : Colors.blue[100]!;
      case ColorType.selectionBorder:
        return isDark ? Colors.blue[700]! : Colors.blue[300]!;
      case ColorType.selectionForeground:
        return isDark ? Colors.blue[100]! : Colors.blue[900]!;
    }
  }
  
  // 功能性颜色
  static Color get functionalSuccess => AppColors.success;
  static Color get functionalWarning => AppColors.warning;
  static Color get functionalError => AppColors.error;
}

enum ColorType {
  foregroundTertiary,
  foregroundSecondary,
  backgroundTertiary,
  backgroundSecondary,
  backgroundPrimary,
  borderPrimary,
  borderSecondary,
  foregroundPrimary,
  foregroundInverse,
  primary,
  white,
  black,
  selectionBackground,
  selectionBorder,
  selectionForeground,
}
