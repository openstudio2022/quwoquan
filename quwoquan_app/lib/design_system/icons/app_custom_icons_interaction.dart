part of 'app_custom_icons.dart';

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
