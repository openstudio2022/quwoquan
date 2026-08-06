import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_appearance.dart';

/// 欢迎页与应用图标共用的花瓣标识。
///
/// 花瓣 `bloomAmount` 语义为「绽放度」：0 = 历史花苞态、1 = 全开。
/// 花瓣始终保持原始宽高比，只做以花心为原点的同比例二维缩放；尺寸、透明度
/// 与花瓣中心半径同步增长，形成从花心向外舒展的逐瓣开放感。
///
/// 后续花瓣路径、花蕊、渐变或 bloom 调整都应在这里完成，再重新生成图标，
/// 避免欢迎页与 launcher icon 产生两套视觉。
class WelcomeFlowerMark extends StatelessWidget {
  const WelcomeFlowerMark({
    super.key,
    required this.appearance,
    this.petalBloomAmounts = const [1, 1, 1, 1, 1, 1, 1, 1],
  });

  final WelcomeAppearance appearance;
  final List<double> petalBloomAmounts;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: WelcomeFlowerMarkPainter(
        appearance: appearance,
        petalBloomAmounts: petalBloomAmounts,
      ),
      size: const Size.square(AppSpacing.welcomeGraphicDiameter),
    );
  }
}

class WelcomeFlowerMarkPainter extends CustomPainter {
  const WelcomeFlowerMarkPainter({
    required this.appearance,
    required this.petalBloomAmounts,
    this.graphicExtent = AppSpacing.welcomeGraphicDiameter,
  });

  static const int petalCount = 8;
  static const double historicalBudVisualFactor = 0.561024;
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
  final List<double> petalBloomAmounts;
  final double graphicExtent;

  static double visualFactorFor(double bloomAmount) {
    return historicalBudVisualFactor +
        (1 - historicalBudVisualFactor) * bloomAmount.clamp(0.0, 1.0);
  }

  static WelcomePetalGeometry geometryFor({
    required double bloomAmount,
    double scale = 1,
  }) {
    final visualFactor = visualFactorFor(bloomAmount);
    return WelcomePetalGeometry(
      visualFactor: visualFactor,
      size: Size(
        AppSpacing.welcomePetalWidth * scale * visualFactor,
        AppSpacing.welcomePetalHeight * scale * visualFactor,
      ),
      centerRadius: AppSpacing.welcomePetalRadialOffset * scale * visualFactor,
    );
  }

  @override
  void paint(Canvas canvas, Size size) {
    final scale = size.shortestSide / graphicExtent;
    paintFlower(
      canvas,
      center: Offset(size.width / 2, size.height / 2),
      scale: scale,
      appearance: appearance,
      petalBloomAmounts: petalBloomAmounts,
    );
  }

  static void paintFlower(
    Canvas canvas, {
    required Offset center,
    required double scale,
    required WelcomeAppearance appearance,
    required List<double> petalBloomAmounts,
  }) {
    _paintBloomPlate(canvas, center, scale, appearance);
    for (var i = 0; i < petalCount; i++) {
      final bloomAmount = i < petalBloomAmounts.length
          ? petalBloomAmounts[i].clamp(0.0, 1.0)
          : 1.0;
      _paintPetal(canvas, center, scale, appearance, i, bloomAmount);
    }
    _paintStamen(canvas, center, scale, appearance);
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
    double bloomAmount,
  ) {
    final petalSize = Size(
      AppSpacing.welcomePetalWidth * scale,
      AppSpacing.welcomePetalHeight * scale,
    );
    final path = petalPath(petalSize);
    final petalRect = Offset.zero & petalSize;
    final visualFactor = visualFactorFor(bloomAmount);
    final opacity = visualFactor * appearance.petalOpacity;
    final rotation = petalRotations[index] * math.pi / 180;

    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(rotation);
    if (visualFactor < 1) {
      canvas.scale(visualFactor);
    }
    canvas.translate(
      -petalSize.width / 2,
      -AppSpacing.welcomePetalRadialOffset * scale - petalSize.height / 2,
    );

    canvas.save();
    canvas.translate(0, AppSpacing.two * scale);
    canvas.drawPath(
      path,
      Paint()
        ..color = _withMultipliedAlpha(appearance.petalShadow, visualFactor)
        ..maskFilter = MaskFilter.blur(BlurStyle.normal, AppSpacing.xs * scale),
    );
    canvas.restore();

    final baseColor = WelcomeAppearance.petalColors[index];
    final paint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          _withMultipliedAlpha(
            Color.lerp(baseColor, AppColors.white, 0.04) ?? baseColor,
            opacity,
          ),
          _withMultipliedAlpha(baseColor, opacity),
          _withMultipliedAlpha(
            Color.lerp(baseColor, AppColors.white, 0.20) ?? baseColor,
            opacity,
          ),
          _withMultipliedAlpha(
            Color.lerp(baseColor, AppColors.white, 0.55) ?? baseColor,
            opacity,
          ),
        ],
        stops: const [0.0, 0.5, 0.82, 1.0],
      ).createShader(petalRect);
    canvas.drawPath(path, paint);
    canvas.restore();
  }

  static void _paintStamen(
    Canvas canvas,
    Offset center,
    double scale,
    WelcomeAppearance appearance,
  ) {
    final haloRadius = AppSpacing.welcomeStamenHaloDiameter * scale / 2;
    final haloRect = Rect.fromCircle(center: center, radius: haloRadius);
    canvas.drawCircle(
      center,
      haloRadius,
      Paint()..shader = appearance.stamenHaloGradient.createShader(haloRect),
    );

    final coreRadius = AppSpacing.welcomeStamenCoreDiameter * scale / 2;
    final coreRect = Rect.fromCircle(center: center, radius: coreRadius);
    canvas.drawCircle(
      center,
      coreRadius,
      Paint()..shader = appearance.stamenCoreGradient.createShader(coreRect),
    );
  }

  static Color _withMultipliedAlpha(Color color, double multiplier) {
    return color.withValues(alpha: color.a * multiplier);
  }

  @override
  bool shouldRepaint(covariant WelcomeFlowerMarkPainter oldDelegate) {
    if (oldDelegate.appearance != appearance ||
        oldDelegate.graphicExtent != graphicExtent ||
        oldDelegate.petalBloomAmounts.length != petalBloomAmounts.length) {
      return true;
    }
    for (var i = 0; i < petalBloomAmounts.length; i++) {
      if (oldDelegate.petalBloomAmounts[i] != petalBloomAmounts[i]) {
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
      petalBloomAmounts: const [1, 1, 1, 1, 1, 1, 1, 1],
    );
  }

  @override
  bool shouldRepaint(covariant WelcomeAppIconPainter oldDelegate) {
    return oldDelegate.appearance != appearance ||
        oldDelegate.flowerDiameterRatio != flowerDiameterRatio;
  }
}

@immutable
class WelcomePetalGeometry {
  const WelcomePetalGeometry({
    required this.visualFactor,
    required this.size,
    required this.centerRadius,
  });

  final double visualFactor;
  final Size size;
  final double centerRadius;
}
