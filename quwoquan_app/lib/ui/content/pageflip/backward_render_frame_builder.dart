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
  final double maxShadowOpacity;
  final StPageFlipShadowData? shadow;
}

/// Builds a backward [StPageFlipRenderFrame] by reusing the forward
/// [StPageFlipCalculation] on a horizontally-mirrored drag point. This keeps
/// the geometry main line unified with the forward path: instead of a custom
/// 1D rectangular fold, the polygon clipping/intersection logic that already
/// drives the forward flip is reused, then mirrored back for the backward
/// rendering pipeline.
StPageFlipRenderFrame buildBackwardRenderFrame(BackwardRenderFrameData data) {
  return _buildBackwardRenderFrameMirrored(data, dynamicVariant: false);
}

StPageFlipRenderFrame buildBackwardDynamicRenderFrame(
  BackwardRenderFrameData data,
) {
  return _buildBackwardRenderFrameMirrored(data, dynamicVariant: true);
}

StPageFlipRenderFrame _buildBackwardRenderFrameMirrored(
  BackwardRenderFrameData data, {
  required bool dynamicVariant,
}) {
  final progress = data.progress.clamp(0.0, 1.0).toDouble();
  final renderDirection = resolvePageFlipRenderDirection(
    direction: StPageFlipDirection.back,
    orientation: data.orientation,
    reversePose: null,
  );
  final pageWidth = data.pageSize.width;
  final pageHeight = data.pageSize.height;

  final replayLocalPoint = resolveBackwardReplayLocalPagePoint(
    localPagePoint: data.localPagePoint,
    pageSize: data.pageSize,
  );

  final forwardCalculation = StPageFlipCalculation(
    direction: StPageFlipDirection.forward,
    corner: data.corner,
    pageWidth: pageWidth,
    pageHeight: pageHeight,
  );
  final ok = forwardCalculation.calc(replayLocalPoint);
  final forwardFoldGeometry = forwardCalculation.getForwardFoldGeometry();

  late final List<ui.Offset> flippingClipArea;
  late final List<ui.Offset> bottomClipArea;
  late final ui.Offset bottomAnchor;
  late final double angle;
  if (ok) {
    flippingClipArea = _mirrorPolygonX(
      forwardCalculation.getFlippingClipArea(),
      pageWidth,
    );
    bottomClipArea = _mirrorPolygonX(
      forwardCalculation.getBottomClipArea(),
      pageWidth,
    );
    // Bottom layer for backward stays anchored at the right page's spine
    // (book-coords origin), mirroring the forward semantic where the bottom
    // layer stays put while the lifted polygon moves over it.
    bottomAnchor = ui.Offset.zero;
    angle = -forwardCalculation.getAngle();
  } else {
    // The forward calc rejects degenerate inputs (drag right at the corner
    // with no perpendicular displacement). Keep the mirrored-forward result
    // empty here and let the effective geometry below fall back to the
    // controller's backward calculation for this frame.
    flippingClipArea = const <ui.Offset>[];
    bottomClipArea = const <ui.Offset>[];
    bottomAnchor = ui.Offset.zero;
    angle = 0.0;
  }

  final effectiveFlippingClipArea = flippingClipArea.isEmpty
      ? data.flippingClipArea
      : flippingClipArea;
  final effectiveBottomClipArea = bottomClipArea.isEmpty
      ? data.bottomClipArea
      : bottomClipArea;

  // Backward leaf frame is retained for diagnostics/timeline only — it no
  // longer drives geometry. The unified mainline above is the source of truth
  // for all clipping/rotation values.
  final backwardLeafFrame = resolveArticlePageBackwardLeafFrame(
    direction: StPageFlipDirection.back,
    progress: progress,
    reversePose: null,
  );
  final backwardProjectedFrame = _buildBackwardProjectedFrame(
    forwardFoldGeometry: forwardFoldGeometry,
    fallbackForwardFoldLine: _resolveForwardFoldLineFromPosition(
      position: replayLocalPoint,
      corner: data.corner,
      pageSize: data.pageSize,
    ),
    previousBackArea: effectiveFlippingClipArea,
    progress: progress,
    pageSize: data.pageSize,
  );

  final angleBand = resolveForwardCurlAngleBand(
    localPagePoint: replayLocalPoint,
    pageSize: data.pageSize,
    corner: data.corner,
  );

  return StPageFlipRenderFrame(
    localPagePoint: data.localPagePoint,
    progress: progress,
    direction: StPageFlipDirection.back,
    renderDirection: renderDirection,
    corner: data.corner,
    flippingClipArea: List<ui.Offset>.unmodifiable(
      effectiveFlippingClipArea,
    ),
    bottomClipArea: List<ui.Offset>.unmodifiable(
      effectiveBottomClipArea,
    ),
    flippingAnchor: data.flippingAnchor,
    bottomAnchor: bottomAnchor,
    angle: ok ? angle : (dynamicVariant ? data.angle : 0.0),
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

ui.Offset _mirrorXOffset(ui.Offset point, double width) =>
    ui.Offset(width - point.dx, point.dy);

List<ui.Offset> _mirrorPolygonX(List<ui.Offset> polygon, double width) {
  if (polygon.isEmpty) {
    return const <ui.Offset>[];
  }
  return polygon.map((p) => _mirrorXOffset(p, width)).toList(growable: false);
}

ArticlePageBackwardProjectedFrame? _buildBackwardProjectedFrame({
  required StPageFlipFoldGeometry? forwardFoldGeometry,
  required (ui.Offset, ui.Offset)? fallbackForwardFoldLine,
  required List<ui.Offset> previousBackArea,
  required double progress,
  required ui.Size pageSize,
}) {
  final sourceFoldLine =
      forwardFoldGeometry?.foldLine ??
      fallbackForwardFoldLine ??
      (
        ui.Offset(pageSize.width * (1 - progress.clamp(0.0, 1.0)), 0),
        ui.Offset(
          pageSize.width * (1 - progress.clamp(0.0, 1.0)),
          pageSize.height,
        ),
      );
  if (pageSize.width <= 0 || pageSize.height <= 0) {
    return null;
  }
  final foldLine = _orderedTopToBottomLine(
    _mirrorLineX(sourceFoldLine, pageSize.width),
  );
  final pagePolygon = <ui.Offset>[
    ui.Offset.zero,
    ui.Offset(pageSize.width, 0),
    ui.Offset(pageSize.width, pageSize.height),
    ui.Offset(0, pageSize.height),
  ];
  final previousBackPolygon = _validPolygon(previousBackArea).isNotEmpty
      ? _validPolygon(previousBackArea)
      : _clipPolygonByLine(
          polygon: pagePolygon,
          line: foldLine,
          keepPositive:
              _lineSide(ui.Offset(0, pageSize.height / 2), foldLine) >= 0,
        );
  if (previousBackPolygon.isEmpty) {
    return null;
  }
  final originalPreviousRightEdgeLine =
    forwardFoldGeometry?.originalRightEdgeLine ??
        (
          ui.Offset(pageSize.width, 0),
          ui.Offset(pageSize.width, pageSize.height),
        );
  final projectedRightEdgeLine = _orderedTopToBottomLine((
    _reflectPointAcrossLine(originalPreviousRightEdgeLine.$1, foldLine),
    _reflectPointAcrossLine(originalPreviousRightEdgeLine.$2, foldLine),
  ));
  final keepFrontPositive =
      _lineSide(ui.Offset(0, pageSize.height / 2), projectedRightEdgeLine) >= 0;
  final previousFrontCandidate = _clipPolygonByLine(
    polygon: pagePolygon,
    line: projectedRightEdgeLine,
    keepPositive: keepFrontPositive,
  );
  final edgeEnteredPage = previousFrontCandidate.isNotEmpty;
  final previousFrontPolygon = edgeEnteredPage
      ? previousFrontCandidate
      : const <ui.Offset>[];
  final keepCurrentPositive =
      _lineSide(ui.Offset(pageSize.width, pageSize.height / 2), foldLine) >= 0;
  final currentResidualPolygon = _clipPolygonByLine(
    polygon: pagePolygon,
    line: foldLine,
    keepPositive: keepCurrentPositive,
  );
  return ArticlePageBackwardProjectedFrame(
    foldLine: foldLine,
    projectedRightEdgeLine: projectedRightEdgeLine,
    previousBackPolygon: previousBackPolygon,
    previousFrontPolygon: previousFrontPolygon,
    currentResidualPolygon: currentResidualPolygon,
    edgeEnteredPage: edgeEnteredPage,
    foldLineSource: 'forwardRealGeometryMirrored',
    edgeLineSource: 'reflectedOriginalRightEdge',
  );
}

(ui.Offset, ui.Offset) _mirrorLineX(
  (ui.Offset, ui.Offset) line,
  double width,
) => (_mirrorXOffset(line.$1, width), _mirrorXOffset(line.$2, width));

(ui.Offset, ui.Offset) _orderedTopToBottomLine((ui.Offset, ui.Offset) line) {
  if (line.$1.dy < line.$2.dy) {
    return line;
  }
  if (line.$1.dy > line.$2.dy) {
    return (line.$2, line.$1);
  }
  return line.$1.dx <= line.$2.dx ? line : (line.$2, line.$1);
}

(ui.Offset, ui.Offset)? _resolveForwardFoldLineFromPosition({
  required ui.Offset position,
  required StPageFlipCorner corner,
  required ui.Size pageSize,
}) {
  final originalCorner = corner == StPageFlipCorner.top
      ? ui.Offset(pageSize.width, 0)
      : ui.Offset(pageSize.width, pageSize.height);
  final dx = position.dx - originalCorner.dx;
  final dy = position.dy - originalCorner.dy;
  if ((dx * dx + dy * dy) <= 0.000001) {
    return null;
  }
  final midpoint = ui.Offset(
    (position.dx + originalCorner.dx) / 2,
    (position.dy + originalCorner.dy) / 2,
  );
  final direction = ui.Offset(-dy, dx);
  final line = (midpoint - direction * 10000, midpoint + direction * 10000);
  final edges = <(ui.Offset, ui.Offset)>[
    (ui.Offset.zero, ui.Offset(pageSize.width, 0)),
    (ui.Offset(pageSize.width, 0), ui.Offset(pageSize.width, pageSize.height)),
    (ui.Offset(pageSize.width, pageSize.height), ui.Offset(0, pageSize.height)),
    (ui.Offset(0, pageSize.height), ui.Offset.zero),
  ];
  final intersections = <ui.Offset>[];
  for (final edge in edges) {
    final point = _intersectInfiniteLines(line, edge);
    if (point == null ||
        point.dx < -0.5 ||
        point.dx > pageSize.width + 0.5 ||
        point.dy < -0.5 ||
        point.dy > pageSize.height + 0.5) {
      continue;
    }
    if (intersections.every((existing) => (existing - point).distance > 0.5)) {
      intersections.add(point);
    }
  }
  if (intersections.length < 2) {
    return null;
  }
  intersections.sort((a, b) {
    final byY = a.dy.compareTo(b.dy);
    return byY == 0 ? a.dx.compareTo(b.dx) : byY;
  });
  return (intersections.first, intersections.last);
}

ui.Offset? _intersectInfiniteLines(
  (ui.Offset, ui.Offset) a,
  (ui.Offset, ui.Offset) b,
) {
  final x1 = a.$1.dx;
  final y1 = a.$1.dy;
  final x2 = a.$2.dx;
  final y2 = a.$2.dy;
  final x3 = b.$1.dx;
  final y3 = b.$1.dy;
  final x4 = b.$2.dx;
  final y4 = b.$2.dy;
  final denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
  if (denominator.abs() <= 0.000001) {
    return null;
  }
  final px =
      ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) /
      denominator;
  final py =
      ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) /
      denominator;
  if (!px.isFinite || !py.isFinite) {
    return null;
  }
  return ui.Offset(px, py);
}

double _lineSide(ui.Offset point, (ui.Offset, ui.Offset) line) {
  final a = line.$1;
  final b = line.$2;
  return (b.dx - a.dx) * (point.dy - a.dy) - (b.dy - a.dy) * (point.dx - a.dx);
}

ui.Offset _projectPointToLine(ui.Offset point, (ui.Offset, ui.Offset) line) {
  final a = line.$1;
  final b = line.$2;
  final dx = b.dx - a.dx;
  final dy = b.dy - a.dy;
  final lengthSquared = dx * dx + dy * dy;
  if (lengthSquared <= 0.000001) {
    return a;
  }
  final t = ((point.dx - a.dx) * dx + (point.dy - a.dy) * dy) / lengthSquared;
  return ui.Offset(a.dx + dx * t, a.dy + dy * t);
}

ui.Offset _reflectPointAcrossLine(
  ui.Offset point,
  (ui.Offset, ui.Offset) line,
) {
  final projected = _projectPointToLine(point, line);
  return projected * 2 - point;
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
  return _validPolygon(clipped);
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
