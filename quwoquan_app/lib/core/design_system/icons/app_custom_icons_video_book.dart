part of 'app_custom_icons.dart';

// ─── 视频书「书籍 + 播放」图标 ───────────────────────────────
/// 底部导航「视频书」专用图标：方案 B 的书籍轮廓 + 播放符号。
/// 公开类名沿用 AppOpenWindowIcon，避免底栏装配层跟随视觉命名 churn。
class AppOpenWindowIcon extends StatelessWidget {
  const AppOpenWindowIcon({
    super.key,
    required this.size,
    required this.color,
    this.filled = false,
    this.state,
  });

  final double size;
  final Color color;

  /// 旧 API 的 selected 语义；保留给底栏 iconBuilder 继续传入。
  final bool filled;

  /// 新图标算法支持未选中、选中、禁用三态；为空时由 [filled] 映射。
  final AppVideoBookIconState? state;

  @override
  Widget build(BuildContext context) {
    final effectiveState =
        state ??
        (filled
            ? AppVideoBookIconState.selected
            : AppVideoBookIconState.unselected);
    return SizedBox.square(
      dimension: size,
      child: CustomPaint(
        size: Size.square(size),
        painter: _VideoBookIconPainter(color: color, state: effectiveState),
      ),
    );
  }
}

enum AppVideoBookIconState { unselected, selected, disabled }

/// 底部导航「视频书」方案 B 的 24pt 标准几何算法。
///
/// 坐标来自方案 B 优化版：加宽主体页、右侧翻页层与居中播放三角。
/// 所有公开方法只做等比缩放，确保 24/28/32/40 等尺寸同源生成。
class AppVideoBookIconGeometry {
  const AppVideoBookIconGeometry._();

  static const double designSize = 24.0;
  static const double unselectedStrokeWidth = 1.24;
  static const double selectedStrokeWidth = 1.24;
  static const double disabledStrokeWidth = 1.24;
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

  static double strokeWidth(
    Size size, {
    AppVideoBookIconState state = AppVideoBookIconState.unselected,
  }) {
    final width = switch (state) {
      AppVideoBookIconState.unselected => unselectedStrokeWidth,
      AppVideoBookIconState.selected => selectedStrokeWidth,
      AppVideoBookIconState.disabled => disabledStrokeWidth,
    };
    return size.shortestSide * width / designSize;
  }

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
