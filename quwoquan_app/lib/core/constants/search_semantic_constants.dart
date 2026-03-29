import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 搜索输入统一语义 token。
///
/// 覆盖全局搜索、页面内嵌搜索、选择器搜索等场景，确保浅色/深色下
/// 具备一致的留白、对比度与 iOS 质感。
class SearchSemanticConstants {
  SearchSemanticConstants._();

  static double get fieldBorderRadius => AppSpacing.radiusTwenty;

  static double get fieldIconSize => AppSpacing.twenty;

  static EdgeInsets get fieldContentPadding => const EdgeInsets.symmetric(
    horizontal: AppSpacing.containerSm,
    vertical: AppSpacing.ten,
  );

  static TextStyle inputTextStyle(BuildContext context) => TextStyle(
    fontSize: AppTypography.iosBody,
    fontWeight: FontWeight.w400,
    height: AppSpacing.textLineHeightDense,
    color: AppColors.iosLabel(context),
  );

  static TextStyle placeholderTextStyle(BuildContext context) =>
      inputTextStyle(context).copyWith(
        color: AppColors.iosSecondaryLabel(context).withValues(alpha: 0.96),
      );

  static Color backgroundColor(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return isDark
        ? AppColors.iosGroupedSurfaceElevated(context).withValues(alpha: 0.94)
        : AppColors.iosSystemBackground(context).withValues(alpha: 0.98);
  }

  static Color borderColor(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return AppColors.iosOpaqueSeparator(
      context,
    ).withValues(alpha: isDark ? 0.28 : 0.08);
  }

  static List<BoxShadow> shadows(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    if (isDark) {
      return const <BoxShadow>[];
    }
    return <BoxShadow>[
      BoxShadow(
        color: AppColors.black.withValues(alpha: 0.035),
        blurRadius: AppSpacing.eighteen,
        offset: const Offset(0, 8),
      ),
    ];
  }

  static Color iconColor(BuildContext context) =>
      AppColors.iosTertiaryLabel(context);

  // ==================== 嵌入式成员搜索（全屏 / 顶栏下条）====================

  /// 全屏成员搜索页主背景（与 Inset Grouped 表单灰底一致）。
  static Color embeddedMemberSearchPageBackground(bool isDark) =>
      SettingsSemanticConstants.insetFormPageBackground(isDark);

  /// 搜索条区域灰带背景（顶栏下或独立页首条）。
  static Color embeddedMemberSearchChromeBackground(bool isDark) =>
      AppColorsFunctional.getColor(isDark, ColorType.surfaceMuted);

  /// 「取消」等次要操作文字色（主标签色，非强调蓝）。
  static Color embeddedMemberSearchActionLabelColor(bool isDark) =>
      AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);

  /// 内嵌「选人群」搜索条里，已选成员头像边长（置于输入框内，小于列表行头像）。
  static double get embeddedMemberSearchChipAvatarSize =>
      AppSpacing.largeButtonSize * 0.72;

  /// 选人头 + 搜索框容器因换行/增删选中项时的尺寸过渡。
  static Duration get embeddedMemberSearchChipsLayoutDuration =>
      const Duration(milliseconds: 220);

  static Curve get embeddedMemberSearchChipsLayoutCurve =>
      Curves.easeInOutCubic;

  /// 与 [embeddedMemberSearchChipAvatarSize] 对齐的输入区最小高度（含行内对齐）。
  static double get embeddedMemberSearchChipsRowMinHeight =>
      embeddedMemberSearchChipAvatarSize + AppSpacing.xs;

  /// 「选人群」芯片条内联输入：占位比 [placeholderTextStyle] 更淡（深浅色均用 tertiary）。
  static TextStyle embeddedMemberSearchChipsPlaceholderStyle(
    BuildContext context,
  ) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return inputTextStyle(context).copyWith(
      color: AppColors.iosTertiaryLabel(context).withValues(
        alpha: isDark ? 0.88 : 0.72,
      ),
    );
  }

  /// 与头像同一行时，输入槽最小宽度（约「搜索」二字 + 内边距）；仅当行剩余小于此值时才整段换行。
  static const double embeddedMemberSearchChipsInlineInputMinWidth = 48.0;
}
