part of 'app_custom_icons.dart';

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
