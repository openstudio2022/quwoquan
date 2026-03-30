import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

/// 来电/去电与语音通话主舞台：背景渐变与叠在渐变上的前景色。
///
/// 与 [ColorType.callStageGradientStart] / [ColorType.callStageGradientEnd] 一致。
abstract final class CallStageChrome {
  static List<Color> backgroundGradient(bool isDark) => [
        AppColorsFunctional.getColor(isDark, ColorType.callStageGradientStart),
        AppColorsFunctional.getColor(isDark, ColorType.callStageGradientEnd),
      ];

  /// 渐变上的主文案（等价于原 welcome 白字）
  static Color primaryOnGradient(bool isDark) =>
      AppColorsFunctional.getColor(
        isDark,
        ColorType.mediaThumbnailOverlayForeground,
      );

  static Color secondaryOnGradient(bool isDark) =>
      primaryOnGradient(isDark).withValues(alpha: 0.7);

  static Color timerOnGradient(bool isDark) =>
      AppColors.welcomeForeground.withValues(alpha: 0.5);
}
