import 'package:flutter/cupertino.dart';
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
}
