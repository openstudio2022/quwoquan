import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

/// 欢迎页品牌渐变、装饰光斑与花瓣等视觉 token（随深浅色切换）。
class WelcomeAppearance {
  WelcomeAppearance._(this.isDark, {this.vivid = false});

  final bool isDark;

  /// 鲜艳品牌外观：花瓣满不透明、饱和，用于浅底登录页 hero（贴合高保与应用图标）。
  /// 欢迎页/启动图标走默认（vivid=false），不受影响。
  final bool vivid;

  /// 是否深色主题（用于下层 bloom 等局部调色）。
  bool get isDarkTheme => isDark;

  static WelcomeAppearance of(BuildContext context) {
    final dark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return WelcomeAppearance._(dark);
  }

  /// 登录页等浅底场景使用的鲜艳花瓣品牌外观。
  static WelcomeAppearance brandMark() =>
      WelcomeAppearance._(false, vivid: true);

  Color get background =>
      isDark ? AppColors.welcomeBackgroundDark : AppColors.welcomeBackground;

  Color get gradientStart => isDark
      ? AppColors.welcomeGradientStartDark
      : AppColors.welcomeGradientStart;

  Color get gradientEnd =>
      isDark ? AppColors.welcomeGradientEndDark : AppColors.welcomeGradientEnd;

  Color get foregroundMuted => isDark
      ? AppColors.welcomeForegroundMutedDark
      : AppColors.welcomeForegroundMuted;

  Color get buttonBackground =>
      isDark ? AppColors.welcomeButtonBgDark : AppColors.welcomeButtonBg;

  /// 背景大光斑填充
  Color get decorSoftBlobFill => AppColors.white.withValues(alpha: 0.05);

  /// 背景大光斑外晕
  Color get decorSoftBlobShadow => AppColors.black.withValues(alpha: 0.1);

  /// 花瓣投影（压低 alpha，减轻「闷」感）。
  Color get petalShadow =>
      AppColors.black.withValues(alpha: isDark ? 0.095 : 0.055);

  /// 花瓣最终透明度：略抬亮外缘，强化「绽放」感。鲜艳品牌外观满不透明。
  double get petalOpacity => vivid
      ? 1.0
      : isDark
      ? 0.82
      : 0.86;

  /// 花瓣根部混光：花心叠片区须偏亮，减轻多片半透明叠在深蓝底上的暗沉。
  Color get petalRootTint => Color.alphaBlend(
    AppColors.white.withValues(alpha: isDark ? 0.58 : 0.52),
    AppColors.welcomeForegroundMuted.withValues(alpha: isDark ? 0.28 : 0.22),
  );

  /// 花瓣根部 cyan 高光：与标题渐变 mid 同源，增强花心通透。
  Color get petalRootGlow =>
      AppColors.welcomeTitleGradientMid.withValues(alpha: isDark ? 0.34 : 0.28);

  /// 花瓣下层径向柔光（羽化至透明）：提亮花心负空间，非独立「光圈」图层。
  RadialGradient get bloomPlateGradient => RadialGradient(
    colors: [
      AppColors.white.withValues(alpha: isDark ? 0.26 : 0.20),
      AppColors.welcomeTitleGradientMid.withValues(alpha: isDark ? 0.13 : 0.10),
      AppColors.transparent,
    ],
    stops: const [0.0, 0.44, 1.0],
  );

  /// 花瓣上层花蕊柔光；只使用品牌蓝与白，保证小尺寸图标仍可辨认。
  RadialGradient get stamenHaloGradient => RadialGradient(
    colors: [
      AppColors.white.withValues(alpha: isDark ? 0.82 : 0.88),
      AppColors.welcomeTitleGradientMid.withValues(alpha: isDark ? 0.44 : 0.38),
      AppColors.transparent,
    ],
    stops: const [0.0, 0.45, 1.0],
  );

  RadialGradient get stamenCoreGradient => RadialGradient(
    colors: [
      AppColors.white,
      Color.alphaBlend(
        AppColors.welcomeTitleGradientMid.withValues(alpha: 0.28),
        AppColors.white,
      ),
    ],
  );

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
