import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

enum AppChromeSurface { standard, immersive, overlay }

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

  /// 应用 chrome 操作图标色：沉浸/封面层固定白色，普通页面使用导航语义色。
  static Color chromeActionIconColor(
    bool isDark, {
    AppChromeSurface surface = AppChromeSurface.standard,
  }) {
    switch (surface) {
      case AppChromeSurface.immersive:
      case AppChromeSurface.overlay:
        return AppColors.white;
      case AppChromeSurface.standard:
        return barIconColor(isDark);
    }
  }

  /// 应用 chrome 操作按钮背景。当前统一为透明，避免资料页/圈子页半透明圆底漂移。
  static Color chromeActionBackground({
    AppChromeSurface surface = AppChromeSurface.standard,
  }) => AppColors.transparent;

  /// 设置入口统一使用更疏朗的 iOS 滑杆语义，替代密集齿轮。
  static const IconData settingsActionIcon = CupertinoIcons.slider_horizontal_3;

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
