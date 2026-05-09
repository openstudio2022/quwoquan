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

(Offset, Offset) orderViewportLineTopToBottom((Offset, Offset) line) {
  if (line.$1.dy < line.$2.dy) {
    return line;
  }
  if (line.$1.dy > line.$2.dy) {
    return (line.$2, line.$1);
  }
  return line.$1.dx <= line.$2.dx ? line : (line.$2, line.$1);
}
