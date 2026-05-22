import 'dart:math';

import 'package:flutter/material.dart';

// ─── 圆润星星图标 ───────────────────────────────────────────
/// 使用 StrokeJoin.round 画出尖角完全圆润的五角星，
/// 对标原型图中圆润收藏图标。
class AppStarIcon extends StatelessWidget {
  final double size;
  final Color color;
  final bool filled;

  const AppStarIcon({
    super.key,
    required this.size,
    required this.color,
    this.filled = false,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        size: Size(size, size),
        painter: _RoundStarPainter(color: color, filled: filled),
      ),
    );
  }
}

class _RoundStarPainter extends CustomPainter {
  final Color color;
  final bool filled;

  _RoundStarPainter({required this.color, required this.filled});

  @override
  void paint(Canvas canvas, Size size) {
    final sw = size.width * 0.075;
    final path = _starPath(size, sw);

    if (filled) {
      canvas.drawPath(
        path,
        Paint()
          ..color = color
          ..style = PaintingStyle.fill,
      );
    }

    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = sw
        ..strokeJoin = StrokeJoin.round
        ..strokeCap = StrokeCap.round,
    );
  }

  Path _starPath(Size size, double sw) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final outerR = (size.width / 2) - sw;
    final innerR = outerR * 0.42;

    final path = Path();
    for (int i = 0; i < 10; i++) {
      final r = i.isEven ? outerR : innerR;
      final angle = -pi / 2 + pi * i / 5;
      final x = cx + r * cos(angle);
      final y = cy + r * sin(angle);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    path.close();
    return path;
  }

  @override
  bool shouldRepaint(covariant _RoundStarPainter old) =>
      color != old.color || filled != old.filled;
}

// ─── 圆润气泡图标 ───────────────────────────────────────────
/// 无内部横线的单评论气泡，避免圆圈尾线和文字气泡的视觉干扰。
class AppBubbleIcon extends StatelessWidget {
  final double size;
  final Color color;
  final bool filled;

  const AppBubbleIcon({
    super.key,
    required this.size,
    required this.color,
    this.filled = false,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        size: Size(size, size),
        painter: _RoundedBubblePainter(color: color, filled: filled),
      ),
    );
  }
}

/// 两个无文字横线的对话气泡，用于表达「消息 = 多人会话」。
class AppMessagesIcon extends StatelessWidget {
  const AppMessagesIcon({
    super.key,
    required this.size,
    required this.color,
    this.filled = false,
  });

  final double size;
  final Color color;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        size: Size(size, size),
        painter: _MessagesPainter(color: color, filled: filled),
      ),
    );
  }
}

/// 圆润花印，用于「精品」入口，避免钻石、星星、播放三角带来的尖角和视频误解。
class AppPremiumMarkIcon extends StatelessWidget {
  const AppPremiumMarkIcon({
    super.key,
    required this.size,
    required this.color,
    this.filled = false,
  });

  final double size;
  final Color color;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        size: Size(size, size),
        painter: _PremiumMarkPainter(color: color, filled: filled),
      ),
    );
  }
}

class _RoundedBubblePainter extends CustomPainter {
  _RoundedBubblePainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  @override
  void paint(Canvas canvas, Size size) {
    final sw = size.width * 0.075;
    final path = _bubblePath(
      size,
      Rect.fromLTWH(
        size.width * 0.14,
        size.height * 0.17,
        size.width * 0.72,
        size.height * 0.54,
      ),
      radius: size.width * 0.22,
      tailBaseStartX: size.width * 0.36,
      tailBaseEndX: size.width * 0.54,
      tailTip: Offset(size.width * 0.22, size.height * 0.84),
    );

    _paintIconPath(canvas, path, color: color, strokeWidth: sw, filled: filled);
  }

  @override
  bool shouldRepaint(covariant _RoundedBubblePainter old) =>
      color != old.color || filled != old.filled;
}

class _MessagesPainter extends CustomPainter {
  _MessagesPainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  @override
  void paint(Canvas canvas, Size size) {
    final sw = size.width * 0.075;
    final back = RRect.fromRectAndRadius(
      Rect.fromLTWH(
        size.width * 0.31,
        size.height * 0.15,
        size.width * 0.52,
        size.height * 0.40,
      ),
      Radius.circular(size.width * 0.18),
    );
    final front = _bubblePath(
      size,
      Rect.fromLTWH(
        size.width * 0.13,
        size.height * 0.30,
        size.width * 0.60,
        size.height * 0.43,
      ),
      radius: size.width * 0.19,
      tailBaseStartX: size.width * 0.34,
      tailBaseEndX: size.width * 0.50,
      tailTip: Offset(size.width * 0.18, size.height * 0.86),
    );

    final fillPaint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;
    final strokePaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = sw
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;

    if (filled) {
      canvas.drawRRect(back, fillPaint);
      canvas.drawPath(front, fillPaint);
    }
    canvas.drawRRect(back, strokePaint);
    canvas.drawPath(front, strokePaint);
  }

  @override
  bool shouldRepaint(covariant _MessagesPainter old) =>
      color != old.color || filled != old.filled;
}

class _PremiumMarkPainter extends CustomPainter {
  _PremiumMarkPainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  @override
  void paint(Canvas canvas, Size size) {
    final sw = size.width * 0.075;
    final strokePaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = sw
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;
    final fillPaint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;

    canvas.save();
    canvas.translate(size.width / 2, size.height / 2);
    for (var i = 0; i < 4; i++) {
      canvas.save();
      canvas.rotate(pi / 2 * i);
      final petal = RRect.fromRectAndRadius(
        Rect.fromCenter(
          center: Offset(0, -size.height * 0.18),
          width: size.width * 0.28,
          height: size.height * 0.46,
        ),
        Radius.circular(size.width * 0.14),
      );
      if (filled) {
        canvas.drawRRect(petal, fillPaint);
      }
      canvas.drawRRect(petal, strokePaint);
      canvas.restore();
    }
    canvas.restore();

    final center = Offset(size.width / 2, size.height / 2);
    if (filled) {
      canvas.drawCircle(center, size.width * 0.09, Paint()..color = color);
    } else {
      canvas.drawCircle(center, size.width * 0.07, strokePaint);
    }
  }

  @override
  bool shouldRepaint(covariant _PremiumMarkPainter old) =>
      color != old.color || filled != old.filled;
}

Path _bubblePath(
  Size size,
  Rect rect, {
  required double radius,
  required double tailBaseStartX,
  required double tailBaseEndX,
  required Offset tailTip,
}) {
  final path = Path()
    ..moveTo(rect.left + radius, rect.top)
    ..lineTo(rect.right - radius, rect.top)
    ..quadraticBezierTo(rect.right, rect.top, rect.right, rect.top + radius)
    ..lineTo(rect.right, rect.bottom - radius)
    ..quadraticBezierTo(
      rect.right,
      rect.bottom,
      rect.right - radius,
      rect.bottom,
    )
    ..lineTo(tailBaseEndX, rect.bottom)
    ..quadraticBezierTo(
      tailTip.dx + size.width * 0.07,
      tailTip.dy - size.height * 0.01,
      tailTip.dx,
      tailTip.dy,
    )
    ..quadraticBezierTo(
      tailTip.dx + size.width * 0.08,
      tailTip.dy - size.height * 0.11,
      tailBaseStartX,
      rect.bottom,
    )
    ..lineTo(rect.left + radius, rect.bottom)
    ..quadraticBezierTo(rect.left, rect.bottom, rect.left, rect.bottom - radius)
    ..lineTo(rect.left, rect.top + radius)
    ..quadraticBezierTo(rect.left, rect.top, rect.left + radius, rect.top)
    ..close();
  return path;
}

void _paintIconPath(
  Canvas canvas,
  Path path, {
  required Color color,
  required double strokeWidth,
  required bool filled,
}) {
  if (filled) {
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.fill,
    );
  }
  canvas.drawPath(
    path,
    Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round,
  );
}
