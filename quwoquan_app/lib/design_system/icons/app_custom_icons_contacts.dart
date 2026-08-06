part of 'app_custom_icons.dart';

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

  static const double _strokeRatio = 1.34 / 24.0;

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
      body: const Rect.fromLTRB(0.50, 1.30, 15.85, 17.35),
      tailStartDegrees: 130.0,
      tailEndDegrees: 98.0,
      tipA: const Offset(2.90, 21.05),
      tipB: const Offset(4.45, 20.42),
      roundA: const Offset(3.72, 17.58),
      roundTip: const Offset(2.95, 21.52),
      roundB: const Offset(5.80, 19.08),
    );
  }

  Path _smallBubblePath(Size size) {
    return _bubblePath(
      size,
      // 小气泡应压在大气泡右上，不向下坠；尾巴也收短以贴近建群聊图标。
      body: const Rect.fromLTRB(11.75, 3.00, 23.35, 15.15),
      tailStartDegrees: 66.0,
      tailEndDegrees: 46.0,
      tipA: const Offset(21.40, 17.20),
      tipB: const Offset(22.08, 16.88),
      roundA: const Offset(20.72, 15.68),
      roundTip: const Offset(21.92, 17.62),
      roundB: const Offset(21.76, 15.55),
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
