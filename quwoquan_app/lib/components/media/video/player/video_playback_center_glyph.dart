import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 暂停态中央的纯视觉播放提示。
///
/// 播放命令仍由外层整块视频画布处理；本组件不建立第二个点击区域。
/// 三角三个角必须圆润，且不得绘制圆形/方形背景容器。
class VideoPlaybackCenterPlayGlyph extends StatelessWidget {
  const VideoPlaybackCenterPlayGlyph({super.key});

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: SizedBox.square(
        dimension: AppSpacing.videoPlayOverlaySize,
        child: Center(
          child: CustomPaint(
            key: const ValueKey<String>('video-rounded-play-glyph-paint'),
            size: const Size.square(AppSpacing.videoPlayRoundedGlyphSize),
            painter: const _RoundedPlayGlyphPainter(),
          ),
        ),
      ),
    );
  }
}

class _RoundedPlayGlyphPainter extends CustomPainter {
  const _RoundedPlayGlyphPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final path = _roundedTrianglePath(size, cornerRadius: AppSpacing.xs);
    final paint = Paint()
      ..color = AppColors.white.withValues(alpha: 0.94)
      ..style = PaintingStyle.fill
      ..isAntiAlias = true;
    canvas.drawPath(path, paint);
  }

  /// 以顶点邻边内缩 + 二次贝塞尔构造圆角三角，避免尖角 Icon。
  Path _roundedTrianglePath(Size size, {required double cornerRadius}) {
    final p0 = Offset(size.width * 0.30, size.height * 0.18);
    final p1 = Offset(size.width * 0.84, size.height * 0.50);
    final p2 = Offset(size.width * 0.30, size.height * 0.82);
    final vertices = <Offset>[p0, p1, p2];
    final path = Path();
    for (var i = 0; i < vertices.length; i++) {
      final previous = vertices[(i + vertices.length - 1) % vertices.length];
      final current = vertices[i];
      final next = vertices[(i + 1) % vertices.length];
      final toPrev = previous - current;
      final toNext = next - current;
      final prevLength = toPrev.distance;
      final nextLength = toNext.distance;
      if (prevLength <= 0 || nextLength <= 0) {
        continue;
      }
      final radius = math.min(
        cornerRadius,
        math.min(prevLength, nextLength) / 2,
      );
      final start = current + (toPrev / prevLength) * radius;
      final end = current + (toNext / nextLength) * radius;
      if (i == 0) {
        path.moveTo(start.dx, start.dy);
      } else {
        path.lineTo(start.dx, start.dy);
      }
      path.quadraticBezierTo(current.dx, current.dy, end.dx, end.dy);
    }
    path.close();
    return path;
  }

  @override
  bool shouldRepaint(covariant _RoundedPlayGlyphPainter oldDelegate) => false;
}
