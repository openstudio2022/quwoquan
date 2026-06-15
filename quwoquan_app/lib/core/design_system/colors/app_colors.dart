import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

class AppColors {
  AppColors._();

  // ==================== 品牌蓝色阶 ====================
  /// 更轻快的品牌蓝色阶：保留 iOS 的清透感，避免大面积使用时偏沉。
  static const Color brandBlue50 = Color(0xFFEFF8FF);
  static const Color brandBlue100 = Color(0xFFDCEFFF);
  static const Color brandBlue300 = Color(0xFF76C7FF);
  static const Color brandBlue400 = Color(0xFF36A8FF);
  static const Color brandBlue500 = Color(0xFF1491FF);
  static const Color brandBlue600 = Color(0xFF0A84FF);
  static const Color brandBlue700 = Color(0xFF0072E5);
  static const Color brandBlue800 = Color(0xFF005BBC);

  /// 品牌主蓝，作为全局默认强调色。
  static const Color primaryColor = brandBlue600;
  static const Color primaryColorHover = brandBlue500;
  static const Color primaryColorActive = brandBlue700;

  static const Color secondaryColor = Color(0xFF5E5CE6);
  static const Color secondaryColorHover = Color(0xFF7D7AFF);
  static const Color secondaryColorActive = Color(0xFF4B49D1);

  static const Color accentColor = Color(0xFF34C759);
  static const Color error = Color(0xFFFF3B30);
  static const Color success = Color(0xFF34C759);
  static const Color warning = Color(0xFFFF9F0A);

  /// 通话/RTC 弱网指示（橙红，与系统 [warning] 区分）
  static const Color networkCallQualityWeak = Color(0xFFFF6B35);
  static const Color info = primaryColor;
  static const Color white = Colors.white;
  static const Color black = Colors.black;

  /// 全透明（沉浸式顶栏、barrier、渐变端点等）
  static const Color transparent = Color(0x00000000);

  /// 分享海报主标题/深链区等高对比黑字（Canvas 绘制，非主题色）
  static const Color sharePosterInkHighContrast = Color(0xDE000000);

  /// 分享海报深链块浅灰底
  static const Color sharePosterDeeplinkSurface = Color(0xFFF5F5F5);

  /// 图片编辑器 Pro — HSL 色环通道色标（固定色相参考）
  static const Color imageEditorHslRed = Color(0xFFE85656);
  static const Color imageEditorHslOrange = Color(0xFFE79A4B);
  static const Color imageEditorHslYellow = Color(0xFFDED95A);
  static const Color imageEditorHslGreen = Color(0xFF70D85C);
  static const Color imageEditorHslCyan = Color(0xFF4DCFD2);
  static const Color imageEditorHslBlue = Color(0xFF4D73DE);
  static const Color imageEditorHslPurple = Color(0xFF9B57D8);
  static const Color imageEditorHslMagenta = Color(0xFFD84FC7);

  /// 九宫格/动态图片占位浅灰
  static const Color gridImagePlaceholderLight = Color(0xFFEEEEEE);

  /// 动态视频卡片底层深色底
  static const Color momentVideoCardBackdrop = Color(0xFF212121);

  /// 发现页作品宫格卡片内层占位（浅灰）
  static const Color discoveryPostGridInnerFallback = Color(0xFFE0E0E0);

  /// 发现页宫格占位图标色
  static const Color discoveryPostGridIconMuted = Color(0xFF757575);

  /// iOS 工具栏次要图标色（深/浅外观）
  static const Color iosToolbarSecondaryIconDark = Color(0xFF98989F);
  static const Color iosToolbarSecondaryIconLight = Color(0xFF8E8E93);

  /// iOS 系统青强调（深色模式下链接/高亮）
  static const Color iosSystemCyanAccent = Color(0xFF64D2FF);

  /// 小型弹出层主文字（再生选项等）
  static const Color iosPopupPrimaryLabelOnDark = Color(0xFFEBEBF5);
  static const Color iosPopupPrimaryLabelOnLight = Color(0xFF1C1C1E);

  /// 弹出层细分隔线
  static const Color iosPopupHairlineSeparatorDark = Color(0xFF38383A);
  static const Color iosPopupHairlineSeparatorLight = Color(0xFFE5E5EA);

  static const Color overlayMedium = Color(0x80000000);
  static const Color overlayStrong = Color(0xB3000000);
  static const Color overlayDark = Color(0xCC000000);
  static const Color overlayLight = Color(0x4D000000);

  /// 媒体查看器等深色背景上的「已关注」按钮背景，低对比度融入沉浸模式
  static const Color followingButtonOnDark = Color(0xFF333333);
  static const Color iosSystemSurfaceDark = Color(0xFF2C2C2E);
  static const Color iosAccentLight = primaryColor;
  static const Color iosAccentDark = brandBlue500;

  // ==================== 小趣身份色（assistant brand mark） ====================
  /// 「小趣」品牌身份色（浅色 / 常规背景）。
  ///
  /// 全 App 中所有承担「这是小趣」身份语义的 `CupertinoIcons.sparkles` /
  /// `Icons.auto_awesome` 必须引用此 token，建立用户对「小趣 = 这个蓝色」
  /// 的全局认知锚点。当前与 iOS 系统蓝同源，未来若要差异化只需改此一处。
  ///
  /// 反例（禁止）：
  /// - 用 `welcomeTitleGradientMid` 等装饰色作为小趣 icon 颜色
  /// - 在新增页面直接写 `color: AppColors.primaryColor` 表达小趣身份
  ///
  /// 例外：助手悬浮球内部的 sparkle 是反白处理（用 `AppColors.white`），
  /// 不属于本 token 语义。
  static const Color assistantMarkColor = primaryColor;

  /// 「小趣」品牌身份色（深色 / 品牌渐变 / 沉浸面板背景）。
  ///
  /// 在欢迎页深蓝渐变、媒体沉浸模式等深色背景上，`assistantMarkColor`
  /// 的对比度不足，必须使用更亮的系统蓝变体；与 iOS 深色模式 accent 同源。
  static const Color assistantMarkColorOnDark = iosAccentDark;
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
  static const Color welcomeBackground = primaryColor;
  static const Color welcomeGradientStart = brandBlue500;
  static const Color welcomeGradientEnd = Color(0xFF1554D1);
  static const Color welcomeForeground = Colors.white;
  static const Color welcomeForegroundMuted = brandBlue50;
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
  static const Color webPcWelcomeCopySecondary = Color(0xB8FFFFFF);
  static const Color webPcWelcomeCopyTertiary = Color(0x7AFFFFFF);
  static const Color webPcWelcomeDownloadPanelBackground = Color(0x14FFFFFF);
  static const Color webPcWelcomeDownloadPanelBorder = Color(0x29FFFFFF);
  static const Color webPcWelcomeDownloadPanelCaption = Color(0xA3FFFFFF);
  static const Color webPcWelcomeVisualGlowPrimary = Color(0x700A84FF);
  static const Color webPcWelcomeVisualGlowSecondary = Color(0x2467E8F9);
  static const Color webPcWelcomePetalStart = Color(0xEBC084FC);
  static const Color webPcWelcomePetalEnd = Color(0xB867E8F9);
  static const Color webPcGhostButtonForeground = Color(0xD1FFFFFF);
  static const Color webPcSelectedSurface = Color(0x1A0A84FF);
  static const Color webPcCreateSelectedSurface = Color(0x140A84FF);
  static const Color webPcLoginScrim = Color(0x66000000);
  static const Color webPcLoginSurfaceShadow = Color(0x26000000);
  static const Color webPcToolbarShadow = Color(0x14000000);

  /// 第三方登录品牌色（与 simple_icons 官方品牌色一致，作为语义 token 复用）
  static const Color loginMethodWechatBrand = Color(0xFF07C160);
  static const Color loginMethodQqBrand = Color(0xFF1EBAFC);
  static const Color loginMethodAlipayBrand = Color(0xFF1677FF);

  /// 「其他手机号」登录方式实心圆底：与微信/QQ/支付宝同为实心彩色圆 + 白色图标，
  /// 取应用品牌蓝，保证图一/图二底部入口视觉权重一致（不再是浅灰近背景的隐形圆）。
  static const Color loginMethodPhoneCircle = brandBlue600;

  /// 登录页高保背景与控件语义色。
  static const Color loginPageBackgroundLight = Color(0xFFF7F7FB);
  static const Color loginPageBackgroundDark = iosGroupedBackgroundDark;
  static const Color loginInputSurfaceLight = Color(0xFFFFFFFF);
  static const Color loginInputSurfaceDark = iosGroupedSurfaceDark;
  static const Color loginInputBorderLight = Color(0xFFD7D7DE);
  static const Color loginInputBorderDark = iosPopupHairlineSeparatorDark;
  static const Color loginInputFocusedBorderLight = brandBlue600;
  static const Color loginInputFocusedBorderDark = brandBlue500;
  static const Color loginPrimaryDisabledLight = Color(0xFFA9D3FF);
  static const Color loginPrimaryDisabledDark = Color(0xFF295F9B);
  static const Color loginOtherDividerLight = Color(0xFFDADAE0);
  static const Color loginOtherDividerDark = iosPopupHairlineSeparatorDark;

  static Color loginPageBackground(BuildContext context) {
    return CupertinoDynamicColor.resolve(
      const CupertinoDynamicColor.withBrightness(
        color: loginPageBackgroundLight,
        darkColor: loginPageBackgroundDark,
      ),
      context,
    );
  }

  static Color loginInputSurface(BuildContext context) {
    return CupertinoDynamicColor.resolve(
      const CupertinoDynamicColor.withBrightness(
        color: loginInputSurfaceLight,
        darkColor: loginInputSurfaceDark,
      ),
      context,
    );
  }

  static Color loginInputBorder(BuildContext context) {
    return CupertinoDynamicColor.resolve(
      const CupertinoDynamicColor.withBrightness(
        color: loginInputBorderLight,
        darkColor: loginInputBorderDark,
      ),
      context,
    );
  }

  static Color loginInputFocusedBorder(BuildContext context) {
    return CupertinoDynamicColor.resolve(
      const CupertinoDynamicColor.withBrightness(
        color: loginInputFocusedBorderLight,
        darkColor: loginInputFocusedBorderDark,
      ),
      context,
    );
  }

  static Color loginPrimaryDisabled(BuildContext context) {
    return CupertinoDynamicColor.resolve(
      const CupertinoDynamicColor.withBrightness(
        color: loginPrimaryDisabledLight,
        darkColor: loginPrimaryDisabledDark,
      ),
      context,
    );
  }

  static Color loginOtherDivider(BuildContext context) {
    return CupertinoDynamicColor.resolve(
      const CupertinoDynamicColor.withBrightness(
        color: loginOtherDividerLight,
        darkColor: loginOtherDividerDark,
      ),
      context,
    );
  }

  static Color webPcToolbarSurface(BuildContext context) =>
      iosGroupedSurface(context).withValues(alpha: 0.96);

  /// 欢迎页 — 系统深色外观（与浅色同源色相，压低亮度，S6 对称深色）
  static const Color welcomeBackgroundDark = Color(0xFF0F172A);
  static const Color welcomeGradientStartDark = Color(0xFF1E3A8A);
  static const Color welcomeGradientEndDark = Color(0xFF020617);
  static const Color welcomeForegroundMutedDark = Color(0xFFBFDBFE);
  static const Color welcomeButtonBgDark = Color(0x33FFFFFF);

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

  /// 创作页媒体错误占位渐变
  static const Color createMediaFallbackGradientTop = Color(0xFF343434);
  static const Color createMediaFallbackGradientBottom = Color(0xFF141414);
  static const Color webPcMediaFallbackGradientTop = brandBlue50;
  static const Color webPcMediaFallbackGradientBottom = white;

  // ==================== Feed 卡片语义色 ====================

  /// 关注流卡片浅色边框（柔和轮廓，非强分隔）
  static const Color feedCardBorderLight = Color(0xFFE8E8ED);
  static const Color feedCardBorderDark = Color(0xFF38383A);

  /// 关注流卡片表面色（比纯白略暖，与灰底形成轻微层次）
  static const Color feedCardSurfaceLight = Color(0xFFFFFEFD);
  static const Color feedCardSurfaceDark = Color(0xFF1C1C1E);

  /// Feed 互动图标默认色（中性灰，不喧宾夺主）
  static const Color feedActionIconLight = Color(0xFF8E8E93);
  static const Color feedActionIconDark = Color(0xFF98989F);

  static Color feedCardBorder(BuildContext context) =>
      CupertinoDynamicColor.resolve(
        CupertinoDynamicColor.withBrightness(
          color: feedCardBorderLight,
          darkColor: feedCardBorderDark,
        ),
        context,
      );

  static Color feedCardSurface(BuildContext context) =>
      CupertinoDynamicColor.resolve(
        CupertinoDynamicColor.withBrightness(
          color: feedCardSurfaceLight,
          darkColor: feedCardSurfaceDark,
        ),
        context,
      );

  static Color feedActionIcon(BuildContext context) =>
      CupertinoDynamicColor.resolve(
        CupertinoDynamicColor.withBrightness(
          color: feedActionIconLight,
          darkColor: feedActionIconDark,
        ),
        context,
      );

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

  static Color iosAccent(BuildContext context) => CupertinoDynamicColor.resolve(
    const CupertinoDynamicColor.withBrightness(
      color: iosAccentLight,
      darkColor: iosAccentDark,
    ),
    context,
  );

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

/// 文章阅读器「纸张质感」色板（见 `resolveArticlePaperPalette`）。
class ArticlePaperPaletteColors {
  ArticlePaperPaletteColors._();

  // Work Browser Dark Paper V1.0
  static const Color darkPaperStage = Color(0xFF0F1115);
  static const Color darkPaperPaper = Color(0xFF161A20);
  static const Color darkPaperBorder = Color(0xFF242A33);
  static const Color darkPaperText = Color(0xFFE6E8EB);
  static const Color darkPaperSecondaryText = Color(0xFF8B919C);
  static const Color darkPaperAccent = AppColors.iosAccentDark;
  static const Color darkPaperBadgeBackground = Color(0xFF242A33);
  static const Color darkPaperBadgeText = Color(0xFFE6E8EB);
  static const Color darkPaperOverlay = Color(0x0AFFFFFF);

  static const Color coolGrayStage = Color(0xFF101318);
  static const Color coolGrayPaper = Color(0xFF1A1F26);
  static const Color coolGrayBorder = Color(0xFF29313B);
  static const Color coolGrayText = Color(0xFFE6E8EB);
  static const Color coolGraySecondaryText = Color(0xFF8B919C);
  static const Color coolGrayAccent = Color(0xFF7BA7FF);
  static const Color coolGrayBadgeBackground = Color(0xFF29313B);
  static const Color coolGrayBadgeText = Color(0xFFE6E8EB);
  static const Color coolGrayOverlay = Color(0x0AFFFFFF);

  static const Color warmBlackStage = Color(0xFF13100D);
  static const Color warmBlackPaper = Color(0xFF1E1A16);
  static const Color warmBlackBorder = Color(0xFF302820);
  static const Color warmBlackText = Color(0xFFE8E6E3);
  static const Color warmBlackSecondaryText = Color(0xFF8D8680);
  static const Color warmBlackAccent = Color(0xFFD0A36C);
  static const Color warmBlackBadgeBackground = Color(0xFF302820);
  static const Color warmBlackBadgeText = Color(0xFFE8E6E3);
  static const Color warmBlackOverlay = Color(0x0AFFF3E8);

  static const Color inkGreenStage = Color(0xFF101511);
  static const Color inkGreenPaper = Color(0xFF161B18);
  static const Color inkGreenBorder = Color(0xFF263129);
  static const Color inkGreenText = Color(0xFFE6EAE6);
  static const Color inkGreenSecondaryText = Color(0xFF879086);
  static const Color inkGreenAccent = Color(0xFF8CBF9A);
  static const Color inkGreenBadgeBackground = Color(0xFF263129);
  static const Color inkGreenBadgeText = Color(0xFFE6EAE6);
  static const Color inkGreenOverlay = Color(0x0AE6FAE6);

  static const Color deepBrownStage = Color(0xFF15110F);
  static const Color deepBrownPaper = Color(0xFF1F1A17);
  static const Color deepBrownBorder = Color(0xFF322922);
  static const Color deepBrownText = Color(0xFFE8E4DF);
  static const Color deepBrownSecondaryText = Color(0xFF8F8882);
  static const Color deepBrownAccent = Color(0xFFC79A72);
  static const Color deepBrownBadgeBackground = Color(0xFF322922);
  static const Color deepBrownBadgeText = Color(0xFFE8E4DF);
  static const Color deepBrownOverlay = Color(0x0AFFF0E6);
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
      case ColorType.globalSearchFieldBackground:
        return isDark ? const Color(0xFF2A2B2F) : AppColors.white;
      case ColorType.globalSearchFieldBorder:
        return isDark
            ? AppColors.white.withValues(alpha: 0.06)
            : AppColors.white.withValues(alpha: 0.42);
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
      // S6: RTC 来电/去电舞台渐变 — 深色下略压暗，避免与浅色壳「同图」
      case ColorType.callStageGradientStart:
        return isDark
            ? const Color(0xFF1D4ED8)
            : AppColors.welcomeGradientStart;
      case ColorType.callStageGradientEnd:
        return isDark ? const Color(0xFF1E1B4B) : AppColors.welcomeGradientEnd;
      // WebView / 壳层信息卡：替代裸 white + black(alpha) 边框
      case ColorType.chromeInfoCardBackground:
        return getColor(isDark, ColorType.surfaceElevated);
      case ColorType.chromeInfoCardBorder:
        return isDark ? const Color(0xFF3A3A3C) : const Color(0x1A000000);
      case ColorType.webViewPlaceholderBackground:
        return getColor(isDark, ColorType.pageBackground);
      case ColorType.dropShadow:
        return AppColors.black.withValues(alpha: isDark ? 0.14 : 0.05);

      /// 全屏竖滑视频/视频模式底：固定黑场（与浅色系统栏对比由 AnnotatedRegion 处理）
      case ColorType.fullBleedMediaBackdrop:
        return AppColors.black;
      case ColorType.secondaryCapsuleTrack:
        return isDark
            ? AppColors.white.withValues(alpha: 0.04)
            : AppColors.black.withValues(alpha: 0.03);

      /// 缩略图/视频封面上的角标与控件（叠在任意内容上，固定深底浅字）
      case ColorType.mediaThumbnailOverlayScrim:
        return AppColors.black.withValues(alpha: 0.25);
      case ColorType.mediaThumbnailOverlayBorder:
        return AppColors.white.withValues(alpha: 0.1);
      case ColorType.mediaThumbnailOverlayForegroundMuted:
        return AppColors.white.withValues(alpha: 0.9);
      case ColorType.mediaThumbnailOverlayForeground:
        return AppColors.white;

      /// 发现页竖滑全屏视频轨道 UI（叠在内容上，与系统深浅无关）
      case ColorType.videoImmersionBottomGradientEnd:
        return AppColors.black.withValues(alpha: 0.8);
      case ColorType.videoImmersionOverlayForeground:
        return AppColors.white;
      case ColorType.videoImmersionOverlaySecondary:
        return AppColors.white.withValues(alpha: 0.9);
      case ColorType.videoImmersionOverlayTertiary:
        return AppColors.white.withValues(alpha: 0.8);
      case ColorType.videoImmersionOverlayQuaternary:
        return AppColors.white.withValues(alpha: 0.78);

      /// 创作页媒体格按压/遮罩基色（深色模式白、浅色模式黑，再叠 alpha）
      case ColorType.createMediaOverlayBase:
        return isDark ? AppColors.white : AppColors.black;
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
  globalSearchFieldBackground,
  globalSearchFieldBorder,

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

  /// RTC incoming/outgoing 全屏渐变起点（随 isDark 变体）
  callStageGradientStart,

  /// RTC incoming/outgoing 全屏渐变终点
  callStageGradientEnd,

  /// WebView 页顶信息卡表面（原固定白底）
  chromeInfoCardBackground,

  /// WebView 页信息卡描边（原 black 0.06）
  chromeInfoCardBorder,

  /// WebView 宿主底层色（setBackgroundColor）
  webViewPlaceholderBackground,

  /// 卡片浮层阴影（浅/深不同透明度）
  dropShadow,

  /// 全屏媒体沉浸底（发现视频轨道等）
  fullBleedMediaBackdrop,

  /// 二级胶囊 Tab 轨道浅填充（原 white/black 透明度）
  secondaryCapsuleTrack,

  /// 媒体缩略图角标底（黑半透明）
  mediaThumbnailOverlayScrim,

  /// 媒体缩略图角标描边
  mediaThumbnailOverlayBorder,

  /// 媒体缩略图角标字/图标（浅、略透明）
  mediaThumbnailOverlayForegroundMuted,

  /// 媒体缩略图角标字/图标（浅、不透明）
  mediaThumbnailOverlayForeground,

  /// 竖滑视频底渐变末端
  videoImmersionBottomGradientEnd,

  videoImmersionOverlayForeground,
  videoImmersionOverlaySecondary,
  videoImmersionOverlayTertiary,
  videoImmersionOverlayQuaternary,

  /// 创作流媒体 tile 遮罩基色
  createMediaOverlayBase,
}
