part of 'app_custom_icons.dart';

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
