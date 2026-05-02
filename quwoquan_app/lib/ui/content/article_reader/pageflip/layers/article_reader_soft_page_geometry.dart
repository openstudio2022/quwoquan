import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

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

@immutable
class BackwardFoldSurfaceGeometry {
  const BackwardFoldSurfaceGeometry({
    required this.softGeometry,
    required this.sheetLocalPolygon,
    required this.previousFrontLocalPolygon,
    required this.previousBackLocalPolygon,
    required this.currentResidualPagePolygon,
    required this.foldLineLocal,
    required this.frontBackBoundaryLocal,
    required this.sheetViewportPolygon,
    required this.previousFrontViewportPolygon,
    required this.previousBackViewportPolygon,
    required this.currentResidualViewportPolygon,
    required this.foldLineViewport,
    required this.frontBackBoundaryViewport,
    required this.sheetLocalBounds,
    required this.previousFrontLocalBounds,
    required this.previousBackLocalBounds,
    required this.currentResidualPageBounds,
    required this.sheetViewportBounds,
    required this.previousFrontViewportBounds,
    required this.previousBackViewportBounds,
    required this.currentResidualViewportBounds,
  });

  final SoftPageLayerGeometry softGeometry;
  final List<Offset> sheetLocalPolygon;
  final List<Offset> previousFrontLocalPolygon;
  final List<Offset> previousBackLocalPolygon;
  final List<Offset> currentResidualPagePolygon;
  final (Offset, Offset) foldLineLocal;
  final (Offset, Offset) frontBackBoundaryLocal;
  final List<Offset> sheetViewportPolygon;
  final List<Offset> previousFrontViewportPolygon;
  final List<Offset> previousBackViewportPolygon;
  final List<Offset> currentResidualViewportPolygon;
  final (Offset, Offset) foldLineViewport;
  final (Offset, Offset) frontBackBoundaryViewport;
  final Rect? sheetLocalBounds;
  final Rect? previousFrontLocalBounds;
  final Rect? previousBackLocalBounds;
  final Rect? currentResidualPageBounds;
  final Rect? sheetViewportBounds;
  final Rect? previousFrontViewportBounds;
  final Rect? previousBackViewportBounds;
  final Rect? currentResidualViewportBounds;
}

BackwardFoldSurfaceGeometry resolveBackwardFoldSurfaceGeometry({
  required List<Offset> sheetArea,
  required List<Offset> previousFrontArea,
  required List<Offset> previousBackArea,
  required List<Offset> currentResidualArea,
  required (Offset, Offset) foldLine,
  required (Offset, Offset) frontBackBoundaryLine,
  required Offset anchor,
  required double angle,
  required StPageFlipBoundsRect bounds,
  required Size pageSize,
  required Rect pageViewportRect,
}) {
  final softGeometry = resolveBackwardSoftPageGeometry(
    area: sheetArea,
    anchor: anchor,
    angle: angle,
    bounds: bounds,
    pageSize: pageSize,
  );
  List<Offset> toSoftLocalPolygon(List<Offset> polygon) {
    if (polygon.length < 3) {
      return const <Offset>[];
    }
    return List<Offset>.unmodifiable(
      polygon.map(
        (point) => Offset(anchor.dx - point.dx, point.dy - anchor.dy),
      ),
    );
  }

  (Offset, Offset) toSoftLocalLine((Offset, Offset) line) => (
    Offset(anchor.dx - line.$1.dx, line.$1.dy - anchor.dy),
    Offset(anchor.dx - line.$2.dx, line.$2.dy - anchor.dy),
  );

  final previousBackLocalPolygon = toSoftLocalPolygon(
    previousBackArea.length >= 3 ? previousBackArea : sheetArea,
  );
  final previousFrontLocalPolygon = toSoftLocalPolygon(previousFrontArea);
  final currentResidualPagePolygon = List<Offset>.unmodifiable(
    currentResidualArea,
  );
  final foldLineLocal = toSoftLocalLine(foldLine);
  final frontBackBoundaryLocal = toSoftLocalLine(frontBackBoundaryLine);
  final sheetViewportPolygon = transformSoftLayerLocalPolygon(
    polygon: softGeometry.localClipPolygon,
    geometry: softGeometry,
  );
  final previousBackViewportPolygon = transformSoftLayerLocalPolygon(
    polygon: previousBackLocalPolygon,
    geometry: softGeometry,
  );
  final previousFrontViewportPolygon = transformSoftLayerLocalPolygon(
    polygon: previousFrontLocalPolygon,
    geometry: softGeometry,
  );
  final currentResidualViewportPolygon = _shiftPolygon(
    currentResidualPagePolygon,
    pageViewportRect.topLeft,
  );
  final foldLineViewport = (
    transformSoftLayerLocalPoint(
      point: foldLineLocal.$1,
      geometry: softGeometry,
    ),
    transformSoftLayerLocalPoint(
      point: foldLineLocal.$2,
      geometry: softGeometry,
    ),
  );
  final frontBackBoundaryViewport = (
    transformSoftLayerLocalPoint(
      point: frontBackBoundaryLocal.$1,
      geometry: softGeometry,
    ),
    transformSoftLayerLocalPoint(
      point: frontBackBoundaryLocal.$2,
      geometry: softGeometry,
    ),
  );

  return BackwardFoldSurfaceGeometry(
    softGeometry: softGeometry,
    sheetLocalPolygon: softGeometry.localClipPolygon,
    previousFrontLocalPolygon: previousFrontLocalPolygon,
    previousBackLocalPolygon: previousBackLocalPolygon,
    currentResidualPagePolygon: currentResidualPagePolygon,
    foldLineLocal: foldLineLocal,
    frontBackBoundaryLocal: frontBackBoundaryLocal,
    sheetViewportPolygon: sheetViewportPolygon,
    previousFrontViewportPolygon: previousFrontViewportPolygon,
    previousBackViewportPolygon: previousBackViewportPolygon,
    currentResidualViewportPolygon: currentResidualViewportPolygon,
    foldLineViewport: orderViewportLineTopToBottom(foldLineViewport),
    frontBackBoundaryViewport: orderViewportLineTopToBottom(
      frontBackBoundaryViewport,
    ),
    sheetLocalBounds: softGeometry.clipLocalBounds,
    previousFrontLocalBounds: polygonBounds(previousFrontLocalPolygon),
    previousBackLocalBounds: polygonBounds(previousBackLocalPolygon),
    currentResidualPageBounds: polygonBounds(currentResidualPagePolygon),
    sheetViewportBounds: polygonBounds(sheetViewportPolygon),
    previousFrontViewportBounds: polygonBounds(previousFrontViewportPolygon),
    previousBackViewportBounds: polygonBounds(previousBackViewportPolygon),
    currentResidualViewportBounds: polygonBounds(
      currentResidualViewportPolygon,
    ),
  );
}

SoftPageLayerGeometry resolveBackwardSoftPageGeometry({
  required List<Offset> area,
  required Offset anchor,
  required double angle,
  required StPageFlipBoundsRect bounds,
  required Size pageSize,
}) {
  final pivotLocal = Offset.zero;
  final positionViewport = convertBookPointToViewport(
    anchor,
    bounds,
    direction: StPageFlipDirection.back,
  );
  final localClipPolygon = List<Offset>.unmodifiable(
    area.map((point) => Offset(anchor.dx - point.dx, point.dy - anchor.dy)),
  );
  final transform = Matrix4.identity()..rotateZ(angle);
  final viewportClipPolygon = localClipPolygon
      .map((point) {
        final rotated = rotatePointForCanvasTransform(point, angle);
        return positionViewport + rotated;
      })
      .toList(growable: false);
  return SoftPageLayerGeometry(
    surfaceOrigin: anchor,
    pivotLocal: pivotLocal,
    positionViewport: positionViewport,
    surfaceViewportRect: positionViewport & pageSize,
    localClipPolygon: localClipPolygon,
    viewportClipPolygon: viewportClipPolygon,
    clipLocalBounds: polygonBounds(localClipPolygon),
    clipViewportBounds: polygonBounds(viewportClipPolygon),
    transform: transform,
  );
}

List<Offset> _shiftPolygon(List<Offset> polygon, Offset delta) {
  return polygon.map((point) => point + delta).toList(growable: false);
}

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
