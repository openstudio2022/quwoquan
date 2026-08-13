import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

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

  /// 应用 chrome 操作按钮背景。
  ///
  /// - `immersive`：半透明暗色圆底（iOS Photos 沉浸惯例），保证媒体加载失败
  ///   退到浅色背景时白色返回/操作图标仍然可见，用户不会被困在失败页。
  /// - `overlay`：封面壳保持透明——其前景色已随封面亮度自适应
  ///   （见 profile/circle shell 的 compactForeground），不叠加圆底避免漂移。
  /// - `standard`：透明。
  static Color chromeActionBackground({
    AppChromeSurface surface = AppChromeSurface.standard,
  }) {
    switch (surface) {
      case AppChromeSurface.immersive:
        return AppColors.overlayLight;
      case AppChromeSurface.overlay:
      case AppChromeSurface.standard:
        return AppColors.transparent;
    }
  }

  /// 设置入口使用业界通用齿轮图标语义。
  static const IconData settingsActionIcon = CupertinoIcons.gear;

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
