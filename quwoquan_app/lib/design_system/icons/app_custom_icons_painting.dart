part of 'app_custom_icons.dart';

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
