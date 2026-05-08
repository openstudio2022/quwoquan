import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class BackwardRenderFrameData {
  const BackwardRenderFrameData({
    required this.localPagePoint,
    required this.progress,
    required this.orientation,
    required this.corner,
    required this.pageSize,
    required this.flippingClipArea,
    required this.bottomClipArea,
    required this.flippingAnchor,
    required this.bottomAnchor,
    required this.angle,
    required this.foldLine,
    required this.freeEdgeLine,
    required this.maxShadowOpacity,
    this.shadow,
  });

  final ui.Offset localPagePoint;
  final double progress;
  final StPageFlipOrientation orientation;
  final StPageFlipCorner corner;
  final ui.Size pageSize;
  final List<ui.Offset> flippingClipArea;
  final List<ui.Offset> bottomClipArea;
  final ui.Offset flippingAnchor;
  final ui.Offset bottomAnchor;
  final double angle;
  final (ui.Offset, ui.Offset)? foldLine;
  final (ui.Offset, ui.Offset)? freeEdgeLine;
  final double maxShadowOpacity;
  final StPageFlipShadowData? shadow;
}

/// Builds a backward [StPageFlipRenderFrame] from the native BACK
/// [StPageFlipCalculation] outputs. Backward is a first-class paper-fold
/// direction; it must not recreate a forward calculation and mirror it.
StPageFlipRenderFrame buildBackwardRenderFrame(BackwardRenderFrameData data) {
  return _buildBackwardRenderFrame(data);
}

StPageFlipRenderFrame buildBackwardDynamicRenderFrame(
  BackwardRenderFrameData data,
) {
  return _buildBackwardRenderFrame(data);
}

ui.Rect? _polygonAxisBounds(List<ui.Offset> polygon) {
  if (polygon.isEmpty) {
    return null;
  }
  var left = polygon.first.dx;
  var top = polygon.first.dy;
  var right = left;
  var bottom = top;
  for (final point in polygon.skip(1)) {
    left = left < point.dx ? left : point.dx;
    top = top < point.dy ? top : point.dy;
    right = right > point.dx ? right : point.dx;
    bottom = bottom > point.dy ? bottom : point.dy;
  }
  return ui.Rect.fromLTRB(left, top, right, bottom);
}

(ui.Offset, ui.Offset) _orderLineTopToBottom((ui.Offset, ui.Offset) line) {
  if (line.$1.dy < line.$2.dy) {
    return line;
  }
  if (line.$1.dy > line.$2.dy) {
    return (line.$2, line.$1);
  }
  return line.$1.dx <= line.$2.dx ? line : (line.$2, line.$1);
}

double _lineAverageX((ui.Offset, ui.Offset) line) =>
    (line.$1.dx + line.$2.dx) / 2;

double _resolveRectoCoverageFromFoldLine({
  required (ui.Offset, ui.Offset) foldLine,
  required ui.Size pageSize,
}) {
  if (pageSize.width <= 0) {
    return 0.0;
  }
  final coveredWidth = (_lineAverageX(foldLine) / pageSize.width)
      .clamp(0.0, 1.0)
      .toDouble();
  if (coveredWidth <= 0.5) {
    return 0.0;
  }
  return (2.0 - 1.0 / coveredWidth).clamp(0.0, 1.0).toDouble();
}

(ui.Offset, ui.Offset) _interpolateBoundaryLine({
  required (ui.Offset, ui.Offset) startLine,
  required (ui.Offset, ui.Offset) endLine,
  required double t,
}) {
  final clampedT = t.clamp(0.0, 1.0).toDouble();
  ui.Offset lerp(ui.Offset a, ui.Offset b) => ui.Offset(
    ui.lerpDouble(a.dx, b.dx, clampedT) ?? a.dx,
    ui.lerpDouble(a.dy, b.dy, clampedT) ?? a.dy,
  );
  return _orderLineTopToBottom((
    lerp(startLine.$1, endLine.$1),
    lerp(startLine.$2, endLine.$2),
  ));
}

StPageFlipRenderFrame _buildBackwardRenderFrame(BackwardRenderFrameData data) {
  final progress = data.progress.clamp(0.0, 1.0).toDouble();
  final renderDirection = resolvePageFlipRenderDirection(
    direction: StPageFlipDirection.back,
    orientation: data.orientation,
    reversePose: null,
  );

  final backwardLeafFrame = resolveArticlePageBackwardLeafFrame(
    direction: StPageFlipDirection.back,
    progress: progress,
    reversePose: null,
  )!;
  final backwardProjectedFrame = _buildBackwardProjectedFrame(
    localPagePoint: data.localPagePoint,
    previousFoldSurfaceArea: data.flippingClipArea,
    currentResidualArea: data.bottomClipArea,
    foldLine: data.foldLine,
    freeEdgeLine: data.freeEdgeLine,
    pageSize: data.pageSize,
  );

  final angleBand = resolveForwardCurlAngleBand(
    localPagePoint: resolveBackwardReplayLocalPagePoint(
      localPagePoint: data.localPagePoint,
      pageSize: data.pageSize,
    ),
    pageSize: data.pageSize,
    corner: data.corner,
  );

  return StPageFlipRenderFrame(
    localPagePoint: data.localPagePoint,
    progress: progress,
    direction: StPageFlipDirection.back,
    renderDirection: renderDirection,
    corner: data.corner,
    flippingClipArea: List<ui.Offset>.unmodifiable(data.flippingClipArea),
    bottomClipArea: List<ui.Offset>.unmodifiable(data.bottomClipArea),
    flippingAnchor: data.flippingAnchor,
    bottomAnchor: data.bottomAnchor,
    angle: data.angle,
    shadow: data.shadow,
    timeline: resolvePageCurlTimeline(
      direction: StPageFlipDirection.back,
      renderDirection: renderDirection,
      progress: progress,
      localPagePoint: data.localPagePoint,
      pageSize: data.pageSize,
      corner: data.corner,
      angleBand: angleBand,
      reversePose: null,
    ),
    reversePose: null,
    backwardLeafFrame: backwardLeafFrame,
    backwardProjectedFrame: backwardProjectedFrame,
  );
}

ArticlePageBackwardProjectedFrame? _buildBackwardProjectedFrame({
  required ui.Offset localPagePoint,
  required List<ui.Offset> previousFoldSurfaceArea,
  required List<ui.Offset> currentResidualArea,
  required (ui.Offset, ui.Offset)? foldLine,
  required (ui.Offset, ui.Offset)? freeEdgeLine,
  required ui.Size pageSize,
}) {
  if (pageSize.width <= 0 || pageSize.height <= 0) {
    return null;
  }
  final canonicalFoldLine = foldLine == null
      ? null
      : _clipLineToPageRect(_orderLineTopToBottom(foldLine), pageSize);
  final canonicalFreeEdgeLine = freeEdgeLine == null
      ? null
      : _clipLineToPageRect(_orderLineTopToBottom(freeEdgeLine), pageSize);
  final canonicalSpineLine = _orderLineTopToBottom((
    ui.Offset.zero,
    ui.Offset(0, pageSize.height),
  ));
  if (canonicalFoldLine == null || canonicalFreeEdgeLine == null) {
    return null;
  }
  final frontBackBoundaryFactor = _resolveRectoCoverageFromFoldLine(
    foldLine: canonicalFoldLine,
    pageSize: pageSize,
  );
  final canonicalFrontBackBoundaryLine = _interpolateBoundaryLine(
    startLine: canonicalSpineLine,
    endLine: canonicalFoldLine,
    t: frontBackBoundaryFactor,
  );
  final resolvedFoldSurfacePolygon = _clipPolygonToPageRect(
    previousFoldSurfaceArea,
    pageSize,
  );
  if (resolvedFoldSurfacePolygon.isEmpty) {
    return null;
  }

  final spineMid = ui.Offset(0, pageSize.height / 2);
  final backCandidate = frontBackBoundaryFactor <= 0.001
      ? resolvedFoldSurfacePolygon
      : _clipPolygonByLine(
          polygon: resolvedFoldSurfacePolygon,
          line: canonicalFrontBackBoundaryLine,
          keepPositive:
              _lineSide(
                _lineMidpoint(canonicalFoldLine),
                canonicalFrontBackBoundaryLine,
              ) >=
              0,
        );
  final frontCandidate = frontBackBoundaryFactor > 0.001
      ? _clipPolygonByLine(
          polygon: resolvedFoldSurfacePolygon,
          line: canonicalFrontBackBoundaryLine,
          keepPositive:
              _lineSide(spineMid, canonicalFrontBackBoundaryLine) >= 0,
        )
      : const <ui.Offset>[];
  final hasValidSplit =
      frontBackBoundaryFactor > 0.001 &&
      backCandidate.length >= 3 &&
      frontCandidate.length >= 3;
  final previousBackFoldPolygon = hasValidSplit
      ? backCandidate
      : resolvedFoldSurfacePolygon;
  final resolvedFrontFoldPolygon = hasValidSplit
      ? frontCandidate
      : const <ui.Offset>[];
  final currentResidualPolygon = _clipPolygonToPageRect(
    currentResidualArea,
    pageSize,
  );
  return ArticlePageBackwardProjectedFrame(
    foldLine: canonicalFoldLine,
    projectedRightEdgeLine: canonicalFreeEdgeLine,
    frontBackBoundaryLine: canonicalFrontBackBoundaryLine,
    foldSurfaceMovingEdgeLine: canonicalFreeEdgeLine,
    replayLocalPoint: localPagePoint,
    previousBackPagePolygon: const <ui.Offset>[],
    previousLaidFrontPolygon: const <ui.Offset>[],
    previousFoldSurfacePolygon: resolvedFoldSurfacePolygon,
    previousBackFoldPolygon: previousBackFoldPolygon,
    previousFrontFoldPolygon: resolvedFrontFoldPolygon,
    previousBackPolygon: previousBackFoldPolygon,
    previousFrontPolygon: resolvedFrontFoldPolygon,
    currentResidualPolygon: currentResidualPolygon,
    edgeEnteredPage:
        previousBackFoldPolygon.isNotEmpty ||
        resolvedFrontFoldPolygon.isNotEmpty,
    foldLineSource: 'backwardCanonicalFoldLine',
    edgeLineSource: 'backwardCanonicalFreeEdgeLine',
  );
}

(ui.Offset, ui.Offset)? _clipLineToPageRect(
  (ui.Offset, ui.Offset) line,
  ui.Size pageSize,
) {
  final orderedLine = _orderLineTopToBottom(line);
  final bounds = ui.Rect.fromLTWH(
    -0.5,
    -0.5,
    pageSize.width + 1,
    pageSize.height + 1,
  );
  final rectEdges = <List<ui.Offset>>[
    <ui.Offset>[ui.Offset.zero, ui.Offset(pageSize.width, 0)],
    <ui.Offset>[
      ui.Offset(pageSize.width, 0),
      ui.Offset(pageSize.width, pageSize.height),
    ],
    <ui.Offset>[
      ui.Offset(pageSize.width, pageSize.height),
      ui.Offset(0, pageSize.height),
    ],
    <ui.Offset>[ui.Offset(0, pageSize.height), ui.Offset.zero],
  ];
  final intersections = <ui.Offset>[];
  for (final edge in rectEdges) {
    ui.Offset? point;
    try {
      point = pointInRect(
        bounds,
        intersectLines(<ui.Offset>[orderedLine.$1, orderedLine.$2], edge),
      );
    } catch (_) {
      continue;
    }
    if (point != null &&
        intersections.every(
          (existing) => distanceBetweenPoints(existing, point) > 0.5,
        )) {
      intersections.add(point);
    }
  }
  if (intersections.length >= 2) {
    intersections.sort((a, b) {
      final byY = a.dy.compareTo(b.dy);
      return byY == 0 ? a.dx.compareTo(b.dx) : byY;
    });
    return _orderLineTopToBottom((intersections.first, intersections.last));
  }
  final insidePoints = <ui.Offset>[
    if (pointInRect(bounds, orderedLine.$1) != null) orderedLine.$1,
    if (pointInRect(bounds, orderedLine.$2) != null) orderedLine.$2,
  ];
  if (insidePoints.length >= 2) {
    return _orderLineTopToBottom((insidePoints.first, insidePoints.last));
  }
  if (intersections.length == 1 && insidePoints.length == 1) {
    return _orderLineTopToBottom((intersections.first, insidePoints.first));
  }
  return null;
}

ui.Offset _lineMidpoint((ui.Offset, ui.Offset) line) {
  return ui.Offset(
    (line.$1.dx + line.$2.dx) / 2,
    (line.$1.dy + line.$2.dy) / 2,
  );
}

List<ui.Offset> _buildCurrentResidualFromMovingEdge({
  required (ui.Offset, ui.Offset)? movingEdgeLine,
  required ui.Size pageSize,
}) {
  if (movingEdgeLine == null) {
    return const <ui.Offset>[];
  }
  final fullPage = <ui.Offset>[
    ui.Offset.zero,
    ui.Offset(pageSize.width, 0),
    ui.Offset(pageSize.width, pageSize.height),
    ui.Offset(0, pageSize.height),
  ];
  final spineMid = ui.Offset(0, pageSize.height / 2);
  final spinePositive = _lineSide(spineMid, movingEdgeLine) >= 0;
  return _clipPolygonByLine(
    polygon: fullPage,
    line: movingEdgeLine,
    keepPositive: !spinePositive,
  );
}

double _lineSide(ui.Offset point, (ui.Offset, ui.Offset) line) {
  final a = line.$1;
  final b = line.$2;
  return (b.dx - a.dx) * (point.dy - a.dy) - (b.dy - a.dy) * (point.dx - a.dx);
}

List<ui.Offset> _clipPolygonByLine({
  required List<ui.Offset> polygon,
  required (ui.Offset, ui.Offset) line,
  required bool keepPositive,
}) {
  if (polygon.length < 3) {
    return const <ui.Offset>[];
  }
  const epsilon = 0.0001;
  final clipped = <ui.Offset>[];
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
          ui.Offset(
            current.dx + (next.dx - current.dx) * t,
            current.dy + (next.dy - current.dy) * t,
          ),
        );
      }
    }
  }

  /// Do not apply [_validPolygon] bbox heuristics here: folding clips can be
  /// valid thin strips that still participate in the shared BACK sheet.
  if (clipped.length < 3) {
    return const <ui.Offset>[];
  }
  return List<ui.Offset>.unmodifiable(clipped);
}

List<ui.Offset> _clipPolygonToPageRect(
  List<ui.Offset> polygon,
  ui.Size pageSize,
) {
  final valid = _validPolygon(polygon);
  if (valid.isEmpty) {
    return const <ui.Offset>[];
  }
  final clippedLeft = _clipPolygonByLine(
    polygon: valid,
    line: (ui.Offset.zero, ui.Offset(0, pageSize.height)),
    keepPositive: false,
  );
  final clippedRight = _clipPolygonByLine(
    polygon: clippedLeft,
    line: (
      ui.Offset(pageSize.width, 0),
      ui.Offset(pageSize.width, pageSize.height),
    ),
    keepPositive: true,
  );
  final clippedTop = _clipPolygonByLine(
    polygon: clippedRight,
    line: (ui.Offset.zero, ui.Offset(pageSize.width, 0)),
    keepPositive: true,
  );
  return _clipPolygonByLine(
    polygon: clippedTop,
    line: (
      ui.Offset(0, pageSize.height),
      ui.Offset(pageSize.width, pageSize.height),
    ),
    keepPositive: false,
  );
}

List<ui.Offset> _validPolygon(List<ui.Offset> polygon) {
  if (polygon.length < 3) {
    return const <ui.Offset>[];
  }
  var minX = polygon.first.dx;
  var maxX = polygon.first.dx;
  var minY = polygon.first.dy;
  var maxY = polygon.first.dy;
  for (final point in polygon.skip(1)) {
    minX = minX < point.dx ? minX : point.dx;
    maxX = maxX > point.dx ? maxX : point.dx;
    minY = minY < point.dy ? minY : point.dy;
    maxY = maxY > point.dy ? maxY : point.dy;
  }
  if ((maxX - minX).abs() < 0.5 || (maxY - minY).abs() < 0.5) {
    return const <ui.Offset>[];
  }
  return List<ui.Offset>.unmodifiable(polygon);
}
