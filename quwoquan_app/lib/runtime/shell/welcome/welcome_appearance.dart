import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';

/// 欢迎页品牌渐变与花瓣视觉 token。
///
/// 品牌欢迎页在浅色与深色系统模式下保持同一套品牌深蓝，不跟随系统主题
/// 切换页面底色；原生启动图、应用图标与 Flutter 首帧因此天然同源。
class WelcomeAppearance {
  const WelcomeAppearance._();

  static const WelcomeAppearance _brand = WelcomeAppearance._();

  /// 欢迎页统一品牌外观；不读取主题亮度。
  static WelcomeAppearance of(BuildContext context) => _brand;

  /// 登录页品牌标与欢迎页、应用图标必须消费同一终态，禁止第二套调色。
  static WelcomeAppearance brandMark() => _brand;

  Color get background => AppColors.welcomeBackground;

  Color get gradientStart => AppColors.welcomeGradientStart;

  Color get gradientEnd => AppColors.welcomeGradientEnd;

  Color get foregroundMuted => AppColors.welcomeForegroundMuted;

  /// 花瓣投影（压低 alpha，减轻「闷」感）。
  Color get petalShadow => AppColors.black.withValues(alpha: 0.055);

  /// 图一终态花瓣保持高饱和全不透明，聚拢过程再由 visualFactor 统一衰减。
  double get petalOpacity => 1.0;

  /// 花瓣下层径向柔光（羽化至透明）：提亮花心负空间，非独立「光圈」图层。
  RadialGradient get bloomPlateGradient => RadialGradient(
    colors: [
      AppColors.white.withValues(alpha: 0.20),
      AppColors.welcomeTitleGradientMid.withValues(alpha: 0.10),
      AppColors.transparent,
    ],
    stops: const [0.0, 0.44, 1.0],
  );

  /// 花瓣上层花蕊柔光；只使用品牌蓝与白，保证小尺寸图标仍可辨认。
  RadialGradient get stamenHaloGradient => RadialGradient(
    colors: [
      AppColors.white.withValues(alpha: 0.88),
      AppColors.welcomeTitleGradientMid.withValues(alpha: 0.38),
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
