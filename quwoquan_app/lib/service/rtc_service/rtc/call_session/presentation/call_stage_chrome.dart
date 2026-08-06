import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';

/// 来电/去电与语音通话主舞台：背景渐变与叠在渐变上的前景色。
///
/// 与 [ColorType.callStageGradientStart] / [ColorType.callStageGradientEnd] 一致。
abstract final class CallStageChrome {
  static List<Color> backgroundGradient(bool isDark) => [
    AppColorsFunctional.getColor(isDark, ColorType.callStageGradientStart),
    AppColorsFunctional.getColor(isDark, ColorType.callStageGradientEnd),
  ];

  /// 渐变上的主文案使用 RTC 自有前景色，不依赖 welcome 品牌调色。
  static Color primaryOnGradient(bool isDark) => AppColors.callStageForeground;

  static Color secondaryOnGradient(bool isDark) =>
      primaryOnGradient(isDark).withValues(alpha: 0.7);

  static Color timerOnGradient(bool isDark) =>
      AppColors.callStageForeground.withValues(alpha: 0.5);
}
