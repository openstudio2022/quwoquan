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

BackwardFoldSurfaceGeometry? resolveBackwardFoldFrameGeometry({
  required List<Offset> flippingArea,
  required List<Offset> bottomArea,
  required Offset anchor,
  required double angle,
  required StPageFlipBoundsRect bounds,
  required Size pageSize,
  required Rect pageViewportRect,
}) {
  if (flippingArea.length < 3 || bottomArea.length < 3) {
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
  final foldLineViewport = _resolveBottomAreaBoundaryLine(
    bottomArea: bottomArea,
    pageSize: pageSize,
    pageViewportRect: pageViewportRect,
  );
  if (foldLineViewport == null) {
    return null;
  }

  final pageEdgeViewport = _clampBackwardPageEdgeBeforeFold(
    edge: _resolveBackwardPageEdgeViewport(
      anchor: anchor,
      angle: angle,
      pageSize: pageSize,
      pageViewportRect: pageViewportRect,
    ),
    foldLine: foldLineViewport,
    pageViewportRect: pageViewportRect,
  );
  final pageEdgeLocal = _viewportLineToSoftLocal(
    pageEdgeViewport,
    softGeometry,
  );
  final foldLineLocal = _viewportLineToSoftLocal(
    foldLineViewport,
    softGeometry,
  );
  final resolvedBackLocalPolygon = <Offset>[
    pageEdgeLocal.$1,
    foldLineLocal.$1,
    foldLineLocal.$2,
    pageEdgeLocal.$2,
  ];

  final previousFrontLocalPolygon = _buildLeftPagePlanePolygonFromViewportLine(
    pageViewportRect: pageViewportRect,
    boundaryViewportLine: pageEdgeViewport,
  );
  final currentResidualPagePolygon = List<Offset>.unmodifiable(bottomArea);
  final previousFrontViewportPolygon = _pageLocalPolygonToViewport(
    previousFrontLocalPolygon,
    pageViewportRect,
  );
  final previousBackViewportPolygon = transformSoftLayerLocalPolygon(
    polygon: resolvedBackLocalPolygon,
    geometry: softGeometry,
  );
  final currentResidualViewportPolygon = _pageLocalPolygonToViewport(
    currentResidualPagePolygon,
    pageViewportRect,
  );

  return BackwardFoldSurfaceGeometry(
    softGeometry: softGeometry,
    sheetLocalPolygon: sheetLocalPolygon,
    previousFrontLocalPolygon: previousFrontLocalPolygon,
    previousBackLocalPolygon: resolvedBackLocalPolygon,
    currentResidualPagePolygon: currentResidualPagePolygon,
    foldLineLocal: foldLineLocal,
    frontBackBoundaryLocal: pageEdgeLocal,
    sheetViewportPolygon: sheetViewportPolygon,
    previousFrontViewportPolygon: previousFrontViewportPolygon,
    previousBackViewportPolygon: previousBackViewportPolygon,
    currentResidualViewportPolygon: currentResidualViewportPolygon,
    foldLineViewport: foldLineViewport,
    frontBackBoundaryViewport: pageEdgeViewport,
    sheetLocalBounds: polygonBounds(sheetLocalPolygon),
    previousFrontLocalBounds: polygonBounds(previousFrontLocalPolygon),
    previousBackLocalBounds: polygonBounds(resolvedBackLocalPolygon),
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

(Offset, Offset) _viewportLineToSoftLocal(
  (Offset, Offset) line,
  SoftPageLayerGeometry geometry,
) {
  return (
    _viewportPointToSoftLocal(line.$1, geometry),
    _viewportPointToSoftLocal(line.$2, geometry),
  );
}

(Offset, Offset) _resolveBackwardPageEdgeViewport({
  required Offset anchor,
  required double angle,
  required Size pageSize,
  required Rect pageViewportRect,
}) {
  Offset toCurrentPageViewport(Offset point) {
    return Offset(
      pageViewportRect.left + pageSize.width - point.dx,
      pageViewportRect.top + point.dy,
    );
  }

  final top = toCurrentPageViewport(anchor);
  final bottomBookPoint =
      anchor +
      Offset(
        pageSize.height * math.sin(angle),
        pageSize.height * math.cos(angle),
      );
  final bottom = toCurrentPageViewport(bottomBookPoint);
  return orderViewportLineTopToBottom((top, bottom));
}

(Offset, Offset) _clampBackwardPageEdgeBeforeFold({
  required (Offset, Offset) edge,
  required (Offset, Offset) foldLine,
  required Rect pageViewportRect,
}) {
  final orderedEdge = orderViewportLineTopToBottom(edge);
  final orderedFold = orderViewportLineTopToBottom(foldLine);
  final readableBackWidth = math.max(1.0, pageViewportRect.width * 0.16);
  Offset clampPoint(Offset point, Offset foldPoint) {
    final foldSpan = math.max(0.0, foldPoint.dx - pageViewportRect.left);
    final maxX = math.max(
      pageViewportRect.left,
      foldPoint.dx - readableBackWidth,
    );
    final readableFrontX = pageViewportRect.left + foldSpan * 0.28;
    final minX = math.min(readableFrontX, maxX);
    return Offset(
      point.dx.clamp(minX, maxX).toDouble(),
      point.dy.clamp(pageViewportRect.top, pageViewportRect.bottom).toDouble(),
    );
  }

  return orderViewportLineTopToBottom((
    clampPoint(orderedEdge.$1, orderedFold.$1),
    clampPoint(orderedEdge.$2, orderedFold.$2),
  ));
}

(Offset, Offset)? _resolveBottomAreaBoundaryLine({
  required List<Offset> bottomArea,
  required Size pageSize,
  required Rect pageViewportRect,
}) {
  if (bottomArea.length < 3) {
    return null;
  }
  final interior = bottomArea
      .where((point) {
        final onOuterEdge =
            point.dx.abs() <= 0.001 ||
            (point.dx - pageSize.width).abs() <= 0.001;
        final onHorizontalEdge =
            point.dy.abs() <= 0.001 ||
            (point.dy - pageSize.height).abs() <= 0.001;
        return !(onOuterEdge && onHorizontalEdge);
      })
      .toList(growable: false);
  final candidates = interior.length >= 2 ? interior : bottomArea;
  if (candidates.length < 2) {
    return null;
  }
  final minX = candidates.fold<double>(
    candidates.first.dx,
    (value, point) => math.min(value, point.dx),
  );
  final leftBoundary = candidates
      .where((point) => (point.dx - minX).abs() <= 0.001)
      .toList(growable: false);
  final sorted =
      [
        ...(leftBoundary.length >= 2
            ? leftBoundary
            : ([...candidates]..sort((a, b) => a.dx.compareTo(b.dx))).take(2)),
      ]..sort((a, b) {
        final byY = a.dy.compareTo(b.dy);
        return byY != 0 ? byY : a.dx.compareTo(b.dx);
      });
  return orderViewportLineTopToBottom((
    pageViewportRect.topLeft + sorted.first,
    pageViewportRect.topLeft + sorted.last,
  ));
}

List<Offset> _buildLeftPagePlanePolygonFromViewportLine({
  required Rect pageViewportRect,
  required (Offset, Offset) boundaryViewportLine,
}) {
  final boundary = orderViewportLineTopToBottom(boundaryViewportLine);
  final top = Offset(
    boundary.$1.dx.clamp(pageViewportRect.left, pageViewportRect.right),
    boundary.$1.dy.clamp(pageViewportRect.top, pageViewportRect.bottom),
  );
  final bottom = Offset(
    boundary.$2.dx.clamp(pageViewportRect.left, pageViewportRect.right),
    boundary.$2.dy.clamp(pageViewportRect.top, pageViewportRect.bottom),
  );
  final viewportPolygon = <Offset>[
    pageViewportRect.topLeft,
    top,
    bottom,
    pageViewportRect.bottomLeft,
  ];
  return viewportPolygon
      .map((point) => point - pageViewportRect.topLeft)
      .toList(growable: false);
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
