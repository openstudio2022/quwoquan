import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 设置页统一语义 token，供聊天设置、账号设置等所有设置类页面复用。
/// 浅色/深色模式均通过 [isDark] 区分，确保一致。
class SettingsSemanticConstants {
  SettingsSemanticConstants._();

  // ==================== 页面与功能块 ====================
  /// 设置页整体背景色（浅色：偏灰；深色：深灰）
  static Color pageBackground(bool isDark) =>
      AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);

  /// 功能块背景色（浅色：白；深色：深黑）
  static Color blockBackground(bool isDark) =>
      AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);

  /// 创作页（微趣/美图/视频/文章）整体背景：浅色纯白、深色与设置页一致；分割线保持 [createInlineDividerColor]；支持深色模式
  static Color createPageBackground(bool isDark) => isDark
      ? AppColorsFunctional.getColor(true, ColorType.backgroundSecondary)
      : AppColorsFunctional.getColor(false, ColorType.backgroundPrimary);

  /// 创作页功能块/AppBar 背景：浅色纯白、深色深黑 [backgroundPrimary]；支持深色模式
  static Color createPageBlockBackground(bool isDark) =>
      AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);

  /// 功能块之间垂直间距（与设计一致，偏小）
  static double get blockSpacing => AppSpacing.sm + AppSpacing.xs; // 12

  /// 功能块圆角
  static double get blockBorderRadius => AppSpacing.borderRadius;

  /// 功能块边框色（极浅，仅做轻微区分）
  static Color blockBorderColor(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    return c.withValues(alpha: 0.12);
  }

  // ==================== 内容与分割线 ====================
  /// 设置项主文字颜色
  static Color labelColor(bool isDark) =>
      AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);

  /// 设置项次要文字/箭头颜色
  static Color secondaryColor(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    return c.withValues(alpha: 0.6);
  }

  /// 创作页输入提示文字颜色（更浅、更中性）
  static Color createInputHintColor(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    return isDark ? c.withValues(alpha: 0.45) : c.withValues(alpha: 0.4);
  }

  /// 创作页顶部标题字号（与设置项名一致）
  static double get createToolbarTitleFontSize => 17.0;

  /// 创作页：标题输入字号（标题类）
  static double get createInputTitleFontSize => 20.0;

  /// 创作页：正文/配文字号
  static double get createInputBodyFontSize => 16.0;

  /// 创作页：微趣正文输入字号
  static double get createInputMomentFontSize => 17.0;

  /// 创作页：文章标题字号（与图片标题一致）
  static double get createInputArticleTitleFontSize => createInputTitleFontSize;

  /// 创作页：文章正文字号
  static double get createInputArticleBodyFontSize => 18.0;

  /// 创作页：设置项名字号（与顶部标题同号，非黑体）
  static double get createSettingItemLabelFontSize =>
      createToolbarTitleFontSize;

  /// 创作页：设置项值字号（比设置项名小一号）
  static double get createSettingItemValueFontSize => AppTypography.lg;

  /// 创作页：设置项值颜色（更浅）
  static Color createSettingItemValueColor(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    return c.withValues(alpha: 0.5);
  }

  /// 创作页：添加图片/视频/封面块背景（大图与列表中一致）：浅色纯白、深色 [backgroundPrimary] 与页面块一致；支持深色模式
  static Color createAddTileBackground(bool isDark) =>
      AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);

  /// 创作页：添加块虚线边框颜色：浅色与白底有对比度、深色与深底有对比度；支持深色模式
  static Color createAddTileBorderColor(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    return isDark ? c.withValues(alpha: 0.28) : c.withValues(alpha: 0.22);
  }

  /// 创作页：添加块内图标/文字颜色（+、上传视频、添加封面等）：浅色/深色均与背景有对比度；支持深色模式
  static Color createAddTileIconColor(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    return isDark ? c.withValues(alpha: 0.62) : c.withValues(alpha: 0.5);
  }

  /// 创作页：添加按钮虚线边框宽度
  static double get createAddTileBorderWidth => 1.0;

  /// 创作页：添加按钮虚线长度
  static double get createAddTileDashLength => 5.0;

  /// 创作页：添加按钮虚线间隔
  static double get createAddTileDashGap => 4.0;

  /// 创作页：添加按钮圆角
  static double get createAddTileBorderRadius => 8.0;

  /// 块内分割线颜色（非常细、浅）
  static Color dividerColor(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    return c.withValues(alpha: 0.12);
  }

  /// 块内分割线粗细
  static double get dividerThickness => 0.5;

  /// 块内行垂直内边距（与区块首尾一致）
  static double get sectionVerticalPadding =>
      AppSpacing.sm + AppSpacing.xs + 1.0;

  /// 块内水平内边距
  static double get blockHorizontalPadding =>
      AppSpacing.semantic[DesignSemanticConstants
          .container]?[DesignSemanticConstants.md] ??
      AppSpacing.containerMd;

  // ==================== 开关 Switch ====================
  /// 选中：轨道色（主色/蓝）
  static Color get switchActiveTrackColor => AppColors.primaryColor;

  /// 选中：拇指色
  static Color get switchActiveThumbColor => Colors.white;

  /// 未选中：轨道色（明显灰，与白拇指对比度接近选中态蓝底白钮）
  static Color switchInactiveTrackColor(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    return isDark ? c.withValues(alpha: 0.5) : c.withValues(alpha: 0.45);
  }

  /// 未选中：拇指色（白，与浅灰轨道对比明显）
  static Color get switchInactiveThumbColor => Colors.white;

  /// 开关轨道轮廓线宽（细线）
  static double get switchTrackOutlineWidth => 0.25;

  // ==================== 危险操作（如退出群聊） ====================
  /// 危险操作文字色（红，稍浅）
  static Color exitActionColor(bool isDark) {
    final base = AppColors.error;
    final mix = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    return Color.lerp(base, mix, 0.12) ?? base;
  }

  // ==================== 选择/设置页操作按钮 ====================
  /// 强调色按钮（选择、确认等）：背景
  static Color get actionButtonPrimaryBackground => AppColors.primaryColor;

  /// 强调色按钮：文字
  static Color get actionButtonPrimaryForeground => Colors.white;

  /// 未选中/禁用时按钮背景（深一点灰，便于区分）
  static Color actionButtonDisabledBackground(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    return isDark ? c.withValues(alpha: 0.5) : c.withValues(alpha: 0.45);
  }

  /// 未选中/禁用时按钮文字
  static Color actionButtonDisabledForeground(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    return c.withValues(alpha: 0.55);
  }

  /// 操作按钮高度 - 小（列表内、紧凑）
  static double get actionButtonHeightSmall => 36.0;

  /// 操作按钮高度 - 中（底部栏「选择」等，默认）
  static double get actionButtonHeightMedium => 40.0;

  /// 操作按钮高度 - 大（主 CTA）
  static double get actionButtonHeightLarge => AppSpacing.buttonHeight;

  /// 操作按钮水平内边距（中）
  static double get actionButtonPaddingHorizontal => AppSpacing.lg;

  /// 操作按钮垂直内边距（中）
  static double get actionButtonPaddingVertical => AppSpacing.sm;

  /// 操作按钮圆角
  static double get actionButtonBorderRadius => AppSpacing.borderRadius;

  // ==================== 选择页 Checkbox ====================
  /// 未选中：边框色（可见，不与背景融在一起）
  static Color checkboxUnselectedBorderColor(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    return isDark ? c.withValues(alpha: 0.6) : c.withValues(alpha: 0.5);
  }

  /// 未选中：边框宽
  static double get checkboxUnselectedBorderWidth => 1.5;

  /// 未选中：内部填充（极浅灰，使方框可见）
  static Color checkboxUnselectedFillColor(bool isDark) {
    final c = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    return c.withValues(alpha: 0.08);
  }

  /// 选中：填充色
  static Color get checkboxSelectedColor => AppColors.primaryColor;

  /// Checkbox 缩放（与列表紧凑）
  static double get checkboxScale => 0.82;

  // ==================== 创作页（发微趣/美图/视频/文章） ====================
  /// 文字与图片之间的分割线（同一体块内，细线）
  static Color createInlineDividerColor(bool isDark) => dividerColor(isDark);

  /// 图片区与设置块之间的带状分割高度（灰带）
  static double get createStripSeparatorHeight => blockSpacing;

  /// 顶部工具栏与首个内容块之间：仅分割线，无带状间隙（0 = 紧贴分割线）
  static double get createContentTopPadding => 0;

  /// AppBar 内发表按钮：高度与内边距略大一号
  static double get actionButtonHeightInToolbar => 38.0;

  /// AppBar 内发表按钮：垂直内边距
  static double get actionButtonPaddingVerticalInToolbar => 6.0;

  /// AppBar 内发表按钮：水平内边距
  static double get actionButtonPaddingHorizontalInToolbar => 16.0;

  /// AppBar 内发表按钮：文字字号
  static double get actionButtonTextSizeInToolbar => AppTypography.sm;

  // ==================== 选择页 / 浮层统一语义 ====================
  /// 选择页工具栏背景，和设置/发布场景保持同一层级。
  static Color selectionToolbarBackground(bool isDark) =>
      createPageBlockBackground(isDark);

  /// 选择页搜索框底色，浅色偏中性灰，深色抬高一层表面。
  static Color selectionSearchBackground(bool isDark) =>
      AppColorsFunctional.getColor(isDark, ColorType.surfaceMuted);

  /// 选择页右侧箭头/辅助图标颜色。
  static Color selectionChevronColor(bool isDark) => secondaryColor(isDark);

  /// 选择页卡片圆角，相比设置页略大，接近全局弹层视觉。
  static double get selectionCardBorderRadius => AppSpacing.largeBorderRadius;

  /// 选择页卡片内行最小高度，保证触控与视觉留白一致。
  static double get selectionRowMinHeight => 56.0;

  /// 已选头像上的移除按钮背景。
  static Color selectionAvatarAccessoryBackground(bool isDark) =>
      blockBackground(isDark);

  /// 已选头像上的移除按钮描边。
  static Color selectionAvatarAccessoryBorder(bool isDark) =>
      dividerColor(isDark);

  /// 已选头像上的移除按钮图标色，保持低强调。
  static Color selectionAvatarAccessoryForeground(bool isDark) =>
      secondaryColor(isDark);

  // ==================== 工具栏高度（业界设计） ====================
  /// 顶部 AppBar 高度（含分割线）
  static double get appBarHeight => 56.0;

  /// 键盘之上工具栏高度（emoji 等入口，紧凑）
  static double get toolbarHeightOverKeyboard => 44.0;

  /// 固定底部 Tab 栏高度（微趣/美图/视频/文章）
  static double get toolbarHeightFixed => 48.0;

  /// 工具栏与下方面板间距（键盘之上工具栏 ↔ emoji 面板）
  static double get toolbarToPanelSpacing => 0;

  /// emoji 面板高度（与系统键盘同高，便于切换体验一致）
  static double get emojiPanelHeight => 280.0;

  /// emoji Tab 左右内边距（与 blockHorizontalPadding 或更紧凑）
  static double get emojiTabPaddingHorizontal =>
      AppSpacing.semantic[DesignSemanticConstants
          .container]?[DesignSemanticConstants.sm] ??
      AppSpacing.containerSm;

  /// emoji Tab 上下内边距
  static double get emojiTabPaddingVertical => AppSpacing.xs;

  /// emoji Tab 之间水平间距（胶囊之间更疏朗）
  static double get emojiTabSpacing =>
      AppSpacing.semantic[DesignSemanticConstants
          .intraGroup]?[DesignSemanticConstants.md] ??
      AppSpacing.intraGroupMd;

  /// emoji Tab 胶囊圆角
  static double get emojiTabCapsuleRadius => 16.0;

  /// emoji Tab 胶囊选中态背景透明度
  static double get emojiTabCapsuleSelectedAlpha => 0.12;

  /// emoji Tab 栏高度（适当降低，与工具栏统一语义）
  static double get emojiTabBarHeight => 40.0;

  /// emoji 网格：横向/纵向间距一致（组内间距 sm）
  static double get emojiGridSpacing =>
      AppSpacing.semantic[DesignSemanticConstants
          .intraGroup]?[DesignSemanticConstants.sm] ??
      AppSpacing.intraGroupSm;

  /// emoji 分类区块标题行高（紧凑，与网格无空行）
  static double get emojiSectionTitleHeight =>
      AppSpacing.semantic[DesignSemanticConstants
          .intraGroup]?[DesignSemanticConstants.lg] ??
      AppSpacing.intraGroupLg;

  /// emoji 分类之间垂直间距（0，分类间无空行）
  static double get emojiSectionGap => 0.0;

  /// emoji 图标字体大小（适当降低以减小单格高度）
  static double get emojiIconFontSize => 26.0;

  /// 创作时键盘上工具栏图标尺寸（与 emoji 入口统一）
  static double get createToolbarIconSize => AppSpacing.iconMedium;

  /// 创作时键盘上工具栏上下内边距
  static double get createToolbarPaddingVertical => AppSpacing.xs;
}
