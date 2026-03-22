import 'package:flutter/material.dart';

class AppTypography {
  /// Minimum legible caption size used for compressed toolbar states.
  static const double xxs = 9.0;
  static const double xs = 10.0;
  static const double xsPlus = 11.0;
  static const double sm = 12.0;
  static const double smPlus = 13.0;
  static const double base = 14.0;
  static const double md = base; // Alias for backward compatibility
  static const double lg = 16.0;
  static const double xl = 18.0;
  static const double xxl = 20.0;
  static const double xxxl = 22.0;

  static const double title = xl;
  static const double sectionTitle = lg;
  static const double body = base;
  static const double secondary = sm;
  static const double caption = xs;

  /// 工具面板功能项文案保持与发现页主体一致。
  static const double toolPanelItemLabel = base;
  static const double toolPanelCategoryLabel = base;
  static const double actionCount = lg;

  /// 一级 Tab 字号（发现/圈子/趣聊统一，与正文一致）
  static const double primaryTabLabel = lg;

  /// 一级 Tab 统一响应式字号。
  static double primaryTabLabelResponsive(BuildContext context) => responsive(
    context,
    compact: base,
    regular: primaryTabLabel,
    expanded: xl,
  );

  /// 一级 Tab 字重（选中/未选中统一，避免切换时布局抖动）
  static const FontWeight primaryTabLabelWeight = medium;

  /// 一级 Tab 选中/未选中统一字重，保证视觉稳定。
  static const FontWeight primaryTabSelectedWeight = primaryTabLabelWeight;
  static const FontWeight primaryTabUnselectedWeight = primaryTabLabelWeight;

  /// 二级 Tab 基础字号。
  static const double secondaryTabLabel = smPlus;

  /// 二级 Tab 统一响应式字号。
  static double secondaryTabLabelResponsive(BuildContext context) => responsive(
    context,
    compact: sm,
    regular: secondaryTabLabel,
    expanded: base,
  );

  /// 二级 Tab 选中态略加重，未选中保持中黑。
  static const FontWeight secondaryTabSelectedWeight = semiBold;
  static const FontWeight secondaryTabUnselectedWeight = medium;

  /// 底部栏未选中字号（与一级 Tab 一致）
  static const double bottomNavLabelUnselected = primaryTabLabel;

  /// 底部栏选中字号（比未选中大一档）
  static const double bottomNavLabelSelected = xl;

  /// 底部栏字重（选中不加粗）
  static const FontWeight bottomNavLabelWeight = medium;

  /// 欢迎页主标题（hero）
  static const double welcomeHeroTitle = 48.0;

  // ==================== iOS 语义字号 ====================
  static const double iosLargeTitle = 34.0;
  static const double iosProfileTitle = 28.0;
  static const double iosTitle2 = 22.0;
  static const double iosTitle3 = 20.0;
  static const double iosNavTitle = 17.0;
  static const double iosBody = 17.0;
  static const double iosCallout = 16.0;
  static const double iosSubheadline = 15.0;
  static const double iosFootnote = 13.0;
  static const double iosCaption1 = 12.0;
  static const double iosCaption2 = 11.0;
  static const double iosSectionHeader = iosFootnote;
  static const double iosButton = iosSubheadline;

  /// 内容分享海报标题/正文层级
  static const double sharePosterEyebrow = 42.0;
  static const double sharePosterSubtitle = 28.0;
  static const double sharePosterHeadline = 58.0;
  static const double sharePosterBody = 34.0;
  static const double sharePosterDeeplink = 30.0;
  static const double sharePosterMeta = 26.0;

  /// 正文行高倍数（TextStyle.height）
  static const double bodyLineHeight = 1.4;

  /// 紧凑标题/卡片单行行高
  static const double lineHeightTight = 1.2;

  /// 紧凑说明文案行高
  static const double lineHeightCompact = 1.3;

  /// 宽松行高倍数（展开文本等）
  static const double lineHeightRelaxed = 1.5;

  static const FontWeight normal = FontWeight.w400;
  static const FontWeight regular = normal;
  static const FontWeight medium = FontWeight.w500;
  static const FontWeight semiBold = FontWeight.w600;
  static const FontWeight bold = FontWeight.w700;
  static const FontWeight extraBold = FontWeight.w800;
  static const FontWeight black = FontWeight.w900;

  static double responsive(
    BuildContext context, {
    required double compact,
    required double regular,
    required double expanded,
  }) {
    final width = MediaQuery.sizeOf(context).width;
    if (width < 360) return compact;
    if (width >= 600) return expanded;
    return regular;
  }
}
