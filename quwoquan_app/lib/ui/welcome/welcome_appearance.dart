import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

/// 欢迎页品牌渐变、装饰光斑与水滴等视觉 token（随深浅色切换）。
class WelcomeAppearance {
  WelcomeAppearance._(this.isDark);

  final bool isDark;

  static WelcomeAppearance of(BuildContext context) {
    final dark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    return WelcomeAppearance._(dark);
  }

  Color get background =>
      isDark ? AppColors.welcomeBackgroundDark : AppColors.welcomeBackground;

  Color get gradientStart => isDark
      ? AppColors.welcomeGradientStartDark
      : AppColors.welcomeGradientStart;

  Color get gradientEnd => isDark
      ? AppColors.welcomeGradientEndDark
      : AppColors.welcomeGradientEnd;

  Color get foregroundMuted => isDark
      ? AppColors.welcomeForegroundMutedDark
      : AppColors.welcomeForegroundMuted;

  Color get buttonBackground =>
      isDark ? AppColors.welcomeButtonBgDark : AppColors.welcomeButtonBg;

  /// 背景大光斑填充
  Color get decorSoftBlobFill =>
      AppColors.white.withValues(alpha: 0.05);

  /// 背景大光斑外晕
  Color get decorSoftBlobShadow =>
      AppColors.black.withValues(alpha: 0.1);

  /// 花瓣投影
  Color get petalShadow =>
      AppColors.black.withValues(alpha: 0.2);

  /// 水滴径向渐变（高 → 低）
  List<Color> get dropRadialColors => [
        AppColors.white.withValues(alpha: 0.4),
        AppColors.white.withValues(alpha: 0.1),
        AppColors.white.withValues(alpha: 0.02),
      ];

  Color get dropBorder =>
      AppColors.white.withValues(alpha: isDark ? 0.14 : 0.1);

  Color get dropHighlightGlow =>
      AppColors.white.withValues(alpha: isDark ? 0.35 : 0.2);

  Color get dropDepthShadow =>
      AppColors.black.withValues(alpha: isDark ? 0.35 : 0.1);

  /// ShaderMask 子树占位色（实际由 shader 着色）
  Color get shaderMaskChildBase => AppColors.white;

  /// 倒计时角标数字
  Color get countdownDigit =>
      AppColors.welcomeForeground.withValues(alpha: 0.9);

  static const List<Color> petalColors = [
    AppColors.welcomePetalOrange,
    AppColors.welcomePetalYellow,
    AppColors.welcomePetalLime,
    AppColors.welcomePetalEmerald,
    AppColors.welcomePetalCyan,
    AppColors.welcomePetalSky,
    AppColors.welcomePetalPurple,
    AppColors.welcomePetalRose,
  ];
}
