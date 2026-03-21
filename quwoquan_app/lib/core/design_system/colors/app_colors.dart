import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

class AppColors {
  AppColors._();

  /// 品牌主蓝，作为全局默认强调色。
  static const Color primaryColor = Color(0xFF007AFF);
  static const Color primaryColorHover = Color(0xFF0A84FF);
  static const Color primaryColorActive = Color(0xFF0062CC);

  static const Color secondaryColor = Color(0xFF5E5CE6);
  static const Color secondaryColorHover = Color(0xFF7D7AFF);
  static const Color secondaryColorActive = Color(0xFF4B49D1);

  static const Color accentColor = Color(0xFF34C759);
  static const Color error = Color(0xFFFF3B30);
  static const Color success = Color(0xFF34C759);
  static const Color warning = Color(0xFFFF9F0A);
  static const Color info = primaryColor;
  static const Color white = Colors.white;
  static const Color black = Colors.black;

  static const Color overlayMedium = Color(0x80000000);
  static const Color overlayStrong = Color(0xB3000000);
  static const Color overlayDark = Color(0xCC000000);
  static const Color overlayLight = Color(0x4D000000);

  /// 媒体查看器等深色背景上的「已关注」按钮背景，与黑底明显区分
  static const Color followingButtonOnDark = Color(0xFF4A4A4A);
  static const Color iosSystemSurfaceDark = Color(0xFF2C2C2E);
  static const Color iosAccentLight = primaryColor;
  static const Color iosAccentDark = Color(0xFF0A84FF);
  static const Color iosGroupedBackgroundLight = Color(0xFFF2F2F7);
  static const Color iosGroupedBackgroundDark = Color(0xFF000000);
  static const Color iosGroupedSurfaceLight = Color(0xFFFFFFFF);
  static const Color iosGroupedSurfaceDark = Color(0xFF1C1C1E);
  static const Color iosGroupedSurfaceElevatedLight = Color(0xFFFFFFFF);
  static const Color iosGroupedSurfaceElevatedDark = Color(0xFF2C2C2E);

  // ==================== 欢迎页语义色 ====================
  static const Color welcomeBackground = Color(0xFF2563EB); // blue-600
  static const Color welcomeGradientStart = Color(0xFF3B82F6); // blue-500
  static const Color welcomeGradientEnd = Color(0xFF312E81); // indigo-900
  static const Color welcomeForeground = Colors.white;
  static const Color welcomeForegroundMuted = Color(0xFFEFF6FF); // blue-50
  static const Color welcomeButtonBg = Color(0x1AFFFFFF);
  static const Color welcomeButtonBgHover = Color(0x33FFFFFF);
  static const Color welcomeButtonBorder = Color(0x33FFFFFF);
  static const Color welcomePetalOrange = Color(0xFFFB923C);
  static const Color welcomePetalYellow = Color(0xFFFDE047);
  static const Color welcomePetalLime = Color(0xFFA3E635);
  static const Color welcomePetalEmerald = Color(0xFF34D399);
  static const Color welcomePetalCyan = Color(0xFF22D3EE);
  static const Color welcomePetalSky = Color(0xFF38BDF8);
  static const Color welcomePetalPurple = Color(0xFFA78BFA);
  static const Color welcomePetalRose = Color(0xFFFB7185);
  static const Color welcomeTitleGradientMid = Color(0xFF67E8F9); // cyan-300
  static const Color welcomeTitleGradientEnd = Color(0xFFC084FC); // purple-400

  // ==================== 作品频道专用色 ====================
  /// 墨浆蓝 #0A0E14 — 作品频道背景（强制深色）
  static const Color worksBackground = Color(0xFF0A0E14);

  /// 克莱因蓝 #002FA7 — 品牌主调
  static const Color worksBrand = Color(0xFF002FA7);

  /// 品牌蓝深色变体 #4A8BF5 — 深色背景上的强调色
  static const Color worksAccent = Color(0xFF4A8BF5);

  /// 银灰 #B8C0CC — 文章正文色
  static const Color worksBodyText = Color(0xFFB8C0CC);

  /// 近白 #E8EDF3 — 文章标题/主文字
  static const Color worksTitle = Color(0xFFE8EDF3);

  /// 暗灰 #6B7585 — 图注/次要信息
  static const Color worksCaption = Color(0xFF6B7585);

  /// 毛玻璃抽屉底色（带蓝色倾向）
  static const Color worksDrawerBg = Color(0xFF0D1523);

  /// 作品频道 — 点赞激活色（暗玫瑰，降低饱和度避免在深色背景过度刺眼）
  static const Color worksLike = Color(0xFFD94F6A);

  /// 作品频道 — 收藏激活色（琥珀棕，业界通行星标色调）
  static const Color worksSave = Color(0xFFE0A850);

  /// 聊天页专用（1:1 图一）：对话区域背景、气泡色
  static const Color chatBackground = Color(0xFFF5F5F5);
  static const Color chatBubbleIncoming = Color(0xFFFFFFFF);
  static const Color chatBubbleOutgoing = Color(0xFF388EED);
  static const Color chatToolbarBackground = Color(0xFFE8E8E8);

  static final AppColorsTheme dark = const AppColorsTheme(isDark: true);
  static final AppColorsTheme light = const AppColorsTheme(isDark: false);

  static Color iosPageBackground(BuildContext context) {
    return CupertinoDynamicColor.resolve(
      CupertinoDynamicColor.withBrightness(
        color: iosGroupedBackgroundLight,
        darkColor: iosGroupedBackgroundDark,
      ),
      context,
    );
  }

  static Color iosGroupedSurface(BuildContext context) {
    return CupertinoDynamicColor.resolve(
      CupertinoDynamicColor.withBrightness(
        color: iosGroupedSurfaceLight,
        darkColor: iosGroupedSurfaceDark,
      ),
      context,
    );
  }

  static Color iosGroupedSurfaceElevated(BuildContext context) {
    return CupertinoDynamicColor.resolve(
      CupertinoDynamicColor.withBrightness(
        color: iosGroupedSurfaceElevatedLight,
        darkColor: iosGroupedSurfaceElevatedDark,
      ),
      context,
    );
  }

  static Color iosSystemBackground(BuildContext context) =>
      CupertinoDynamicColor.resolve(CupertinoColors.systemBackground, context);

  static Color iosSeparator(BuildContext context) =>
      CupertinoDynamicColor.resolve(CupertinoColors.separator, context);

  static Color iosOpaqueSeparator(BuildContext context) =>
      CupertinoDynamicColor.resolve(CupertinoColors.opaqueSeparator, context);

  static Color iosLabel(BuildContext context) =>
      CupertinoDynamicColor.resolve(CupertinoColors.label, context);

  static Color iosSecondaryLabel(BuildContext context) =>
      CupertinoDynamicColor.resolve(CupertinoColors.secondaryLabel, context);

  static Color iosTertiaryLabel(BuildContext context) =>
      CupertinoDynamicColor.resolve(CupertinoColors.tertiaryLabel, context);

  static Color iosQuaternaryLabel(BuildContext context) =>
      CupertinoDynamicColor.resolve(CupertinoColors.quaternaryLabel, context);

  static Color iosFill(BuildContext context) =>
      CupertinoDynamicColor.resolve(CupertinoColors.systemFill, context);

  static Color iosSecondaryFill(BuildContext context) =>
      CupertinoDynamicColor.resolve(
        CupertinoColors.secondarySystemFill,
        context,
      );

  static Color iosAccent(BuildContext context) =>
      CupertinoDynamicColor.resolve(CupertinoColors.activeBlue, context);

  static Color iosDestructive(BuildContext context) =>
      CupertinoDynamicColor.resolve(CupertinoColors.systemRed, context);

  static Color iosTintedFill(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return iosAccent(context).withValues(alpha: isDark ? 0.22 : 0.12);
  }
}

class AppColorsTheme {
  const AppColorsTheme({required this.isDark});

  final bool isDark;

  Color get pageBackground => isDark
      ? AppColors.iosGroupedBackgroundDark
      : AppColors.iosGroupedBackgroundLight;

  Color get backgroundPrimary =>
      isDark ? const Color(0xFF111216) : AppColors.iosGroupedSurfaceLight;

  Color get backgroundSecondary => isDark
      ? AppColors.iosGroupedSurfaceDark
      : AppColors.iosGroupedSurfaceLight;

  Color get backgroundTertiary => isDark
      ? AppColors.iosGroupedSurfaceElevatedDark
      : const Color(0xFFF7F7FC);

  Color get foregroundPrimary =>
      isDark ? const Color(0xFFF2F2F7) : const Color(0xFF111827);

  Color get foregroundSecondary =>
      isDark ? const Color(0xFFAEAEB2) : const Color(0xFF6B7280);

  Color get foregroundTertiary =>
      isDark ? const Color(0xFF8E8E93) : const Color(0xFF8E8E93);

  Color get foregroundInverse =>
      isDark ? const Color(0xFF0F1115) : AppColors.white;
}

class AppColorsFunctional {
  static Color getColor(bool isDark, ColorType colorType) {
    switch (colorType) {
      case ColorType.pageBackground:
        return isDark
            ? AppColors.iosGroupedBackgroundDark
            : AppColors.iosGroupedBackgroundLight;
      case ColorType.surfaceElevated:
        return isDark
            ? AppColors.iosGroupedSurfaceDark
            : AppColors.iosGroupedSurfaceLight;
      case ColorType.surfaceMuted:
        return isDark
            ? AppColors.iosGroupedSurfaceElevatedDark
            : const Color(0xFFF7F7FC);
      case ColorType.glassSurface:
        return isDark ? const Color(0xD92C2C2E) : const Color(0xD9FFFFFF);
      case ColorType.separatorOpaque:
        return isDark ? const Color(0xFF3A3A3C) : const Color(0xFFD1D1D6);
      case ColorType.separatorSubtle:
        return isDark ? const Color(0xFF2C2C2E) : const Color(0xFFE5E5EA);
      case ColorType.pressedSurface:
        return isDark ? const Color(0xFF303136) : const Color(0xFFEFF1F5);
      case ColorType.badgeBackground:
        return AppColors.error;
      case ColorType.badgeForeground:
        return AppColors.white;
      case ColorType.tabUnselected:
        return isDark ? const Color(0xFF8E8E93) : const Color(0xFF8E8E93);
      case ColorType.foregroundTertiary:
        return isDark ? const Color(0xFF8E8E93) : const Color(0xFF8E8E93);
      case ColorType.foregroundSecondary:
        return isDark ? const Color(0xFFAEAEB2) : const Color(0xFF6B7280);
      case ColorType.backgroundTertiary:
        return isDark
            ? AppColors.iosGroupedSurfaceElevatedDark
            : const Color(0xFFF7F7FC);
      case ColorType.backgroundSecondary:
        return isDark
            ? AppColors.iosGroupedSurfaceDark
            : AppColors.iosGroupedSurfaceLight;
      case ColorType.backgroundPrimary:
        return isDark
            ? const Color(0xFF111216)
            : AppColors.iosGroupedSurfaceLight;
      case ColorType.backgroundQuoted:
        return isDark ? const Color(0xFF1F2024) : const Color(0xFFF7F8FB);
      case ColorType.borderPrimary:
        return getColor(isDark, ColorType.separatorOpaque);
      case ColorType.borderSecondary:
        return getColor(isDark, ColorType.separatorSubtle);
      case ColorType.foregroundPrimary:
        return isDark ? const Color(0xFFF2F2F7) : const Color(0xFF111827);
      case ColorType.foregroundInverse:
        return isDark ? const Color(0xFF0F1115) : AppColors.white;
      case ColorType.primary:
        return AppColors.primaryColor;
      case ColorType.white:
        return AppColors.white;
      case ColorType.black:
        return AppColors.black;
      case ColorType.selectionBackground:
        return (isDark ? AppColors.iosAccentDark : AppColors.primaryColor)
            .withValues(alpha: isDark ? 0.22 : 0.12);
      case ColorType.selectionBorder:
        return (isDark ? AppColors.iosAccentDark : AppColors.primaryColor)
            .withValues(alpha: isDark ? 0.34 : 0.22);
      case ColorType.selectionForeground:
        return isDark ? AppColors.iosAccentDark : AppColors.primaryColor;
    }
  }

  static Color get functionalSuccess => AppColors.success;
  static Color get functionalWarning => AppColors.warning;
  static Color get functionalError => AppColors.error;
  static Color get functionalInfo => AppColors.info;
}

enum ColorType {
  pageBackground,
  surfaceElevated,
  surfaceMuted,
  glassSurface,
  separatorOpaque,
  separatorSubtle,
  pressedSurface,
  badgeBackground,
  badgeForeground,
  tabUnselected,
  foregroundTertiary,
  foregroundSecondary,
  backgroundTertiary,
  backgroundSecondary,
  backgroundPrimary,

  /// 引用块/图片占位：比分割条(tertiary)更浅，更接近 post 白(primary)
  backgroundQuoted,
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
