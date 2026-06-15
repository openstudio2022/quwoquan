import 'dart:math' as math;

import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/material.dart';

// ─── 精品「钻石」图标 ───────────────────────────────────────
/// 底部导航「精品」专用图标：极简钻石轮廓，表达精选与高价值内容。
/// 公开类名沿用 AppOpenWindowIcon，避免底栏装配层跟随视觉命名 churn。
class AppOpenWindowIcon extends StatelessWidget {
  const AppOpenWindowIcon({
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
        painter: _PremiumDiamondPainter(color: color, filled: filled),
      ),
    );
  }
}

class _PremiumDiamondPainter extends CustomPainter {
  _PremiumDiamondPainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  // 与首页/联系底栏图标保持同级线性视觉重量。
  static const double _strokeRatio = 1.42 / 24.0;

  double _x(Size size, double value) => size.width * value / 24.0;

  double _y(Size size, double value) => size.height * value / 24.0;

  Path _diamondPath(Size size) => Path()
    ..moveTo(_x(size, 7.3), _y(size, 3.8))
    ..lineTo(_x(size, 16.7), _y(size, 3.8))
    ..lineTo(_x(size, 21.2), _y(size, 9.6))
    ..lineTo(_x(size, 12.0), _y(size, 21.0))
    ..lineTo(_x(size, 2.8), _y(size, 9.6))
    ..close();

  @override
  void paint(Canvas canvas, Size size) {
    final strokeWidth = size.width * _strokeRatio;

    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;
    canvas.drawPath(_diamondPath(size), stroke);
  }

  @override
  bool shouldRepaint(covariant _PremiumDiamondPainter old) =>
      color != old.color || filled != old.filled;
}

// ─── 联系「双气泡」图标 ─────────────────────────────────────
/// 底部导航「联系」专用图标：双聊天气泡，表达「联系/沟通」。
/// 24pt 下不绘制笑脸细节，避免缩放后糊成噪点；视觉口径与「建群聊」图标一致。
/// 按高保规范 24×24pt 矢量复刻，支持任意尺寸像素级缩放。
class AppContactsIcon extends StatelessWidget {
  const AppContactsIcon({
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
        painter: _ContactsPainter(color: color, filled: filled),
      ),
    );
  }
}

class _ContactsPainter extends CustomPainter {
  _ContactsPainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  static const double _strokeRatio = 1.28 / 24.0;

  double _x(Size size, double value) => size.width * value / 24.0;

  double _y(Size size, double value) => size.height * value / 24.0;

  Rect _scaledRect(Size size, Rect rect) => Rect.fromLTRB(
    _x(size, rect.left),
    _y(size, rect.top),
    _x(size, rect.right),
    _y(size, rect.bottom),
  );

  double _rad(double degrees) => degrees * math.pi / 180.0;

  Offset _ellipsePoint(Rect body, double degrees) {
    final angle = _rad(degrees);
    return Offset(
      body.center.dx + body.width / 2 * math.cos(angle),
      body.center.dy + body.height / 2 * math.sin(angle),
    );
  }

  double _longArcSweep(double fromDegrees, double toDegrees) {
    final delta = toDegrees - fromDegrees;
    return _rad(delta > 0 ? delta - 360.0 : delta + 360.0);
  }

  Path _bubblePath(
    Size size, {
    required Rect body,
    required double tailStartDegrees,
    required double tailEndDegrees,
    required Offset tipA,
    required Offset tipB,
    required Offset roundA,
    required Offset roundTip,
    required Offset roundB,
  }) {
    final attachA = _ellipsePoint(body, tailStartDegrees);
    final attachB = _ellipsePoint(body, tailEndDegrees);
    final scaledBody = _scaledRect(size, body);
    return Path()
      ..moveTo(_x(size, attachA.dx), _y(size, attachA.dy))
      ..quadraticBezierTo(
        _x(size, roundA.dx),
        _y(size, roundA.dy),
        _x(size, tipA.dx),
        _y(size, tipA.dy),
      )
      ..quadraticBezierTo(
        _x(size, roundTip.dx),
        _y(size, roundTip.dy),
        _x(size, tipB.dx),
        _y(size, tipB.dy),
      )
      ..quadraticBezierTo(
        _x(size, roundB.dx),
        _y(size, roundB.dy),
        _x(size, attachB.dx),
        _y(size, attachB.dy),
      )
      ..arcTo(
        scaledBody,
        _rad(tailEndDegrees),
        _longArcSweep(tailEndDegrees, tailStartDegrees),
        false,
      )
      ..close();
  }

  Path _largeBubblePath(Size size) {
    return _bubblePath(
      size,
      body: const Rect.fromLTRB(0.55, 1.92, 15.45, 16.22),
      tailStartDegrees: 130.0,
      tailEndDegrees: 97.0,
      tipA: const Offset(3.08, 19.12),
      tipB: const Offset(4.16, 18.72),
      roundA: const Offset(3.92, 16.42),
      roundTip: const Offset(3.14, 19.52),
      roundB: const Offset(5.40, 17.82),
    );
  }

  Path _smallBubblePath(Size size) {
    return _bubblePath(
      size,
      body: const Rect.fromLTRB(12.52, 5.78, 23.62, 16.88),
      tailStartDegrees: 65.0,
      tailEndDegrees: 43.0,
      tipA: const Offset(21.86, 19.02),
      tipB: const Offset(22.44, 18.78),
      roundA: const Offset(21.20, 17.28),
      roundTip: const Offset(22.30, 19.36),
      roundB: const Offset(22.08, 17.22),
    );
  }

  @override
  void paint(Canvas canvas, Size size) {
    final strokeWidth = size.width * _strokeRatio;
    final largeBubble = _largeBubblePath(size);
    final smallBubble = _smallBubblePath(size);

    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;
    final fill = Paint()
      ..color = color.withValues(alpha: filled ? 0.10 : 0.0)
      ..style = PaintingStyle.fill;

    canvas.saveLayer(Offset.zero & size, Paint());
    if (filled) {
      canvas.drawPath(largeBubble, fill);
    }
    canvas.drawPath(largeBubble, stroke);

    // 小气泡在视觉上压在大气泡上层，先清出小气泡面再绘制，
    // 让它遮挡住大气泡底部/右侧线条，形成高保稿的堆叠关系。
    canvas.drawPath(
      smallBubble,
      Paint()
        ..blendMode = BlendMode.clear
        ..style = PaintingStyle.fill,
    );
    if (filled) {
      canvas.drawPath(smallBubble, fill);
    }
    canvas.drawPath(smallBubble, stroke);
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _ContactsPainter old) =>
      color != old.color || filled != old.filled;
}

// ─── 我的「单人」图标 ───────────────────────────────────────
/// 底部导航「我的」专用图标：正圆头 + 敞口肩弧（无外圆圈）。
/// 按高保规范 24×24pt 矢量复刻，支持任意尺寸像素级缩放。
class AppProfilePersonIcon extends StatelessWidget {
  const AppProfilePersonIcon({
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
        painter: _ProfilePersonPainter(color: color, filled: filled),
      ),
    );
  }
}

/// 底部导航「我的」高保人形图标的 24pt 几何算法。
///
/// 与欢迎页花瓣的 `petalPath()` 同思路：把高保稿抽成可复用的标准坐标，
/// 任何尺寸只做等比缩放，避免后续出现第二套头像轮廓。
class AppProfilePersonIconGeometry {
  const AppProfilePersonIconGeometry._();

  static const double designSize = 24.0;
  static const double inactiveStrokeWidth = 1.38;
  static const double selectedStrokeWidth = 1.46;

  static double _x(Size size, double value) => size.width * value / designSize;

  static double _y(Size size, double value) => size.height * value / designSize;

  static Rect headRect(Size size) {
    final radius = _x(size, 4.35);
    final center = Offset(_x(size, 12.0), _y(size, 6.05));
    return Rect.fromCircle(center: center, radius: radius);
  }

  static Path bodyPath(Size size) {
    return Path()
      ..moveTo(_x(size, 4.20), _y(size, 19.85))
      ..lineTo(_x(size, 4.20), _y(size, 16.90))
      ..cubicTo(
        _x(size, 4.20),
        _y(size, 14.25),
        _x(size, 6.25),
        _y(size, 12.45),
        _x(size, 9.50),
        _y(size, 12.45),
      )
      ..lineTo(_x(size, 14.50), _y(size, 12.45))
      ..cubicTo(
        _x(size, 17.75),
        _y(size, 12.45),
        _x(size, 19.80),
        _y(size, 14.25),
        _x(size, 19.80),
        _y(size, 16.90),
      )
      ..lineTo(_x(size, 19.80), _y(size, 19.85))
      ..lineTo(_x(size, 4.20), _y(size, 19.85));
  }

  static void paintIcon(
    Canvas canvas,
    Size size, {
    required Color color,
    required bool selected,
  }) {
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth =
          size.width *
          (selected ? selectedStrokeWidth : inactiveStrokeWidth) /
          designSize
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;
    canvas
      ..drawOval(headRect(size), stroke)
      ..drawPath(bodyPath(size), stroke);
  }
}

class _ProfilePersonPainter extends CustomPainter {
  _ProfilePersonPainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  @override
  void paint(Canvas canvas, Size size) {
    AppProfilePersonIconGeometry.paintIcon(
      canvas,
      size,
      color: color,
      selected: filled,
    );
  }

  @override
  bool shouldRepaint(covariant _ProfilePersonPainter old) =>
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
