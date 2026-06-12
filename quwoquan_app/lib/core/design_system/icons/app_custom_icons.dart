import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/material.dart';

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

/// 媒体互动栏专用心形：与转发、评论共用同一视觉包围盒。
class AppMediaHeartIcon extends StatelessWidget {
  const AppMediaHeartIcon({
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
    return SizedBox.square(
      dimension: size,
      child: CustomPaint(
        size: Size.square(size),
        painter: _MediaHeartPainter(color: color, filled: filled),
      ),
    );
  }
}

/// 媒体互动栏专用转发箭头，对齐 post 卡片的轻量转发语义。
class AppMediaShareIcon extends StatelessWidget {
  const AppMediaShareIcon({super.key, required this.size, required this.color});

  final double size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: size,
      child: Center(
        child: Transform.translate(
          offset: Offset(0, size * -0.01),
          child: Icon(
            CupertinoIcons.arrowshape_turn_up_right,
            size: size,
            color: color,
          ),
        ),
      ),
    );
  }
}

/// 媒体互动栏专用评论气泡：尾巴更短更圆，避免底部尖角下坠。
class AppMediaCommentIcon extends StatelessWidget {
  const AppMediaCommentIcon({
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
    return SizedBox.square(
      dimension: size,
      child: CustomPaint(
        size: Size.square(size),
        painter: _MediaCommentPainter(color: color, filled: filled),
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
    required this.backgroundColor,
    this.filled = false,
  });

  final double size;
  final Color color;
  final Color backgroundColor;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        size: Size(size, size),
        painter: _MessagesPainter(
          color: color,
          backgroundColor: backgroundColor,
          filled: filled,
        ),
      ),
    );
  }
}

/// 单气泡消息图标，用于私信等一对一消息入口。
class AppMessageBubbleIcon extends StatelessWidget {
  const AppMessageBubbleIcon({
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
    return SizedBox.square(
      dimension: size,
      child: CustomPaint(
        size: Size.square(size),
        painter: _MessageBubblePainter(color: color, filled: filled),
      ),
    );
  }
}

/// 圆润播放按钮，用于「精品」入口，避免与中间创建按钮形成交叉重叠感。
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

class _MediaHeartPainter extends CustomPainter {
  _MediaHeartPainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  @override
  void paint(Canvas canvas, Size size) {
    final sw = _mediaIconStrokeWidth(size);
    final path = Path()
      ..moveTo(size.width * 0.50, size.height * 0.81)
      ..cubicTo(
        size.width * 0.25,
        size.height * 0.64,
        size.width * 0.15,
        size.height * 0.51,
        size.width * 0.15,
        size.height * 0.35,
      )
      ..cubicTo(
        size.width * 0.15,
        size.height * 0.22,
        size.width * 0.25,
        size.height * 0.15,
        size.width * 0.36,
        size.height * 0.15,
      )
      ..cubicTo(
        size.width * 0.43,
        size.height * 0.15,
        size.width * 0.48,
        size.height * 0.19,
        size.width * 0.50,
        size.height * 0.27,
      )
      ..cubicTo(
        size.width * 0.52,
        size.height * 0.19,
        size.width * 0.57,
        size.height * 0.15,
        size.width * 0.64,
        size.height * 0.15,
      )
      ..cubicTo(
        size.width * 0.75,
        size.height * 0.15,
        size.width * 0.85,
        size.height * 0.22,
        size.width * 0.85,
        size.height * 0.35,
      )
      ..cubicTo(
        size.width * 0.85,
        size.height * 0.51,
        size.width * 0.75,
        size.height * 0.64,
        size.width * 0.50,
        size.height * 0.81,
      )
      ..close();

    _paintIconPath(canvas, path, color: color, strokeWidth: sw, filled: filled);
  }

  @override
  bool shouldRepaint(covariant _MediaHeartPainter old) =>
      color != old.color || filled != old.filled;
}

class _MediaCommentPainter extends CustomPainter {
  _MediaCommentPainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  @override
  void paint(Canvas canvas, Size size) {
    final sw = _mediaIconStrokeWidth(size);
    final rect = Rect.fromLTWH(
      size.width * 0.15,
      size.height * 0.17,
      size.width * 0.70,
      size.height * 0.52,
    );
    final radius = size.width * 0.16;
    final tailTip = Offset(size.width * 0.34, size.height * 0.77);
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
      ..lineTo(size.width * 0.51, rect.bottom)
      ..cubicTo(
        size.width * 0.45,
        rect.bottom,
        size.width * 0.40,
        size.height * 0.75,
        tailTip.dx,
        tailTip.dy,
      )
      ..cubicTo(
        size.width * 0.36,
        size.height * 0.76,
        size.width * 0.34,
        rect.bottom,
        size.width * 0.30,
        rect.bottom,
      )
      ..lineTo(rect.left + radius, rect.bottom)
      ..quadraticBezierTo(
        rect.left,
        rect.bottom,
        rect.left,
        rect.bottom - radius,
      )
      ..lineTo(rect.left, rect.top + radius)
      ..quadraticBezierTo(rect.left, rect.top, rect.left + radius, rect.top)
      ..close();

    _paintIconPath(canvas, path, color: color, strokeWidth: sw, filled: filled);
  }

  @override
  bool shouldRepaint(covariant _MediaCommentPainter old) =>
      color != old.color || filled != old.filled;
}

class _MessagesPainter extends CustomPainter {
  _MessagesPainter({
    required this.color,
    required this.backgroundColor,
    required this.filled,
  });

  final Color color;
  final Color backgroundColor;
  final bool filled;

  @override
  void paint(Canvas canvas, Size size) {
    final sw = size.width * 0.064;

    final back = _conversationBubblePath(
      rect: Rect.fromLTWH(
        size.width * 0.045,
        size.height * 0.13,
        size.width * 0.62,
        size.height * 0.64,
      ),
      tailDirection: _BubbleTailDirection.left,
    );
    final front = _conversationBubblePath(
      rect: Rect.fromLTWH(
        size.width * 0.34,
        size.height * 0.19,
        size.width * 0.60,
        size.height * 0.60,
      ),
      tailDirection: _BubbleTailDirection.right,
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
      canvas.drawPath(back, fillPaint);
      final separatorPaint = Paint()
        ..color = Color.lerp(color, backgroundColor, 0.58) ?? backgroundColor
        ..style = PaintingStyle.stroke
        ..strokeWidth = sw * 1.22
        ..strokeJoin = StrokeJoin.round
        ..strokeCap = StrokeCap.round;
      canvas.drawPath(front, separatorPaint);
      canvas.drawPath(front, fillPaint);
      return;
    }

    canvas.saveLayer(Offset.zero & size, Paint());
    canvas.drawPath(back, strokePaint);
    final clearFill = Paint()
      ..blendMode = BlendMode.clear
      ..style = PaintingStyle.fill;
    final clearStroke = Paint()
      ..blendMode = BlendMode.clear
      ..style = PaintingStyle.stroke
      ..strokeWidth = sw * 1.85
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;
    canvas.drawPath(front, clearStroke);
    canvas.drawPath(front, clearFill);
    canvas.restore();
    canvas.drawPath(front, strokePaint);
  }

  @override
  bool shouldRepaint(covariant _MessagesPainter old) =>
      color != old.color ||
      backgroundColor != old.backgroundColor ||
      filled != old.filled;
}

class _MessageBubblePainter extends CustomPainter {
  _MessageBubblePainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  @override
  void paint(Canvas canvas, Size size) {
    final sw = size.width * 0.064;
    final path = _conversationBubblePath(
      rect: Rect.fromLTWH(
        size.width * 0.07,
        size.height * 0.07,
        size.width * 0.86,
        size.height * 0.72,
      ),
      tailDirection: _BubbleTailDirection.left,
    );
    final centeredPath = path.shift(
      Offset(size.width * 0.025, size.height * 0.012),
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
      canvas.drawPath(centeredPath, fillPaint);
    }
    canvas.drawPath(centeredPath, strokePaint);
  }

  @override
  bool shouldRepaint(covariant _MessageBubblePainter old) =>
      color != old.color || filled != old.filled;
}

enum _BubbleTailDirection { left, right }

Path _conversationBubblePath({
  required Rect rect,
  required _BubbleTailDirection tailDirection,
}) {
  final path = _leftConversationBubblePath(rect);
  if (tailDirection == _BubbleTailDirection.left) {
    return path;
  }

  final mirror = Matrix4.identity()
    ..translateByDouble(rect.center.dx * 2, 0, 0, 1)
    ..scaleByDouble(-1.0, 1.0, 1.0, 1.0);
  return path.transform(mirror.storage);
}

Path _leftConversationBubblePath(Rect rect) {
  final cx = rect.center.dx;
  final cy = rect.center.dy;
  final rx = rect.width / 2;
  final ry = rect.height / 2;
  const k = 0.5522847498;
  final tailInner = Offset(
    rect.left + rect.width * 0.43,
    rect.top + rect.height * 0.96,
  );
  final tailOuter = Offset(
    rect.left + rect.width * 0.27,
    rect.top + rect.height * 0.87,
  );
  final tailTip = Offset(
    rect.left + rect.width * 0.17,
    rect.top + rect.height * 1.06,
  );

  return Path()
    ..moveTo(cx, cy - ry)
    ..cubicTo(cx + rx * k, cy - ry, cx + rx, cy - ry * k, cx + rx, cy)
    ..cubicTo(
      cx + rx,
      cy + ry * 0.66,
      cx + rx * 0.60,
      cy + ry,
      tailInner.dx,
      tailInner.dy,
    )
    ..cubicTo(
      tailInner.dx - rect.width * 0.04,
      tailInner.dy + rect.height * 0.06,
      tailTip.dx + rect.width * 0.09,
      tailTip.dy - rect.height * 0.01,
      tailTip.dx,
      tailTip.dy,
    )
    ..cubicTo(
      tailTip.dx + rect.width * 0.07,
      tailTip.dy - rect.height * 0.12,
      tailOuter.dx - rect.width * 0.01,
      tailOuter.dy + rect.height * 0.02,
      tailOuter.dx,
      tailOuter.dy,
    )
    ..cubicTo(
      cx - rx * 0.86,
      cy + ry * 0.64,
      cx - rx,
      cy + ry * 0.36,
      cx - rx,
      cy,
    )
    ..cubicTo(cx - rx, cy - ry * k, cx - rx * k, cy - ry, cx, cy - ry)
    ..close();
}

class _PremiumMarkPainter extends CustomPainter {
  _PremiumMarkPainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  @override
  void paint(Canvas canvas, Size size) {
    final sw = size.width * 0.064;
    final strokePaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = sw
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;
    final fillPaint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;

    final play = Path()
      ..moveTo(size.width * 0.31, size.height * 0.19)
      ..quadraticBezierTo(
        size.width * 0.31,
        size.height * 0.13,
        size.width * 0.37,
        size.height * 0.17,
      )
      ..lineTo(size.width * 0.82, size.height * 0.45)
      ..quadraticBezierTo(
        size.width * 0.90,
        size.height * 0.50,
        size.width * 0.82,
        size.height * 0.55,
      )
      ..lineTo(size.width * 0.37, size.height * 0.83)
      ..quadraticBezierTo(
        size.width * 0.31,
        size.height * 0.87,
        size.width * 0.31,
        size.height * 0.81,
      )
      ..close();

    if (filled) {
      canvas.drawPath(play, fillPaint);
    }
    canvas.drawPath(play, strokePaint);
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

double _mediaIconStrokeWidth(Size size) => size.width * 0.075;
