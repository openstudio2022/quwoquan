import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

const String kEditorIconFadeBands = 'fadeBands';
const String kEditorIconHighlightRing = 'highlightRing';
const String kEditorIconShadowRing = 'shadowRing';
const String kEditorIconFilterRings = 'filterRings';
const String kEditorIconHslSolid = 'hslSolid';
const String kEditorIconBwLevels = 'bwLevels';

class ImageEditorSemanticIcon extends StatelessWidget {
  const ImageEditorSemanticIcon({
    super.key,
    required this.iconKey,
    required this.size,
    required this.color,
  });

  final String iconKey;
  final double size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    switch (iconKey) {
      case kEditorIconFadeBands:
        return CustomPaint(
          size: Size.square(size),
          painter: _FadeBandsPainter(baseColor: color),
        );
      case kEditorIconHighlightRing:
        return CustomPaint(
          size: Size.square(size),
          painter: _HighlightRingPainter(color: color),
        );
      case kEditorIconFilterRings:
        return CustomPaint(
          size: Size.square(size),
          painter: _FilterRingsPainter(color: color),
        );
      case kEditorIconShadowRing:
        return CustomPaint(
          size: Size.square(size),
          painter: _ShadowRingPainter(color: color),
        );
      case kEditorIconHslSolid:
        return CustomPaint(
          size: Size.square(size),
          painter: _HslSolidPainter(color: color),
        );
      case kEditorIconBwLevels:
        return CustomPaint(
          size: Size.square(size),
          painter: _BwLevelsPainter(color: color),
        );
      default:
        return SizedBox(
          width: size,
          height: size,
          child: Icon(
            Icons.circle_outlined,
            size: size,
            color: color,
          ),
        );
    }
  }
}

class _FadeBandsPainter extends CustomPainter {
  const _FadeBandsPainter({required this.baseColor});

  final Color baseColor;

  @override
  void paint(Canvas canvas, Size size) {
    final alpha = baseColor.a;
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2;
    final ringPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = radius * 0.20
      ..color = AppColors.white.withValues(alpha: alpha);
    canvas.drawCircle(center, radius - ringPaint.strokeWidth / 2, ringPaint);

    final clipPath = Path()
      ..addOval(
        Rect.fromCircle(
          center: center,
          radius: radius - ringPaint.strokeWidth * 0.60,
        ),
      );
    canvas.save();
    canvas.clipPath(clipPath);
    final bandHeight = (radius * 1.35) / 4;
    final top = center.dy - (bandHeight * 2);
    final bands = <Color>[
      AppColors.black.withValues(alpha: 0.86 * alpha),
      AppColors.white.withValues(alpha: 0.22 * alpha),
      AppColors.white.withValues(alpha: 0.45 * alpha),
      AppColors.white.withValues(alpha: 0.78 * alpha),
    ];
    for (var i = 0; i < 4; i++) {
      final rect = Rect.fromLTWH(
        center.dx - radius,
        top + bandHeight * i,
        radius * 2,
        bandHeight,
      );
      canvas.drawRect(
        rect,
        Paint()..color = bands[i],
      );
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _FadeBandsPainter oldDelegate) {
    return oldDelegate.baseColor != baseColor;
  }
}

class _HighlightRingPainter extends CustomPainter {
  const _HighlightRingPainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2;
    final ringPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = radius * 0.17
      ..color = color;
    canvas.drawCircle(center, radius - ringPaint.strokeWidth / 2, ringPaint);

    final innerArcRadius = radius * 0.48;
    final innerPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = radius * 0.15
      ..strokeCap = StrokeCap.round
      ..color = color;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: innerArcRadius),
      -math.pi / 2.2,
      math.pi * 0.40, // ~1/5 圆
      false,
      innerPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _HighlightRingPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}

class _FilterRingsPainter extends CustomPainter {
  const _FilterRingsPainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final s = math.min(size.width, size.height);
    // 三个圆环等视觉尺寸，轻微交汇，不胶着
    final r = s * 0.18;
    final stroke = s * 0.08;
    final centers = <Offset>[
      Offset(size.width * 0.34, size.height * 0.36),
      Offset(size.width * 0.66, size.height * 0.36),
      Offset(size.width * 0.50, size.height * 0.68),
    ];
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..color = color
      ..strokeCap = StrokeCap.round;
    for (final c in centers) {
      canvas.drawCircle(c, r, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _FilterRingsPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}

class _ShadowRingPainter extends CustomPainter {
  const _ShadowRingPainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2;
    final outerPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = radius * 0.14
      ..color = color;
    canvas.drawCircle(center, radius - outerPaint.strokeWidth / 2, outerPaint);

    final shadowArcPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = radius * 0.18
      ..strokeCap = StrokeCap.round
      ..color = AppColors.white.withValues(alpha: color.a * 0.55);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius * 0.66),
      math.pi * 0.20,
      math.pi * 1.15,
      false,
      shadowArcPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _ShadowRingPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}

class _HslSolidPainter extends CustomPainter {
  const _HslSolidPainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final s = math.min(size.width, size.height);
    // HSL 三实心圆要明显饱满，视觉尺寸与邻近工具图标一致
    final r = s * 0.24;
    final colors = <Color>[
      AppColors.white.withValues(alpha: color.a * 0.86),
      AppColors.white.withValues(alpha: color.a * 0.56),
      AppColors.white.withValues(alpha: color.a * 0.30),
    ];
    final centers = <Offset>[
      Offset(size.width * 0.36, size.height * 0.36),
      Offset(size.width * 0.64, size.height * 0.36),
      Offset(size.width * 0.50, size.height * 0.66),
    ];
    for (var i = 0; i < centers.length; i++) {
      canvas.drawCircle(centers[i], r, Paint()..color = colors[i]);
    }
  }

  @override
  bool shouldRepaint(covariant _HslSolidPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}

class _BwLevelsPainter extends CustomPainter {
  const _BwLevelsPainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final s = math.min(size.width, size.height);
    final rect = RRect.fromRectAndRadius(
      Rect.fromLTWH(s * 0.08, s * 0.12, s * 0.84, s * 0.76),
      Radius.circular(s * 0.24),
    );
    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = s * 0.08
      ..color = color;
    canvas.drawRRect(rect, stroke);

    final clip = Path()..addRRect(rect);
    canvas.save();
    canvas.clipPath(clip);
    final bands = <Color>[
      AppColors.black.withValues(alpha: color.a * 0.85),
      AppColors.white.withValues(alpha: color.a * 0.22),
      AppColors.white.withValues(alpha: color.a * 0.48),
      AppColors.white.withValues(alpha: color.a * 0.82),
    ];
    final bandW = rect.width / bands.length;
    for (var i = 0; i < bands.length; i++) {
      canvas.drawRect(
        Rect.fromLTWH(rect.left + bandW * i, rect.top, bandW, rect.height),
        Paint()..color = bands[i],
      );
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _BwLevelsPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}
