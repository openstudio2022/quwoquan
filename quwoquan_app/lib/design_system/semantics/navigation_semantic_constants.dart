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
  /// Product-level accessibility identity for the canonical home surface.
  ///
  /// Flutter projects this value to Android's view resource name and iOS's
  /// accessibility identifier. External accessibility clients can therefore
  /// prove that the already-running production App reached the home surface
  /// without depending on test-only widget keys or translated copy.
  static const String homeSurfaceIdentifier = 'qwq.surface.home';

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
  /// - `immersive`：透明——沉浸导航钮不使用暗色圆底或毛玻璃（REQ-019），
  ///   浅色媒体上的可见性由 [chromeActionIconShadows] 的柔和投影承接。
  ///   相机取景壳等**操作钮**是独立语义，需要暗底时由调用方显式声明，
  ///   不走本导航语义。
  /// - `overlay`：封面壳保持透明——其前景色已随封面亮度自适应
  ///   （见 profile/circle shell 的 compactForeground），不叠加圆底避免漂移。
  /// - `standard`：透明。
  static Color chromeActionBackground({
    AppChromeSurface surface = AppChromeSurface.standard,
  }) {
    switch (surface) {
      case AppChromeSurface.immersive:
      case AppChromeSurface.overlay:
      case AppChromeSurface.standard:
        return AppColors.transparent;
    }
  }

  /// 应用 chrome 操作图标投影：沉浸面白色图标的唯一可见性保护。
  ///
  /// 双层投影：近距细投影提供图标轮廓对比，远距柔投影在雪山/白云等
  /// 浅色媒体与失败面浅背景上衬出图标，返回出路永不消失。
  /// standard/overlay 表面不加投影。
  static List<Shadow> chromeActionIconShadows({
    AppChromeSurface surface = AppChromeSurface.standard,
  }) {
    switch (surface) {
      case AppChromeSurface.immersive:
        return <Shadow>[
          Shadow(
            color: AppColors.black.withValues(alpha: 0.55),
            offset: const Offset(0, AppSpacing.one),
            blurRadius: AppSpacing.two,
          ),
          Shadow(
            color: AppColors.black.withValues(alpha: 0.35),
            blurRadius: AppSpacing.sm,
          ),
        ];
      case AppChromeSurface.overlay:
      case AppChromeSurface.standard:
        return const <Shadow>[];
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
