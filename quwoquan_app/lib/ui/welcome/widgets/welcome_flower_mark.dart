import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';

/// 欢迎页与应用图标共用的花瓣标识。
///
/// 后续花瓣路径、花蕊、渐变或 bloom 调整都应在这里完成，再重新生成图标，
/// 避免欢迎页与 launcher icon 产生两套视觉。
class WelcomeFlowerMark extends StatelessWidget {
  const WelcomeFlowerMark({
    super.key,
    required this.appearance,
    this.petalProgresses = const [1, 1, 1, 1, 1, 1, 1, 1],
  });

  final WelcomeAppearance appearance;
  final List<double> petalProgresses;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: WelcomeFlowerMarkPainter(
        appearance: appearance,
        petalProgresses: petalProgresses,
      ),
      size: const Size.square(AppSpacing.welcomeGraphicDiameter),
    );
  }
}

class WelcomeFlowerMarkPainter extends CustomPainter {
  const WelcomeFlowerMarkPainter({
    required this.appearance,
    required this.petalProgresses,
    this.graphicExtent = AppSpacing.welcomeGraphicDiameter,
  });

  static const int petalCount = 8;
  static const double flowerVisualDiameter =
      (AppSpacing.welcomePetalRadialOffset +
          AppSpacing.welcomePetalHeight / 2) *
      2;
  static const List<double> petalRotations = [
    0,
    45,
    90,
    135,
    180,
    225,
    270,
    315,
  ];

  final WelcomeAppearance appearance;
  final List<double> petalProgresses;
  final double graphicExtent;

  @override
  void paint(Canvas canvas, Size size) {
    final scale = size.shortestSide / graphicExtent;
    paintFlower(
      canvas,
      center: Offset(size.width / 2, size.height / 2),
      scale: scale,
      appearance: appearance,
      petalProgresses: petalProgresses,
    );
  }

  static void paintFlower(
    Canvas canvas, {
    required Offset center,
    required double scale,
    required WelcomeAppearance appearance,
    required List<double> petalProgresses,
  }) {
    _paintBloomPlate(canvas, center, scale, appearance);
    for (var i = 0; i < petalCount; i++) {
      final rawProgress = i < petalProgresses.length ? petalProgresses[i] : 1.0;
      final progress = Curves.easeOutCubic.transform(
        rawProgress.clamp(0.0, 1.0),
      );
      if (progress <= 0) continue;
      _paintPetal(canvas, center, scale, appearance, i, progress);
    }
  }

  static Path petalPath(Size size) {
    final w = size.width;
    final h = size.height;
    final cx = w / 2;

    return Path()
      ..moveTo(cx, 0)
      ..cubicTo(w * 0.82, 0, w, h * 0.16, w * 0.96, h * 0.34)
      ..cubicTo(w * 0.92, h * 0.54, w * 0.70, h * 0.74, w * 0.61, h * 0.92)
      ..cubicTo(w * 0.56, h, w * 0.44, h, w * 0.39, h * 0.92)
      ..cubicTo(w * 0.30, h * 0.74, w * 0.08, h * 0.54, w * 0.04, h * 0.34)
      ..cubicTo(0, h * 0.16, w * 0.18, 0, cx, 0)
      ..close();
  }

  static void _paintBloomPlate(
    Canvas canvas,
    Offset center,
    double scale,
    WelcomeAppearance appearance,
  ) {
    final radius = AppSpacing.welcomeBloomDiameter * scale / 2;
    final rect = Rect.fromCircle(center: center, radius: radius);
    final paint = Paint()
      ..shader = appearance.bloomPlateGradient.createShader(rect);
    canvas.drawCircle(center, radius, paint);
  }

  static void _paintPetal(
    Canvas canvas,
    Offset center,
    double scale,
    WelcomeAppearance appearance,
    int index,
    double progress,
  ) {
    final petalSize = Size(
      AppSpacing.welcomePetalWidth * scale,
      AppSpacing.welcomePetalHeight * scale,
    );
    final path = petalPath(petalSize);
    final petalRect = Offset.zero & petalSize;
    final opacity = progress * appearance.petalOpacity;
    final rotation = petalRotations[index] * math.pi / 180;

    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(rotation);
    canvas.scale(progress);
    canvas.translate(
      -petalSize.width / 2,
      -AppSpacing.welcomePetalRadialOffset * scale - petalSize.height / 2,
    );

    canvas.save();
    canvas.translate(0, AppSpacing.two * scale);
    canvas.drawPath(
      path,
      Paint()
        ..color = _withMultipliedAlpha(appearance.petalShadow, progress)
        ..maskFilter = MaskFilter.blur(BlurStyle.normal, AppSpacing.xs * scale),
    );
    canvas.restore();

    final baseColor = WelcomeAppearance.petalColors[index];
    final paint = Paint()
      ..shader =
          (appearance.vivid
                  ? LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        _withMultipliedAlpha(
                          Color.lerp(baseColor, AppColors.white, 0.04) ??
                              baseColor,
                          opacity,
                        ),
                        _withMultipliedAlpha(baseColor, opacity),
                        _withMultipliedAlpha(
                          Color.lerp(baseColor, AppColors.white, 0.20) ??
                              baseColor,
                          opacity,
                        ),
                        _withMultipliedAlpha(
                          Color.lerp(baseColor, AppColors.white, 0.55) ??
                              baseColor,
                          opacity,
                        ),
                      ],
                      stops: const [0.0, 0.5, 0.82, 1.0],
                    )
                  : LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        _withMultipliedAlpha(
                          Color.lerp(
                                baseColor,
                                AppColors.white,
                                appearance.isDarkTheme ? 0.07 : 0.09,
                              ) ??
                              baseColor,
                          opacity,
                        ),
                        _withMultipliedAlpha(
                          baseColor.withValues(alpha: 0.78),
                          opacity,
                        ),
                        _withMultipliedAlpha(appearance.petalRootGlow, opacity),
                        _withMultipliedAlpha(appearance.petalRootTint, opacity),
                      ],
                      stops: const [0.0, 0.52, 0.78, 1.0],
                    ))
              .createShader(petalRect);
    canvas.drawPath(path, paint);
    canvas.restore();
  }

  static Color _withMultipliedAlpha(Color color, double multiplier) {
    return color.withValues(alpha: color.a * multiplier);
  }

  @override
  bool shouldRepaint(covariant WelcomeFlowerMarkPainter oldDelegate) {
    if (oldDelegate.appearance != appearance ||
        oldDelegate.graphicExtent != graphicExtent ||
        oldDelegate.petalProgresses.length != petalProgresses.length) {
      return true;
    }
    for (var i = 0; i < petalProgresses.length; i++) {
      if (oldDelegate.petalProgresses[i] != petalProgresses[i]) {
        return true;
      }
    }
    return false;
  }
}

class WelcomeAppIconPainter extends CustomPainter {
  const WelcomeAppIconPainter({
    required this.appearance,
    this.flowerDiameterRatio = 0.75,
  });

  final WelcomeAppearance appearance;

  /// 花瓣视觉外接圆占图标画布比例。0.75 表示 1024 图中花瓣约 768px，
  /// 四边各留约 128px 呼吸空间。
  final double flowerDiameterRatio;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    canvas.drawRect(
      rect,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            appearance.gradientStart,
            appearance.background,
            appearance.gradientEnd,
          ],
        ).createShader(rect),
    );

    final targetDiameter = size.shortestSide * flowerDiameterRatio;
    final scale =
        targetDiameter / WelcomeFlowerMarkPainter.flowerVisualDiameter;
    WelcomeFlowerMarkPainter.paintFlower(
      canvas,
      center: Offset(size.width / 2, size.height / 2),
      scale: scale,
      appearance: appearance,
      petalProgresses: const [1, 1, 1, 1, 1, 1, 1, 1],
    );
  }

  @override
  bool shouldRepaint(covariant WelcomeAppIconPainter oldDelegate) {
    return oldDelegate.appearance != appearance ||
        oldDelegate.flowerDiameterRatio != flowerDiameterRatio;
  }
}
