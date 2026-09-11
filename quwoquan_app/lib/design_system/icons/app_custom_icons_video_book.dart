part of 'app_custom_icons.dart';

/// 视频书专用矢量：书封面、右侧页层与空心播放三角。
/// 保留迁入首页前的轮廓；选中只由调用方改变颜色，不填充或加粗。
class AppVideoBookIcon extends StatelessWidget {
  const AppVideoBookIcon({
    super.key,
    required this.size,
    required this.color,
    this.state = AppVideoBookIconState.unselected,
  });

  final double size;
  final Color color;
  final AppVideoBookIconState state;

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: size,
      child: CustomPaint(
        size: Size.square(size),
        painter: _VideoBookIconPainter(color: color, state: state),
      ),
    );
  }
}

enum AppVideoBookIconState { unselected, selected, disabled }

/// 原视频书方案 B 的 24pt 标准几何，24/28/32/40 均等比生成。
class AppVideoBookIconGeometry {
  const AppVideoBookIconGeometry._();

  static const double designSize = 24.0;
  static const double _strokeWidthInDesign = 1.24;
  static const Rect outerBoundsInDesign = Rect.fromLTWH(3.75, 3.0, 16.45, 18.0);
  static const Rect frontCoverRectInDesign = Rect.fromLTWH(
    3.75,
    3.0,
    14.25,
    18.0,
  );
  static const double rightPageLayerOffsetInDesign = 2.2;
  static const double coverCornerRadiusInDesign = 2.8;

  static double _x(Size size, double value) => size.width * value / designSize;

  static double _y(Size size, double value) => size.height * value / designSize;

  static Rect _scaledRect(Size size, Rect rect) => Rect.fromLTRB(
    _x(size, rect.left),
    _y(size, rect.top),
    _x(size, rect.right),
    _y(size, rect.bottom),
  );

  /// 三态统一线宽，状态只参与语义，不改变几何。
  static double strokeWidth(
    Size size, {
    AppVideoBookIconState state = AppVideoBookIconState.unselected,
  }) => size.shortestSide * _strokeWidthInDesign / designSize;

  static Rect outerBounds(Size size) => _scaledRect(size, outerBoundsInDesign);

  static Rect frontCoverRect(Size size) =>
      _scaledRect(size, frontCoverRectInDesign);

  static double coverCornerRadius(Size size) =>
      size.shortestSide * coverCornerRadiusInDesign / designSize;

  static RRect frontCoverRRect(Size size) => RRect.fromRectAndRadius(
    frontCoverRect(size),
    Radius.circular(coverCornerRadius(size)),
  );

  static Path rightPageLayerPath(Size size) {
    final front = frontCoverRect(size);
    final offset = _x(size, rightPageLayerOffsetInDesign);
    final radius = coverCornerRadius(size);
    final outerRight = front.right + offset;
    return Path()
      ..moveTo(front.right - radius * 0.12, front.top)
      ..lineTo(outerRight - radius, front.top)
      ..quadraticBezierTo(outerRight, front.top, outerRight, front.top + radius)
      ..lineTo(outerRight, front.bottom - radius)
      ..quadraticBezierTo(
        outerRight,
        front.bottom,
        outerRight - radius,
        front.bottom,
      )
      ..lineTo(front.right - radius * 0.12, front.bottom);
  }

  static Path playPath(Size size) {
    return Path()
      ..moveTo(_x(size, 8.08), _y(size, 9.18))
      ..quadraticBezierTo(
        _x(size, 8.08),
        _y(size, 8.62),
        _x(size, 8.56),
        _y(size, 8.92),
      )
      ..lineTo(_x(size, 13.12), _y(size, 11.58))
      ..quadraticBezierTo(
        _x(size, 13.76),
        _y(size, 12.0),
        _x(size, 13.12),
        _y(size, 12.42),
      )
      ..lineTo(_x(size, 8.56), _y(size, 15.08))
      ..quadraticBezierTo(
        _x(size, 8.08),
        _y(size, 15.38),
        _x(size, 8.08),
        _y(size, 14.82),
      )
      ..close();
  }

  static void paintIcon(
    Canvas canvas,
    Size size, {
    required Color color,
    required AppVideoBookIconState state,
  }) {
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth(size, state: state)
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;

    canvas
      ..drawPath(rightPageLayerPath(size), stroke)
      ..drawRRect(frontCoverRRect(size), stroke)
      ..drawPath(playPath(size), stroke);
  }
}

class _VideoBookIconPainter extends CustomPainter {
  _VideoBookIconPainter({required this.color, required this.state});

  final Color color;
  final AppVideoBookIconState state;

  @override
  void paint(Canvas canvas, Size size) {
    AppVideoBookIconGeometry.paintIcon(
      canvas,
      size,
      color: color,
      state: state,
    );
  }

  @override
  bool shouldRepaint(covariant _VideoBookIconPainter old) =>
      color != old.color || state != old.state;
}
