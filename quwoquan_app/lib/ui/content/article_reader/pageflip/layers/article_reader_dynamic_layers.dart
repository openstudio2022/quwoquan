import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class ArticleReaderDynamicLayerSpec {
  const ArticleReaderDynamicLayerSpec({
    required this.pageIndex,
    required this.direction,
    required this.isFlippingPage,
    required this.clipArea,
    required this.anchor,
    required this.angle,
  });

  final int pageIndex;
  final StPageFlipDirection direction;
  final bool isFlippingPage;
  final List<Offset> clipArea;
  final Offset anchor;
  final double angle;
}

class ArticlePolygonClipper extends CustomClipper<Path> {
  const ArticlePolygonClipper(this.points);

  final List<Offset> points;

  @override
  Path getClip(Size size) {
    final path = Path();
    if (points.isEmpty) {
      return path;
    }
    path.moveTo(points.first.dx, points.first.dy);
    for (final point in points.skip(1)) {
      path.lineTo(point.dx, point.dy);
    }
    path.close();
    return path;
  }

  @override
  bool shouldReclip(covariant ArticlePolygonClipper oldClipper) {
    if (identical(points, oldClipper.points)) {
      return false;
    }
    if (points.length != oldClipper.points.length) {
      return true;
    }
    for (var index = 0; index < points.length; index += 1) {
      if (points[index] != oldClipper.points[index]) {
        return true;
      }
    }
    return false;
  }
}

enum ArticlePageSurfaceKind { front, back, bottom }
