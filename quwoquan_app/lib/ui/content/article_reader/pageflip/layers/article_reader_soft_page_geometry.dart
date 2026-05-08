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
    required this.currentUnderlayRect,
    required this.foldLineLocal,
    required this.freeEdgeLineLocal,
    required this.frontBackBoundaryLocal,
    required this.sheetViewportPolygon,
    required this.previousFrontViewportPolygon,
    required this.previousBackViewportPolygon,
    required this.currentResidualViewportPolygon,
    required this.foldLineViewport,
    required this.freeEdgeLineViewport,
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
  final Rect currentUnderlayRect;
  final (Offset, Offset) foldLineLocal;
  final (Offset, Offset) freeEdgeLineLocal;
  final (Offset, Offset) frontBackBoundaryLocal;
  final List<Offset> sheetViewportPolygon;
  final List<Offset> previousFrontViewportPolygon;
  final List<Offset> previousBackViewportPolygon;
  final List<Offset> currentResidualViewportPolygon;
  final (Offset, Offset) foldLineViewport;
  final (Offset, Offset) freeEdgeLineViewport;
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

BackwardFoldSurfaceGeometry? resolveBackwardFoldFrameGeometry({
  required List<Offset> flippingArea,
  required List<Offset> bottomArea,
  required Offset anchor,
  required double angle,
  required (Offset, Offset) foldLine,
  required (Offset, Offset) freeEdgeLine,
  required (Offset, Offset) frontBackBoundaryLine,
  required double rectoCoverageNormalized,
  required StPageFlipBoundsRect bounds,
  required Size pageSize,
  required Rect pageViewportRect,
}) {
  // Ownership is derived from the frame boundary E; the legacy recto ratio is
  // kept in the signature for callers but must not open the front by itself.
  final _ = rectoCoverageNormalized;
  if (flippingArea.length < 3) {
    return null;
  }
  final softGeometry = resolveBackwardSoftPageGeometry(
    area: flippingArea,
    anchor: anchor,
    angle: angle,
    bounds: bounds,
    pageSize: pageSize,
  );
  final sheetLocalPolygon = softGeometry.localClipPolygon;
  final sheetViewportPolygon = transformSoftLayerLocalPolygon(
    polygon: sheetLocalPolygon,
    geometry: softGeometry,
  );
  final foldLineLocal = _pageLocalLineToBackwardSoftLocal(
    line: foldLine,
    anchor: anchor,
  );
  final freeEdgeLocal = _pageLocalLineToBackwardSoftLocal(
    line: freeEdgeLine,
    anchor: anchor,
  );
  final frontBackBoundaryLocal = _pageLocalLineToBackwardSoftLocal(
    line: frontBackBoundaryLine,
    anchor: anchor,
  );
  final frontVisible =
      _pageLineDistanceFromSpine(line: frontBackBoundaryLine) > 0.5;
  final backCandidate = frontVisible
      ? _buildBackwardBandLocalPolygon(
          sheetLocalPolygon: sheetLocalPolygon,
          foldLineLocal: foldLineLocal,
          frontBackBoundaryLocal: frontBackBoundaryLocal,
        )
      : sheetLocalPolygon;
  final frontCandidate = frontVisible
      ? _buildBackwardFrontLocalPolygon(
          sheetLocalPolygon: sheetLocalPolygon,
          frontBackBoundaryLocal: frontBackBoundaryLocal,
          spineProbeLocal: _pagePointToBackwardSoftLocal(
            Offset(0, pageSize.height / 2),
            anchor,
          ),
        )
      : const <Offset>[];
  final hasValidSplit =
      frontVisible && backCandidate.length >= 3 && frontCandidate.length >= 3;
  final previousBackLocalPolygon = hasValidSplit
      ? backCandidate
      : sheetLocalPolygon;
  final previousFrontLocalPolygon = hasValidSplit
      ? frontCandidate
      : const <Offset>[];
  final previousBackViewportPolygon = transformSoftLayerLocalPolygon(
    polygon: previousBackLocalPolygon,
    geometry: softGeometry,
  );
  final previousFrontViewportPolygon = previousFrontLocalPolygon.length >= 3
      ? transformSoftLayerLocalPolygon(
          polygon: previousFrontLocalPolygon,
          geometry: softGeometry,
        )
      : const <Offset>[];
  final fullPageRect = Rect.fromLTWH(0, 0, pageSize.width, pageSize.height);
  final currentResidualPagePolygon = _clipPolygonToRect(
    polygon: bottomArea,
    rect: fullPageRect,
  );
  final currentResidualViewportPolygon = _pageLocalPolygonToViewport(
    currentResidualPagePolygon,
    pageViewportRect,
  );
  final foldLineViewport = _softLocalLineToViewport(
    line: foldLineLocal,
    geometry: softGeometry,
  );
  final freeEdgeViewport = _softLocalLineToViewport(
    line: freeEdgeLocal,
    geometry: softGeometry,
  );
  final frontBackBoundaryViewport = _softLocalLineToViewport(
    line: frontBackBoundaryLocal,
    geometry: softGeometry,
  );

  return BackwardFoldSurfaceGeometry(
    softGeometry: softGeometry,
    sheetLocalPolygon: sheetLocalPolygon,
    previousFrontLocalPolygon: previousFrontLocalPolygon,
    previousBackLocalPolygon: previousBackLocalPolygon,
    currentResidualPagePolygon: currentResidualPagePolygon,
    currentUnderlayRect: pageViewportRect,
    foldLineLocal: foldLineLocal,
    freeEdgeLineLocal: freeEdgeLocal,
    frontBackBoundaryLocal: frontBackBoundaryLocal,
    sheetViewportPolygon: sheetViewportPolygon,
    previousFrontViewportPolygon: previousFrontViewportPolygon,
    previousBackViewportPolygon: previousBackViewportPolygon,
    currentResidualViewportPolygon: currentResidualViewportPolygon,
    foldLineViewport: foldLineViewport,
    freeEdgeLineViewport: freeEdgeViewport,
    frontBackBoundaryViewport: frontBackBoundaryViewport,
    sheetLocalBounds: polygonBounds(sheetLocalPolygon),
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

List<Offset> _pageLocalPolygonToViewport(List<Offset> polygon, Rect pageRect) {
  return polygon
      .map((point) => pageRect.topLeft + point)
      .toList(growable: false);
}

Offset _viewportPointToSoftLocal(Offset point, SoftPageLayerGeometry geometry) {
  final angle = rotationZFromMatrix(geometry.transform);
  return rotatePointForCanvasTransform(
    point - geometry.positionViewport,
    -angle,
  );
}

Offset _pagePointToBackwardSoftLocal(Offset point, Offset anchor) {
  return Offset(anchor.dx - point.dx, point.dy - anchor.dy);
}

(Offset, Offset) _pageLocalLineToBackwardSoftLocal({
  required (Offset, Offset) line,
  required Offset anchor,
}) {
  return orderViewportLineTopToBottom((
    _pagePointToBackwardSoftLocal(line.$1, anchor),
    _pagePointToBackwardSoftLocal(line.$2, anchor),
  ));
}

(Offset, Offset) _softLocalLineToViewport({
  required (Offset, Offset) line,
  required SoftPageLayerGeometry geometry,
}) {
  return orderViewportLineTopToBottom((
    transformSoftLayerLocalPoint(point: line.$1, geometry: geometry),
    transformSoftLayerLocalPoint(point: line.$2, geometry: geometry),
  ));
}

double _pageLineDistanceFromSpine({required (Offset, Offset) line}) {
  final averageX = (line.$1.dx + line.$2.dx) / 2;
  return averageX.abs();
}

(Offset, Offset) _viewportLineToSoftLocal(
  (Offset, Offset) line,
  SoftPageLayerGeometry geometry,
) {
  return (
    _viewportPointToSoftLocal(line.$1, geometry),
    _viewportPointToSoftLocal(line.$2, geometry),
  );
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

List<Offset> _buildBackwardBandViewportPolygon({
  required List<Offset> sheetViewportPolygon,
  required (Offset, Offset) foldLineViewport,
  required (Offset, Offset) freeEdgeViewport,
  required Rect pageViewportRect,
}) {
  final foldMid = Offset(
    (foldLineViewport.$1.dx + foldLineViewport.$2.dx) / 2,
    (foldLineViewport.$1.dy + foldLineViewport.$2.dy) / 2,
  );
  final freeEdgeMid = Offset(
    (freeEdgeViewport.$1.dx + freeEdgeViewport.$2.dx) / 2,
    (freeEdgeViewport.$1.dy + freeEdgeViewport.$2.dy) / 2,
  );
  final clippedByFreeEdge = _clipPolygonByLine(
    polygon: sheetViewportPolygon,
    line: freeEdgeViewport,
    keepPositive: _lineSide(foldMid, freeEdgeViewport) >= 0,
  );
  final clippedByFold = _clipPolygonByLine(
    polygon: clippedByFreeEdge,
    line: foldLineViewport,
    keepPositive: _lineSide(freeEdgeMid, foldLineViewport) >= 0,
  );
  final clippedToPage = _clipPolygonToRect(
    polygon: clippedByFold,
    rect: pageViewportRect,
  );
  if (clippedToPage.length >= 3) {
    return clippedToPage;
  }
  return _clipPolygonToRect(
    polygon: <Offset>[
      freeEdgeViewport.$1,
      foldLineViewport.$1,
      foldLineViewport.$2,
      freeEdgeViewport.$2,
    ],
    rect: pageViewportRect,
  );
}

List<Offset> _buildBackwardBandLocalPolygon({
  required List<Offset> sheetLocalPolygon,
  required (Offset, Offset) foldLineLocal,
  required (Offset, Offset) frontBackBoundaryLocal,
}) {
  final foldProbeLocal = Offset(
    (foldLineLocal.$1.dx + foldLineLocal.$2.dx) / 2,
    (foldLineLocal.$1.dy + foldLineLocal.$2.dy) / 2,
  );
  return _clipPolygonByLine(
    polygon: sheetLocalPolygon,
    line: frontBackBoundaryLocal,
    keepPositive: _lineSide(foldProbeLocal, frontBackBoundaryLocal) >= 0,
  );
}

List<Offset> _buildBackwardFrontLocalPolygon({
  required List<Offset> sheetLocalPolygon,
  required (Offset, Offset) frontBackBoundaryLocal,
  required Offset spineProbeLocal,
}) {
  return _clipPolygonByLine(
    polygon: sheetLocalPolygon,
    line: frontBackBoundaryLocal,
    keepPositive: _lineSide(spineProbeLocal, frontBackBoundaryLocal) >= 0,
  );
}

double _lineSide(Offset point, (Offset, Offset) line) {
  final a = line.$1;
  final b = line.$2;
  return (b.dx - a.dx) * (point.dy - a.dy) - (b.dy - a.dy) * (point.dx - a.dx);
}

List<Offset> _clipPolygonByLine({
  required List<Offset> polygon,
  required (Offset, Offset) line,
  required bool keepPositive,
}) {
  if (polygon.length < 3) {
    return const <Offset>[];
  }
  const epsilon = 0.0001;
  final clipped = <Offset>[];
  for (var index = 0; index < polygon.length; index += 1) {
    final current = polygon[index];
    final next = polygon[(index + 1) % polygon.length];
    final currentSide = _lineSide(current, line);
    final nextSide = _lineSide(next, line);
    final currentInside = keepPositive
        ? currentSide >= -epsilon
        : currentSide <= epsilon;
    final nextInside = keepPositive
        ? nextSide >= -epsilon
        : nextSide <= epsilon;
    if (currentInside) {
      clipped.add(current);
    }
    if (currentInside != nextInside) {
      final denominator = currentSide - nextSide;
      if (denominator.abs() > epsilon) {
        final t = currentSide / denominator;
        clipped.add(
          Offset(
            current.dx + (next.dx - current.dx) * t,
            current.dy + (next.dy - current.dy) * t,
          ),
        );
      }
    }
  }
  return clipped.length >= 3
      ? List<Offset>.unmodifiable(clipped)
      : const <Offset>[];
}

List<Offset> _clipPolygonToRect({
  required List<Offset> polygon,
  required Rect rect,
}) {
  final clippedLeft = _clipPolygonByLine(
    polygon: polygon,
    line: (Offset(rect.left, rect.top), Offset(rect.left, rect.bottom)),
    keepPositive: false,
  );
  final clippedRight = _clipPolygonByLine(
    polygon: clippedLeft,
    line: (Offset(rect.right, rect.top), Offset(rect.right, rect.bottom)),
    keepPositive: true,
  );
  final clippedTop = _clipPolygonByLine(
    polygon: clippedRight,
    line: (Offset(rect.left, rect.top), Offset(rect.right, rect.top)),
    keepPositive: true,
  );
  return _clipPolygonByLine(
    polygon: clippedTop,
    line: (Offset(rect.left, rect.bottom), Offset(rect.right, rect.bottom)),
    keepPositive: false,
  );
}
