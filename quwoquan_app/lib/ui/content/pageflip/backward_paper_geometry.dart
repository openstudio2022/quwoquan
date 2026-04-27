import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class BackwardPaperGeometry {
  const BackwardPaperGeometry({
    required this.previousBackMovingSurface,
    required this.pageEdgeLineTop,
    required this.pageEdgeLineBottom,
    required this.foldLineTop,
    required this.foldLineBottom,
    required this.previousFrontPolygon,
    required this.previousBackPolygon,
    required this.currentResidualPolygon,
  });

  final BackwardPaperMovingSurface previousBackMovingSurface;
  final Offset pageEdgeLineTop;
  final Offset pageEdgeLineBottom;
  final Offset foldLineTop;
  final Offset foldLineBottom;
  final List<Offset> previousFrontPolygon;
  final List<Offset> previousBackPolygon;
  final List<Offset> currentResidualPolygon;

  Rect? get previousFrontBounds => _polygonBounds(previousFrontPolygon);
  Rect? get previousBackBounds => previousBackMovingSurface.paintBounds;
  Rect? get currentResidualBounds => _polygonBounds(currentResidualPolygon);

  bool get hasPreviousFront => previousFrontBounds != null;
  bool get hasPreviousBack => previousBackBounds != null;
  bool get hasCurrentResidual => currentResidualBounds != null;
}

@immutable
class BackwardPaperMovingSurface {
  const BackwardPaperMovingSurface({
    required this.clipArea,
    required this.anchor,
    required this.angle,
    required this.viewportPolygon,
    required this.paintBounds,
  });

  final List<Offset> clipArea;
  final Offset anchor;
  final double angle;
  final List<Offset> viewportPolygon;
  final Rect? paintBounds;

  bool get isNotEmpty => paintBounds != null;
}

BackwardPaperGeometry buildBackwardPaperGeometry({
  required Rect pageRect,
  required Size pageSize,
  required List<Offset>? flippingClipArea,
  required Offset? flippingAnchor,
  required double? pageEdgeProgress,
  required double angle,
  required double progress,
  required Offset? localPagePoint,
  required StPageFlipCorner corner,
}) {
  final safeClipArea = flippingClipArea == null || flippingClipArea.length < 3
      ? const <Offset>[]
      : List<Offset>.unmodifiable(flippingClipArea);
  final safeAnchor =
      flippingAnchor ??
      Offset(0, corner == StPageFlipCorner.bottom ? pageSize.height : 0);
  final viewportPolygon = safeClipArea
      .map(
        (point) => _transformLocalPointToViewport(
          point: point,
          anchor: safeAnchor,
          angle: angle,
          pageRect: pageRect,
        ),
      )
      .toList(growable: false);
  final movingBounds = _polygonBounds(viewportPolygon)?.intersect(pageRect);
  final foldLine =
      _lineFromMinXPolygon(viewportPolygon) ??
      _transformedPageEdgeLine(
        pageRect: pageRect,
        pageSize: pageSize,
        anchor: safeAnchor,
        angle: angle,
        x: 0,
      );
  final movingEdgeLine = _transformedPageEdgeLine(
    pageRect: pageRect,
    pageSize: pageSize,
    anchor: safeAnchor,
    angle: angle,
    x: pageSize.width,
  );
  final edgeProgress = (pageEdgeProgress ?? progress)
      .clamp(0.0, 1.0)
      .toDouble();
  final edgeLine = _shiftLineToAverageX(
    movingEdgeLine,
    pageRect.left + pageRect.width * edgeProgress,
  );

  final previousFront = _validPolygon(
    _clipPageRectByLine(pageRect: pageRect, line: edgeLine, keepLeft: true),
  );
  final previousBack = _validPolygon(viewportPolygon);
  final currentResidual = _validPolygon(
    _clipPageRectByLine(pageRect: pageRect, line: edgeLine, keepLeft: false),
  );

  return BackwardPaperGeometry(
    previousBackMovingSurface: BackwardPaperMovingSurface(
      clipArea: safeClipArea,
      anchor: safeAnchor,
      angle: angle,
      viewportPolygon: List<Offset>.unmodifiable(viewportPolygon),
      paintBounds: movingBounds == null || movingBounds.isEmpty
          ? null
          : movingBounds,
    ),
    pageEdgeLineTop: edgeLine.$1,
    pageEdgeLineBottom: edgeLine.$2,
    foldLineTop: foldLine.$1,
    foldLineBottom: foldLine.$2,
    previousFrontPolygon: previousFront,
    previousBackPolygon: previousBack,
    currentResidualPolygon: currentResidual,
  );
}

(Offset, Offset) _shiftLineToAverageX((Offset, Offset) line, double targetX) {
  final currentX = (line.$1.dx + line.$2.dx) / 2;
  final deltaX = targetX - currentX;
  return (
    Offset(line.$1.dx + deltaX, line.$1.dy),
    Offset(line.$2.dx + deltaX, line.$2.dy),
  );
}

(Offset, Offset)? _lineFromMinXPolygon(List<Offset> polygon) {
  if (polygon.length < 2) {
    return null;
  }
  final sorted = polygon.toList(growable: false)
    ..sort((a, b) {
      final x = a.dx.compareTo(b.dx);
      return x == 0 ? a.dy.compareTo(b.dy) : x;
    });
  final pair = sorted.take(2).toList(growable: false);
  if (pair.length < 2 || (pair.first.dy - pair.last.dy).abs() <= 0.5) {
    return null;
  }
  return pair.first.dy <= pair.last.dy
      ? (pair.first, pair.last)
      : (pair.last, pair.first);
}

(Offset, Offset) _transformedPageEdgeLine({
  required Rect pageRect,
  required Size pageSize,
  required Offset anchor,
  required double angle,
  required double x,
}) {
  final top = _transformLocalPointToViewport(
    point: Offset(x, 0),
    anchor: anchor,
    angle: angle,
    pageRect: pageRect,
  );
  final bottom = _transformLocalPointToViewport(
    point: Offset(x, pageSize.height),
    anchor: anchor,
    angle: angle,
    pageRect: pageRect,
  );
  return (
    _clampPointToRect(top, pageRect),
    _clampPointToRect(bottom, pageRect),
  );
}

Offset _transformLocalPointToViewport({
  required Offset point,
  required Offset anchor,
  required double angle,
  required Rect pageRect,
}) {
  final translated = point - anchor;
  final rotated = Offset(
    translated.dx * math.cos(angle) + translated.dy * math.sin(angle),
    translated.dy * math.cos(angle) - translated.dx * math.sin(angle),
  );
  return pageRect.topLeft + anchor + rotated;
}

Offset _clampPointToRect(Offset point, Rect rect) {
  return Offset(
    point.dx.clamp(rect.left, rect.right).toDouble(),
    point.dy.clamp(rect.top, rect.bottom).toDouble(),
  );
}

List<Offset> _clipPageRectByLine({
  required Rect pageRect,
  required (Offset, Offset) line,
  required bool keepLeft,
}) {
  return _clipPolygonByLine(
    polygon: <Offset>[
      pageRect.topLeft,
      pageRect.topRight,
      pageRect.bottomRight,
      pageRect.bottomLeft,
    ],
    lineTop: line.$1,
    lineBottom: line.$2,
    keepLeft: keepLeft,
  );
}

List<Offset> _clipPolygonByLine({
  required List<Offset> polygon,
  required Offset lineTop,
  required Offset lineBottom,
  required bool keepLeft,
}) {
  if (polygon.isEmpty) {
    return const <Offset>[];
  }
  final result = <Offset>[];
  var previous = polygon.last;
  var previousInside = _isPointInsideLineSide(
    previous,
    lineTop,
    lineBottom,
    keepLeft: keepLeft,
  );
  for (final current in polygon) {
    final currentInside = _isPointInsideLineSide(
      current,
      lineTop,
      lineBottom,
      keepLeft: keepLeft,
    );
    if (currentInside != previousInside) {
      final intersection = _intersectSegmentWithLine(
        previous,
        current,
        lineTop,
        lineBottom,
      );
      if (intersection != null) {
        result.add(intersection);
      }
    }
    if (currentInside) {
      result.add(current);
    }
    previous = current;
    previousInside = currentInside;
  }
  return result;
}

bool _isPointInsideLineSide(
  Offset point,
  Offset lineTop,
  Offset lineBottom, {
  required bool keepLeft,
}) {
  final cross =
      (lineBottom.dx - lineTop.dx) * (point.dy - lineTop.dy) -
      (lineBottom.dy - lineTop.dy) * (point.dx - lineTop.dx);
  return keepLeft ? cross >= -0.001 : cross <= 0.001;
}

Offset? _intersectSegmentWithLine(
  Offset segmentStart,
  Offset segmentEnd,
  Offset lineStart,
  Offset lineEnd,
) {
  final segment = segmentEnd - segmentStart;
  final line = lineEnd - lineStart;
  final denominator = segment.dx * line.dy - segment.dy * line.dx;
  if (denominator.abs() < 0.0001) {
    return null;
  }
  final delta = lineStart - segmentStart;
  final t = (delta.dx * line.dy - delta.dy * line.dx) / denominator;
  if (t < -0.001 || t > 1.001) {
    return null;
  }
  return Offset(
    segmentStart.dx + segment.dx * t.clamp(0.0, 1.0),
    segmentStart.dy + segment.dy * t.clamp(0.0, 1.0),
  );
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
