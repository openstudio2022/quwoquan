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

  /// 作者主页等强调质感的 iOS 语义白表面。
  /// 浅色仅保留极轻微暖感，避免与纯白控件形成明显色块对比。
  static const Color iosProfileSurfaceLight = Color(0xFFFFFDFC);
  static const Color iosProfileSurfaceDark = Color(0xFF1C1C1E);

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

  /// 创作页媒体错误占位渐变
  static const Color createMediaFallbackGradientTop = Color(0xFF343434);
  static const Color createMediaFallbackGradientBottom = Color(0xFF141414);

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

  static Color iosProfileSurface(BuildContext context) {
    return CupertinoDynamicColor.resolve(
      CupertinoDynamicColor.withBrightness(
        color: iosProfileSurfaceLight,
        darkColor: iosProfileSurfaceDark,
      ),
      context,
    );
  }

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

class ArticleTemplateColors {
  ArticleTemplateColors._();

  static const Color ritualStageDark = Color(0xFF171411);
  static const Color ritualStageLight = Color(0xFFF6F0E7);
  static const Color ritualPaperDark = Color(0xFF2A241D);
  static const Color ritualPaperLight = Color(0xFFFDF8EF);
  static const Color ritualPaperBorderDark = Color(0xFF564739);
  static const Color ritualPaperBorderLight = Color(0xFFE0D1BC);
  static const Color ritualTextDark = Color(0xFFF8ECDD);
  static const Color ritualTextLight = Color(0xFF3A2C22);
  static const Color ritualSecondaryTextDark = Color(0xFFD1BFA9);
  static const Color ritualSecondaryTextLight = Color(0xFF8A6E56);
  static const Color ritualAccentDark = Color(0xFFD3A96D);
  static const Color ritualAccentLight = Color(0xFFB6874C);
  static const Color ritualBadgeBackgroundDark = Color(0xE646382C);
  static const Color ritualBadgeBackgroundLight = Color(0xCCFFFFFF);
  static const Color ritualBadgeTextDark = Color(0xFFF8ECDD);
  static const Color ritualBadgeTextLight = Color(0xFF6B4E34);
  static const Color ritualOverlayDark = Color(0x14000000);
  static const Color ritualOverlayLight = Color(0x10C79C6E);

  static const Color diffuseStageDark = Color(0xFF16192A);
  static const Color diffuseStageLight = Color(0xFFF6F4FF);
  static const Color diffusePaperDark = Color(0xFF252A43);
  static const Color diffusePaperLight = Color(0xFFFDFBFF);
  static const Color diffusePaperBorderDark = Color(0xFF48507A);
  static const Color diffusePaperBorderLight = Color(0xFFE6DAFF);
  static const Color diffuseTextDark = Color(0xFFF4F1FF);
  static const Color diffuseTextLight = Color(0xFF31274D);
  static const Color diffuseSecondaryTextDark = Color(0xFFC7BFEE);
  static const Color diffuseSecondaryTextLight = Color(0xFF7D6EA1);
  static const Color diffuseAccentDark = Color(0xFFA9B5FF);
  static const Color diffuseAccentLight = Color(0xFF8B8AF5);
  static const Color diffuseBadgeBackgroundDark = Color(0xE634395A);
  static const Color diffuseBadgeBackgroundLight = Color(0xCCFFFFFF);
  static const Color diffuseBadgeTextDark = Color(0xFFF5F3FF);
  static const Color diffuseBadgeTextLight = Color(0xFF6660A8);
  static const Color diffuseOverlayDark = Color(0x145A66A3);
  static const Color diffuseOverlayLight = Color(0x14C3C8FF);

  static const Color journalStageDark = Color(0xFF202322);
  static const Color journalStageLight = Color(0xFFF7F3EA);
  static const Color journalPaperDark = Color(0xFFFAF2E2);
  static const Color journalPaperLight = Color(0xFFFFFBF5);
  static const Color journalPaperBorderDark = Color(0xFFD9C6A8);
  static const Color journalPaperBorderLight = Color(0xFFE8DCC8);
  static const Color journalTextDark = Color(0xFF2B2016);
  static const Color journalTextLight = Color(0xFF3A2C22);
  static const Color journalSecondaryTextDark = Color(0xFF7D6753);
  static const Color journalSecondaryTextLight = Color(0xFF8E7865);
  static const Color journalAccentDark = Color(0xFFFF5D7A);
  static const Color journalAccentLight = Color(0xFFFF4A6B);
  static const Color journalBadgeBackgroundDark = Color(0xE6FBF0DE);
  static const Color journalBadgeBackgroundLight = Color(0xCCFFFFFF);
  static const Color journalBadgeTextDark = Color(0xFF6B5644);
  static const Color journalBadgeTextLight = Color(0xFF7D6A59);
  static const Color journalOverlayDark = Color(0x1024C6A2);
  static const Color journalOverlayLight = Color(0x1438DCC7);

  static const Color techStage = Color(0xFF0B1019);
  static const Color techPaper = Color(0xFF141C2B);
  static const Color techPaperBorder = Color(0xFF314462);
  static const Color techText = Color(0xFFE8F2FF);
  static const Color techSecondaryText = Color(0xFF8FB0D9);
  static const Color techAccent = Color(0xFF4EE0FF);
  static const Color techBadgeBackground = Color(0xCC18273E);
  static const Color techBadgeText = Color(0xFFE8F2FF);
  static const Color techOverlay = Color(0x1237A4C8);

  static const Color gentleStageDark = Color(0xFF1D1E26);
  static const Color gentleStageLight = Color(0xFFF7F8F5);
  static const Color gentlePaperDark = Color(0xFF2A2D36);
  static const Color gentlePaperLight = Color(0xFFFFFEFB);
  static const Color gentlePaperBorderDark = Color(0xFF454956);
  static const Color gentlePaperBorderLight = Color(0xFFE8E7DF);
  static const Color gentleTextDark = Color(0xFFF4F4F0);
  static const Color gentleTextLight = Color(0xFF2F3136);
  static const Color gentleSecondaryTextDark = Color(0xFFC7C9CE);
  static const Color gentleSecondaryTextLight = Color(0xFF7A7D86);
  static const Color gentleAccentDark = Color(0xFFFFB0BE);
  static const Color gentleAccentLight = Color(0xFFFF7A95);
  static const Color gentleBadgeBackgroundDark = Color(0xCC343840);
  static const Color gentleBadgeBackgroundLight = Color(0xCCFFFFFF);
  static const Color gentleBadgeTextDark = Color(0xFFF4F4F0);
  static const Color gentleBadgeTextLight = Color(0xFF6F7280);
  static const Color gentleOverlayDark = Color(0x10B7F0D7);
  static const Color gentleOverlayLight = Color(0x10BFE9D2);

  static const Color gentleBackdropMint = Color(0xFFB6E8D6);
  static const Color diffuseBackdropLavender = Color(0xFFBBC7FF);
  static const Color diffuseBackdropPink = Color(0xFFFFC7EB);
  static const Color journalTape = Color(0x99A5B4FF);
  static const Color journalSticker = Color(0x88A7B8FF);
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
      case ColorType.modalScrim:
        return isDark ? const Color(0x66101012) : const Color(0x40111827);
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
  modalScrim,
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
