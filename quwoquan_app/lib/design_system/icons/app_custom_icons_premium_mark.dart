part of 'app_custom_icons.dart';

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
