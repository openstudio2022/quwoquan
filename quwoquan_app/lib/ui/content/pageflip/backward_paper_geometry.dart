import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class BackwardPaperGeometry {
  const BackwardPaperGeometry({
    required this.pageEdgeLineTop,
    required this.pageEdgeLineBottom,
    required this.foldLineTop,
    required this.foldLineBottom,
    required this.previousFrontPolygon,
    required this.previousBackPolygon,
    required this.currentResidualPolygon,
  });

  final Offset pageEdgeLineTop;
  final Offset pageEdgeLineBottom;
  final Offset foldLineTop;
  final Offset foldLineBottom;
  final List<Offset> previousFrontPolygon;
  final List<Offset> previousBackPolygon;
  final List<Offset> currentResidualPolygon;

  Rect? get previousFrontBounds => _polygonBounds(previousFrontPolygon);
  Rect? get previousBackBounds => _polygonBounds(previousBackPolygon);
  Rect? get currentResidualBounds => _polygonBounds(currentResidualPolygon);

  bool get hasPreviousFront => previousFrontBounds != null;
  bool get hasPreviousBack => previousBackBounds != null;
  bool get hasCurrentResidual => currentResidualBounds != null;
}

BackwardPaperGeometry buildBackwardPaperGeometry({
  required Rect pageRect,
  required Size pageSize,
  required List<Offset>? flippingClipArea,
  required double progress,
  required Offset? localPagePoint,
  required StPageFlipCorner corner,
}) {
  final foldT = _resolveFoldT(
    pageWidth: pageSize.width,
    progress: progress,
    flippingClipArea: flippingClipArea,
  );
  final skew = _resolveLineSkew(
    pageSize: pageSize,
    localPagePoint: localPagePoint,
    corner: corner,
  );
  final foldBaseX = _lerp(pageRect.left, pageRect.right, foldT);
  final edgeBaseX = _lerp(pageRect.left, foldBaseX, 0.38);
  final foldLine = _lineForBaseX(
    pageRect: pageRect,
    baseX: foldBaseX,
    skew: skew,
  );
  final edgeLine = _lineForBaseX(
    pageRect: pageRect,
    baseX: edgeBaseX,
    skew: skew * 0.82,
  );

  final previousFront = _validPolygon(<Offset>[
    pageRect.topLeft,
    edgeLine.$1,
    edgeLine.$2,
    pageRect.bottomLeft,
  ]);
  final previousBack = _validPolygon(<Offset>[
    edgeLine.$1,
    foldLine.$1,
    foldLine.$2,
    edgeLine.$2,
  ]);
  final currentResidual = _validPolygon(<Offset>[
    foldLine.$1,
    pageRect.topRight,
    pageRect.bottomRight,
    foldLine.$2,
  ]);

  return BackwardPaperGeometry(
    pageEdgeLineTop: edgeLine.$1,
    pageEdgeLineBottom: edgeLine.$2,
    foldLineTop: foldLine.$1,
    foldLineBottom: foldLine.$2,
    previousFrontPolygon: previousFront,
    previousBackPolygon: previousBack,
    currentResidualPolygon: currentResidual,
  );
}

double _resolveFoldT({
  required double pageWidth,
  required double progress,
  required List<Offset>? flippingClipArea,
}) {
  if (flippingClipArea != null &&
      flippingClipArea.isNotEmpty &&
      pageWidth > 0) {
    final maxX = flippingClipArea.fold<double>(
      0,
      (value, point) => math.max(value, point.dx),
    );
    return (maxX / pageWidth).clamp(0.04, 0.985).toDouble();
  }
  return progress.clamp(0.04, 0.985).toDouble();
}

double _resolveLineSkew({
  required Size pageSize,
  required Offset? localPagePoint,
  required StPageFlipCorner corner,
}) {
  final normalizedY = pageSize.height <= 0 || localPagePoint == null
      ? 0.5
      : (localPagePoint.dy / pageSize.height).clamp(0.0, 1.0).toDouble();
  final centered = normalizedY - 0.5;
  final cornerSign = corner == StPageFlipCorner.bottom ? -1.0 : 1.0;
  return centered * pageSize.width * 0.34 * cornerSign;
}

(Offset, Offset) _lineForBaseX({
  required Rect pageRect,
  required double baseX,
  required double skew,
}) {
  final top = Offset(
    (baseX - skew).clamp(pageRect.left, pageRect.right).toDouble(),
    pageRect.top,
  );
  final bottom = Offset(
    (baseX + skew).clamp(pageRect.left, pageRect.right).toDouble(),
    pageRect.bottom,
  );
  return (top, bottom);
}

List<Offset> _validPolygon(List<Offset> polygon) {
  final bounds = _polygonBounds(polygon);
  if (bounds == null) {
    return const <Offset>[];
  }
  return List<Offset>.unmodifiable(polygon);
}

Rect? _polygonBounds(List<Offset> polygon) {
  if (polygon.length < 3) {
    return null;
  }
  var left = polygon.first.dx;
  var top = polygon.first.dy;
  var right = left;
  var bottom = top;
  for (final point in polygon.skip(1)) {
    left = math.min(left, point.dx);
    top = math.min(top, point.dy);
    right = math.max(right, point.dx);
    bottom = math.max(bottom, point.dy);
  }
  if (right - left <= 0.5 || bottom - top <= 0.5) {
    return null;
  }
  return Rect.fromLTRB(left, top, right, bottom);
}

double _lerp(double a, double b, double t) => a + (b - a) * t;
