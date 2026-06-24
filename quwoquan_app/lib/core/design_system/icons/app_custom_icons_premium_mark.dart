part of 'app_custom_icons.dart';

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
