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
/// 画一个正圆形气泡体 + 弧形小尾巴 + 两颗圆点，
/// 对标原型图中圆润评论图标，确保与心形/星星/箭头等高居中。
class AppBubbleIcon extends StatelessWidget {
  final double size;
  final Color color;

  const AppBubbleIcon({
    super.key,
    required this.size,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        size: Size(size, size),
        painter: _RoundBubblePainter(color: color),
      ),
    );
  }
}

class _RoundBubblePainter extends CustomPainter {
  final Color color;

  _RoundBubblePainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final sw = w * 0.075;

    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = sw
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;

    // ── 气泡主体：正圆 ──
    final bubbleR = w * 0.36;
    final bubbleCx = w * 0.52;
    final bubbleCy = h * 0.42;
    canvas.drawCircle(Offset(bubbleCx, bubbleCy), bubbleR, paint);

    // ── 尾巴：从左下弧线向下 ──
    final tailPath = Path();
    final ts = Offset(bubbleCx - bubbleR * 0.45, bubbleCy + bubbleR * 0.82);
    final te = Offset(w * 0.15, h * 0.85);
    final tc = Offset(bubbleCx - bubbleR * 0.75, bubbleCy + bubbleR * 1.1);
    tailPath.moveTo(ts.dx, ts.dy);
    tailPath.quadraticBezierTo(tc.dx, tc.dy, te.dx, te.dy);
    canvas.drawPath(tailPath, paint);

    // ── 两颗圆点 ──
    final dotPaint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;
    final dotR = w * 0.055;
    final dotGap = w * 0.13;
    canvas.drawCircle(Offset(bubbleCx - dotGap, bubbleCy), dotR, dotPaint);
    canvas.drawCircle(Offset(bubbleCx + dotGap, bubbleCy), dotR, dotPaint);
  }

  @override
  bool shouldRepaint(covariant _RoundBubblePainter old) => color != old.color;
}
