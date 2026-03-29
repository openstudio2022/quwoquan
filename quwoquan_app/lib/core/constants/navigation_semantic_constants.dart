import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// [AppNavigationBar] / 全屏顶栏：返回与「更多」等图标、中间标题的唯一语义（与聊天信息页 Inset 表单顶栏对齐）。
///
/// 图标使用主标签色，**禁止**默认 Cupertino 强调蓝；尺寸与 [AppNavigationBarIconButton] 一致。
class AppNavigationSemanticConstants {
  AppNavigationSemanticConstants._();

  /// 顶栏 leading/trailing 图标边长（与 [GlobalTopBarIconButton] 一致）。
  static double get barIconSize => AppSpacing.iconMedium;

  /// 返回、更多、搜索等顶栏操作图标色（非品牌蓝）。
  static Color barIconColor(bool isDark) =>
      SettingsSemanticConstants.insetFormNavigationBarActionIconColor(isDark);

  /// 顶栏标题字色。
  static Color barTitleColor(bool isDark) =>
      SettingsSemanticConstants.insetFormNavigationBarTitleColor(isDark);

  /// 顶栏中间标题：iOS 导航标准字号 + 半粗（全站 [AppNavigationBar] 统一）。
  static TextStyle barTitleTextStyle(bool isDark) => TextStyle(
        fontSize: AppTypography.iosNavTitle,
        fontWeight: AppTypography.semiBold,
        color: barTitleColor(isDark),
      );
}
