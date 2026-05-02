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
    required this.movingEdgeLine,
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
  final (ui.Offset, ui.Offset)? movingEdgeLine;
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

(ui.Offset, ui.Offset) _shiftLineToAverageX(
  (ui.Offset, ui.Offset) line,
  double targetAverageX,
) {
  final dx = targetAverageX - _lineAverageX(line);
  return (line.$1 + ui.Offset(dx, 0), line.$2 + ui.Offset(dx, 0));
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
    movingEdgeLine: data.movingEdgeLine,
    frame: backwardLeafFrame,
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
  required (ui.Offset, ui.Offset)? movingEdgeLine,
  required ArticlePageBackwardLeafFrame frame,
  required ui.Size pageSize,
}) {
  if (pageSize.width <= 0 || pageSize.height <= 0) {
    return null;
  }
  final rawCanonicalMovingEdgeLine = movingEdgeLine == null
      ? null
      : _orderLineTopToBottom(movingEdgeLine);
  final canonicalMovingEdgeLine = rawCanonicalMovingEdgeLine == null
      ? null
      : _clipLineToPageRect(rawCanonicalMovingEdgeLine, pageSize);
  final previousFoldSurfaceCandidate = canonicalMovingEdgeLine == null
      ? _clipPolygonToPageRect(previousFoldSurfaceArea, pageSize)
      : _buildCanonicalBackwardSheetPolygon(
          movingEdgeLine: canonicalMovingEdgeLine,
          pageSize: pageSize,
        );
  final previousFoldSurfacePolygon = previousFoldSurfaceCandidate.isNotEmpty
      ? previousFoldSurfaceCandidate
      : _clipPolygonToPageRect(previousFoldSurfaceArea, pageSize);
  if (previousFoldSurfacePolygon.isEmpty) {
    return null;
  }
  final mirroredCurrentResidualPolygon = _clipPolygonToPageRect(
    currentResidualArea,
    pageSize,
  );
  final currentResidualPolygon = mirroredCurrentResidualPolygon.isNotEmpty
      ? mirroredCurrentResidualPolygon
      : _buildCurrentResidualFromMovingEdge(
          movingEdgeLine: canonicalMovingEdgeLine,
          pageSize: pageSize,
        );

  /// Fold progress [ArticlePageBackwardLeafFrame.rectoCoverageNormalized] is
  /// defined along the canonical BACK sheet between the spine and the
  /// calculation right edge.
  final sheetPageBounds = _polygonAxisBounds(previousFoldSurfacePolygon);
  final resolvedMovingEdgeLine =
      canonicalMovingEdgeLine ??
      _orderLineTopToBottom((
        ui.Offset(sheetPageBounds?.right ?? pageSize.width, 0),
        ui.Offset(sheetPageBounds?.right ?? pageSize.width, pageSize.height),
      ));
  final (ui.Offset, ui.Offset) foldLine;
  if (sheetPageBounds != null &&
      sheetPageBounds.width > 1e-3 &&
      sheetPageBounds.height > 1e-3) {
    final foldX =
        (sheetPageBounds.left +
                (_lineAverageX(resolvedMovingEdgeLine) - sheetPageBounds.left) *
                    frame.rectoCoverageNormalized)
            .clamp(sheetPageBounds.left, sheetPageBounds.right)
            .toDouble();
    foldLine = _shiftLineToAverageX(resolvedMovingEdgeLine, foldX);
  } else {
    final frontRevealX = pageSize.width * frame.rectoCoverageNormalized;
    foldLine = _shiftLineToAverageX(resolvedMovingEdgeLine, frontRevealX);
  }

  /// Page-space split, parallel to the moving paper edge so the front/back
  /// boundary stays on the same folded sheet instead of collapsing to a
  /// vertical progress rectangle.
  final movingEdgeMid = ui.Offset(
    (resolvedMovingEdgeLine.$1.dx + resolvedMovingEdgeLine.$2.dx) / 2,
    (resolvedMovingEdgeLine.$1.dy + resolvedMovingEdgeLine.$2.dy) / 2,
  );
  final keepMovingSidePositive = _lineSide(movingEdgeMid, foldLine) >= 0;
  final backClip = _clipPolygonByLine(
    polygon: previousFoldSurfacePolygon,
    line: foldLine,
    keepPositive: keepMovingSidePositive,
  );
  final frontClip = _clipPolygonByLine(
    polygon: previousFoldSurfacePolygon,
    line: foldLine,
    keepPositive: !keepMovingSidePositive,
  );
  List<ui.Offset> fallbackFrontClip() {
    if (sheetPageBounds == null) {
      return const <ui.Offset>[];
    }
    return <ui.Offset>[
      ui.Offset(sheetPageBounds.left, sheetPageBounds.top),
      foldLine.$1,
      foldLine.$2,
      ui.Offset(sheetPageBounds.left, sheetPageBounds.bottom),
    ];
  }

  late final List<ui.Offset> previousBackFoldPolygon;
  late final List<ui.Offset> previousFrontFoldPolygon;
  if (frame.rectoCoverageNormalized <= 0.02) {
    previousBackFoldPolygon = previousFoldSurfacePolygon;
    previousFrontFoldPolygon = const <ui.Offset>[];
  } else if (frame.rectoCoverageNormalized >= 0.98) {
    previousFrontFoldPolygon = frontClip.length >= 3
        ? frontClip
        : fallbackFrontClip();

    /// Keep >=3 verts so diagnostics bounds stay defined when line-clipping
    /// degenerates at the page edge.
    previousBackFoldPolygon = backClip.length >= 3
        ? backClip
        : previousFoldSurfacePolygon;
  } else {
    previousBackFoldPolygon = backClip.length >= 3
        ? backClip
        : previousFoldSurfacePolygon;
    previousFrontFoldPolygon = frontClip.length >= 3
        ? frontClip
        : fallbackFrontClip();
  }
  return ArticlePageBackwardProjectedFrame(
    foldLine: foldLine,
    projectedRightEdgeLine: resolvedMovingEdgeLine,
    foldSurfaceMovingEdgeLine: resolvedMovingEdgeLine,
    replayLocalPoint: localPagePoint,
    previousBackPagePolygon: const <ui.Offset>[],
    previousLaidFrontPolygon: const <ui.Offset>[],
    previousFoldSurfacePolygon: previousFoldSurfacePolygon,
    previousBackFoldPolygon: previousBackFoldPolygon,
    previousFrontFoldPolygon: previousFrontFoldPolygon,
    previousBackPolygon: previousBackFoldPolygon,
    previousFrontPolygon: previousFrontFoldPolygon,
    currentResidualPolygon: currentResidualPolygon,
    edgeEnteredPage: frame.rectoCoverageNormalized > 0.02,
    foldLineSource: 'backCalculationParallelBoundary',
    edgeLineSource: canonicalMovingEdgeLine == null
        ? 'degeneratePageRightEdgeFallback'
        : 'backCalculationRectRightEdge',
  );
}

List<ui.Offset> _buildCanonicalBackwardSheetPolygon({
  required (ui.Offset, ui.Offset) movingEdgeLine,
  required ui.Size pageSize,
}) {
  final sheet = <ui.Offset>[
    ui.Offset.zero,
    movingEdgeLine.$1,
    movingEdgeLine.$2,
    ui.Offset(0, pageSize.height),
  ];
  return _clipPolygonToPageRect(sheet, pageSize);
}

(ui.Offset, ui.Offset) _clipLineToPageRect(
  (ui.Offset, ui.Offset) line,
  ui.Size pageSize,
) {
  ui.Offset clampPoint(ui.Offset point) {
    return ui.Offset(
      point.dx.clamp(0.0, pageSize.width).toDouble(),
      point.dy.clamp(0.0, pageSize.height).toDouble(),
    );
  }

  return _orderLineTopToBottom((clampPoint(line.$1), clampPoint(line.$2)));
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
