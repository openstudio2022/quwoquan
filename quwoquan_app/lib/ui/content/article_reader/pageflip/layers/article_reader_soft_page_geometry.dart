import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

/// StPageFlip native soft render: page state `position` is converted with the
/// active direction. In portrait BACK, this maps the left-side previous page
/// onto the visible current page across the spine at the current page's left
/// edge. Do not force BACK through the forward projection.
StPageFlipDirection softLayerViewportDirection(StPageFlipDirection direction) {
  return direction;
}

Offset softLayerOrigin({
  required Offset anchor,
  required Size pageSize,
  required StPageFlipDirection direction,
  required bool isFlippingPage,
  required bool lockSpineLine,
}) {
  if (lockSpineLine) {
    return Offset.zero;
  }
  return anchor;
}

Alignment softLayerAlignment({
  required Offset anchor,
  required Size pageSize,
  required StPageFlipDirection direction,
  required bool isFlippingPage,
  required bool lockSpineLine,
}) {
  return Alignment.topLeft;
}

@immutable
class SoftPageLayerGeometry {
  const SoftPageLayerGeometry({
    required this.surfaceOrigin,
    required this.pivotLocal,
    required this.positionViewport,
    required this.surfaceViewportRect,
    required this.localClipPolygon,
    required this.viewportClipPolygon,
    required this.clipLocalBounds,
    required this.clipViewportBounds,
    required this.transform,
  });

  final Offset surfaceOrigin;
  final Offset pivotLocal;
  final Offset positionViewport;
  final Rect surfaceViewportRect;
  final List<Offset> localClipPolygon;
  final List<Offset> viewportClipPolygon;
  final Rect? clipLocalBounds;
  final Rect? clipViewportBounds;
  final Matrix4 transform;
}

// BACK does not use a separate geometry helper; it uses the same soft-layer
// pipeline with the direction-aware StPageFlip `drawSoft` local clip formula.

Offset rotatePointForCanvasTransform(Offset point, double angle) {
  final sinAngle = math.sin(angle);
  final cosAngle = math.cos(angle);
  return Offset(
    point.dx * cosAngle - point.dy * sinAngle,
    point.dx * sinAngle + point.dy * cosAngle,
  );
}

Rect? polygonBounds(List<Offset> polygon) {
  if (polygon.isEmpty) {
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
  return Rect.fromLTRB(left, top, right, bottom);
}

Offset transformSoftLayerLocalPoint({
  required Offset point,
  required SoftPageLayerGeometry geometry,
}) {
  final angle = rotationZFromMatrix(geometry.transform);
  final translated = point - geometry.pivotLocal;
  final rotated = rotatePointForCanvasTransform(translated, angle);
  return geometry.positionViewport + geometry.pivotLocal + rotated;
}

Offset inverseTransformSoftLayerLocalPoint({
  required Offset point,
  required SoftPageLayerGeometry geometry,
}) {
  final angle = rotationZFromMatrix(geometry.transform);
  final translated = point - geometry.surfaceOrigin;
  final unrotated = rotatePointForCanvasTransform(
    translated - geometry.pivotLocal,
    -angle,
  );
  return geometry.pivotLocal + unrotated;
}

List<Offset> transformSoftLayerLocalPolygon({
  required List<Offset> polygon,
  required SoftPageLayerGeometry geometry,
}) {
  return polygon
      .map(
        (point) =>
            transformSoftLayerLocalPoint(point: point, geometry: geometry),
      )
      .toList(growable: false);
}

double rotationZFromMatrix(Matrix4 transform) {
  return math.atan2(transform.entry(1, 0), transform.entry(0, 0));
}

bool linesAreParallel((Offset, Offset) a, (Offset, Offset) b) {
  final ax = a.$2.dx - a.$1.dx;
  final ay = a.$2.dy - a.$1.dy;
  final bx = b.$2.dx - b.$1.dx;
  final by = b.$2.dy - b.$1.dy;
  final cross = ax * by - ay * bx;
  final scale = math.sqrt(ax * ax + ay * ay) * math.sqrt(bx * bx + by * by);
  if (scale <= 0.000001) {
    return true;
  }
  return (cross / scale).abs() < 0.01;
}

double lineSide((Offset, Offset) line, Offset point) {
  final ax = line.$2.dx - line.$1.dx;
  final ay = line.$2.dy - line.$1.dy;
  final bx = point.dx - line.$1.dx;
  final by = point.dy - line.$1.dy;
  return ax * by - ay * bx;
}

bool keepPositiveSideForBackwardRecto({
  required (Offset, Offset) foldLine,
  (Offset, Offset)? freeEdgeLine,
  required Size pageSize,
}) {
  final safeFreeEdgeLine = freeEdgeLine;
  if (safeFreeEdgeLine != null) {
    final freeEdgeProbe = Offset(
      (safeFreeEdgeLine.$1.dx + safeFreeEdgeLine.$2.dx) / 2,
      (safeFreeEdgeLine.$1.dy + safeFreeEdgeLine.$2.dy) / 2,
    );
    return lineSide(foldLine, freeEdgeProbe) < 0;
  }
  final spineProbe = Offset(0, pageSize.height / 2);
  return lineSide(foldLine, spineProbe) >= 0;
}

bool polygonHasVisibleArea(List<Offset> polygon, {double minArea = 0.5}) {
  if (polygon.length < 3) {
    return false;
  }
  final bounds = polygonBounds(polygon);
  if (bounds == null || bounds.width <= 0.5 || bounds.height <= 0.5) {
    return false;
  }
  var doubledArea = 0.0;
  for (var index = 0; index < polygon.length; index += 1) {
    final current = polygon[index];
    final next = polygon[(index + 1) % polygon.length];
    doubledArea += current.dx * next.dy - next.dx * current.dy;
  }
  return (doubledArea.abs() / 2) > minArea;
}

bool polygonLooksLikeFullPageFallback(
  List<Offset> polygon, {
  required Size pageSize,
}) {
  final bounds = polygonBounds(polygon);
  if (bounds == null || pageSize.width <= 0 || pageSize.height <= 0) {
    return false;
  }
  return bounds.width >= pageSize.width * 0.92 &&
      bounds.height >= pageSize.height * 0.82;
}

List<Offset> pageRectPolygon(Size pageSize) {
  return <Offset>[
    Offset.zero,
    Offset(pageSize.width, 0),
    Offset(pageSize.width, pageSize.height),
    Offset(0, pageSize.height),
  ];
}

List<Offset> backwardFrontFlatPolygon({
  required Size pageSize,
  required (Offset, Offset)? foldLine,
  required (Offset, Offset)? freeEdgeLine,
}) {
  final safeFreeEdgeLine = freeEdgeLine;
  final safeFoldLine = foldLine;
  if (safeFreeEdgeLine == null || safeFoldLine == null) {
    return const <Offset>[];
  }
  var polygon = pageRectPolygon(pageSize);
  final spineProbe = Offset(0, pageSize.height / 2);
  polygon = clipPolygonByLine(
    polygon: polygon,
    line: safeFreeEdgeLine,
    keepPositiveSide: lineSide(safeFreeEdgeLine, spineProbe) >= 0,
  );
  if (!polygonHasVisibleArea(polygon)) {
    return const <Offset>[];
  }
  polygon = clipPolygonByLine(
    polygon: polygon,
    line: safeFoldLine,
    keepPositiveSide: lineSide(safeFoldLine, spineProbe) >= 0,
  );
  if (!polygonHasVisibleArea(polygon)) {
    return const <Offset>[];
  }
  return polygon;
}

List<Offset> backwardSheetRectoPolygon({
  required Size pageSize,
  required List<Offset> sheetLocalPolygon,
  required (Offset, Offset)? foldLine,
  required (Offset, Offset)? freeEdgeLine,
}) {
  final safeFoldLine = foldLine;
  if (safeFoldLine == null || sheetLocalPolygon.length < 3) {
    return const <Offset>[];
  }
  final keepPositiveForRecto = keepPositiveSideForBackwardRecto(
    foldLine: safeFoldLine,
    freeEdgeLine: freeEdgeLine,
    pageSize: pageSize,
  );
  final polygon = clipPolygonByLine(
    polygon: sheetLocalPolygon,
    line: safeFoldLine,
    keepPositiveSide: keepPositiveForRecto,
  );
  return polygonHasVisibleArea(polygon) ? polygon : const <Offset>[];
}

List<Offset> backwardSheetVersoPolygon({
  required Size pageSize,
  required List<Offset> sheetLocalPolygon,
  required (Offset, Offset)? foldLine,
  required (Offset, Offset)? freeEdgeLine,
}) {
  final safeFoldLine = foldLine;
  if (safeFoldLine == null || sheetLocalPolygon.length < 3) {
    return const <Offset>[];
  }
  final keepPositiveForRecto = keepPositiveSideForBackwardRecto(
    foldLine: safeFoldLine,
    freeEdgeLine: freeEdgeLine,
    pageSize: pageSize,
  );
  final foldSidePolygon = clipPolygonByLine(
    polygon: sheetLocalPolygon,
    line: safeFoldLine,
    keepPositiveSide: !keepPositiveForRecto,
  );
  if (!polygonHasVisibleArea(foldSidePolygon)) {
    return const <Offset>[];
  }

  final safeFreeEdgeLine = freeEdgeLine;
  if (safeFreeEdgeLine == null) {
    return const <Offset>[];
  }
  final foldProbe = Offset(
    (safeFoldLine.$1.dx + safeFoldLine.$2.dx) / 2,
    (safeFoldLine.$1.dy + safeFoldLine.$2.dy) / 2,
  );
  final keepSideContainingFold = lineSide(safeFreeEdgeLine, foldProbe) >= 0;
  final edgeBoundedPolygon = clipPolygonByLine(
    polygon: foldSidePolygon,
    line: safeFreeEdgeLine,
    keepPositiveSide: keepSideContainingFold,
  );
  if (polygonHasVisibleArea(edgeBoundedPolygon) &&
      !polygonLooksLikeFullPageFallback(
        edgeBoundedPolygon,
        pageSize: pageSize,
      )) {
    return edgeBoundedPolygon;
  }

  return const <Offset>[];
}

typedef BackwardFoldFaceGeometry = ({
  List<Offset> sheetLocalPolygon,
  (Offset, Offset)? foldLine,
  (Offset, Offset)? freeEdgeLine,
  List<Offset> recto,
  List<Offset> verso,
});

BackwardFoldFaceGeometry backwardFoldFaceGeometry({
  required Size pageSize,
  required List<Offset> sheetLocalPolygon,
  required (Offset, Offset)? foldLine,
  required (Offset, Offset)? freeEdgeLine,
}) {
  return (
    sheetLocalPolygon: List<Offset>.unmodifiable(sheetLocalPolygon),
    foldLine: foldLine,
    freeEdgeLine: freeEdgeLine,
    recto: backwardSheetRectoPolygon(
      pageSize: pageSize,
      sheetLocalPolygon: sheetLocalPolygon,
      foldLine: foldLine,
      freeEdgeLine: freeEdgeLine,
    ),
    verso: backwardSheetVersoPolygon(
      pageSize: pageSize,
      sheetLocalPolygon: sheetLocalPolygon,
      foldLine: foldLine,
      freeEdgeLine: freeEdgeLine,
    ),
  );
}

List<Offset> clipPolygonByLine({
  required List<Offset> polygon,
  required (Offset, Offset) line,
  required bool keepPositiveSide,
}) {
  if (polygon.length < 3) {
    return const <Offset>[];
  }

  const epsilon = 0.0001;
  bool isInside(Offset point) {
    final side = lineSide(line, point);
    return keepPositiveSide ? side >= -epsilon : side <= epsilon;
  }

  Offset intersectSegmentWithLine(Offset start, Offset end) {
    final startSide = lineSide(line, start);
    final endSide = lineSide(line, end);
    final denominator = startSide - endSide;
    if (denominator.abs() <= epsilon) {
      return end;
    }
    final t = (startSide / denominator).clamp(0.0, 1.0).toDouble();
    return Offset(
      start.dx + (end.dx - start.dx) * t,
      start.dy + (end.dy - start.dy) * t,
    );
  }

  final output = <Offset>[];
  for (var index = 0; index < polygon.length; index += 1) {
    final current = polygon[index];
    final previous = polygon[(index + polygon.length - 1) % polygon.length];
    final currentInside = isInside(current);
    final previousInside = isInside(previous);

    if (currentInside) {
      if (!previousInside) {
        output.add(intersectSegmentWithLine(previous, current));
      }
      output.add(current);
    } else if (previousInside) {
      output.add(intersectSegmentWithLine(previous, current));
    }
  }

  return output.length < 3
      ? const <Offset>[]
      : List<Offset>.unmodifiable(output);
}

(Offset, Offset) orderViewportLineTopToBottom((Offset, Offset) line) {
  if (line.$1.dy < line.$2.dy) {
    return line;
  }
  if (line.$1.dy > line.$2.dy) {
    return (line.$2, line.$1);
  }
  return line.$1.dx <= line.$2.dx ? line : (line.$2, line.$1);
}
