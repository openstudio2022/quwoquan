import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

/// 圈子频道管理页的视觉语义。
class CircleChannelManageStyle {
  CircleChannelManageStyle._();

  /// 顶部抽屉表面背景，使用 grouped surface 而非纯白卡片。
  static Color panelBackground(bool isDark) =>
      SettingsSemanticConstants.conversationSheetPanelBackground(isDark);

  /// 顶部抽屉背景遮罩，保留下层轮廓但不过度压暗。
  static Color backdropColor(bool isDark) => AppColorsFunctional.getColor(
    isDark,
    ColorType.modalScrim,
  ).withValues(alpha: isDark ? 0.04 : 0.02);

  /// 顶部抽屉背景模糊强度，轻度虚化但保留底部 tab 与 post 轮廓。
  static double backdropBlurSigma(BuildContext context) =>
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.two,
        regular: AppSpacing.two,
        expanded: AppSpacing.two,
      );

  /// 频道 chip 表面色。
  static Color chipSurface(bool isDark, bool canRemove) => canRemove
      ? SettingsSemanticConstants.conversationSheetCardSurface(isDark)
      : SettingsSemanticConstants.createAddTileBackground(isDark);

  /// 频道 chip 边框色，iPad 上要更可见。
  static Color chipBorderColor(bool isDark, bool canRemove) {
    final base = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorOpaque,
    );
    return base.withValues(
      alpha: isDark ? (canRemove ? 0.32 : 0.4) : (canRemove ? 0.24 : 0.28),
    );
  }

  /// chip 圆角。
  static double get chipCornerRadius =>
      SettingsSemanticConstants.conversationSheetCardCornerRadius;

  /// chip 内容左右内边距，随卡片宽度拉开。
  static double chipHorizontalPadding(double tileWidth) {
    if (tileWidth >= 190) return AppSpacing.containerMd;
    if (tileWidth >= 150) return AppSpacing.containerSm + AppSpacing.two;
    return AppSpacing.containerSm;
  }

  /// chip 内容上下内边距，随卡片宽度略微放大。
  static double chipVerticalPadding(double tileWidth) {
    if (tileWidth >= 190) return AppSpacing.containerSm;
    if (tileWidth >= 150) return AppSpacing.ten;
    return AppSpacing.six;
  }

  /// add chip 的 icon 与文字间距。
  static double chipIconLabelGap(double tileWidth) {
    if (tileWidth >= 190) return AppSpacing.ten;
    if (tileWidth >= 150) return AppSpacing.six + AppSpacing.two;
    return AppSpacing.six;
  }

  /// add chip 的图标尺寸，平板上更显眼一些。
  static double addChipIconSize(double tileWidth) {
    if (tileWidth >= 190) return AppSpacing.iconMedium;
    return AppSpacing.twenty;
  }
}
