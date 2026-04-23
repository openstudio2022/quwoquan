import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/reverse_curl_calculation.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class ArticlePageCurlMeshSurface {
  const ArticlePageCurlMeshSurface({
    required this.vertices,
    required this.maxDepth,
    required this.diagnostics,
  });

  final ui.Vertices vertices;
  final double maxDepth;
  final ArticlePageCurlSurfaceDiagnostics diagnostics;
}

@immutable
class ArticlePageCurlFrame {
  const ArticlePageCurlFrame({
    required this.frontSurface,
    required this.backSurface,
    required this.bottomClipPath,
    required this.frontBounds,
    required this.backBounds,
    required this.frontDiagnostics,
    required this.backDiagnostics,
    required this.foldXNormalized,
    required this.curlLift,
    required this.progress,
    required this.rollProgress,
    required this.cylinderProgress,
    required this.unfoldProgress,
    this.alignmentDiagnostics,
  });

  final ArticlePageCurlMeshSurface? frontSurface;
  final ArticlePageCurlMeshSurface? backSurface;
  final Path bottomClipPath;
  final Rect frontBounds;
  final Rect backBounds;
  final ArticlePageCurlSurfaceDiagnostics? frontDiagnostics;
  final ArticlePageCurlSurfaceDiagnostics? backDiagnostics;
  final double foldXNormalized;
  final double curlLift;
  final double progress;
  final double rollProgress;
  final double cylinderProgress;
  final double unfoldProgress;
  final ArticlePageCurlAlignmentDiagnostics? alignmentDiagnostics;
}

@immutable
class ArticlePageCurlAlignmentDiagnostics {
  const ArticlePageCurlAlignmentDiagnostics({
    required this.spineTopX,
    required this.spineBottomX,
    required this.seamTopX,
    required this.seamBottomX,
  });

  final double spineTopX;
  final double spineBottomX;
  final double seamTopX;
  final double seamBottomX;

  double get spineDelta => (spineTopX - spineBottomX).abs();

  double get seamDelta => (seamTopX - seamBottomX).abs();
}

@immutable
class ArticlePageCurlSurfaceDiagnostics {
  const ArticlePageCurlSurfaceDiagnostics({
    required this.bounds,
    required this.overflowLeft,
    required this.overflowRight,
    required this.overflowTop,
    required this.overflowBottom,
    required this.maxEdgeScale,
    required this.meanEdgeScale,
    required this.maxTriangleAreaScale,
    required this.meanTriangleAreaScale,
  });

  final Rect bounds;
  final double overflowLeft;
  final double overflowRight;
  final double overflowTop;
  final double overflowBottom;
  final double maxEdgeScale;
  final double meanEdgeScale;
  final double maxTriangleAreaScale;
  final double meanTriangleAreaScale;

  bool get hasOverflow =>
      overflowLeft > 0 ||
      overflowRight > 0 ||
      overflowTop > 0 ||
      overflowBottom > 0;
}

class ArticlePageCurlMeshBuilder {
  const ArticlePageCurlMeshBuilder({
    this.horizontalSegments = 34,
    this.verticalSegments = 18,
  });

  final int horizontalSegments;
  final int verticalSegments;

  ArticlePageCurlFrame build({
    required Rect pageRect,
    required Size pageSize,
    required Offset dragPoint,
    required double progress,
    required StPageFlipDirection direction,
    required StPageFlipCorner corner,
    Path? bottomClipPath,
    ReverseFlipPose? reversePose,
    StPageFlipRenderFrame? renderFrame,
    bool deriveBottomClipPathFromMesh = false,
  }) {
    final effectiveFrame = renderFrame;
    final effectiveDirection = effectiveFrame?.renderDirection ?? direction;
    final effectiveCorner = effectiveFrame?.corner ?? corner;
    final effectiveDragPoint = effectiveFrame?.localPagePoint ?? dragPoint;
    final angleBand =
        effectiveFrame?.timeline.curlAngleBand ??
        resolveForwardCurlAngleBand(
          localPagePoint: effectiveDragPoint,
          pageSize: pageSize,
          corner: effectiveCorner,
        );
    final settledProgress = (effectiveFrame?.progress ?? progress)
        .clamp(0.0, 1.0)
        .toDouble();
    final timeline = effectiveFrame == null
        ? _CurlTimeline.fromPageTimeline(
            resolvePageCurlTimeline(
              direction: effectiveDirection,
              renderDirection:
                  reversePose != null &&
                      effectiveDirection == StPageFlipDirection.back
                  ? StPageFlipDirection.forward
                  : effectiveDirection,
              progress: settledProgress,
              localPagePoint: effectiveDragPoint,
              pageSize: pageSize,
              corner: effectiveCorner,
              angleBand: angleBand,
              reversePose: reversePose,
            ),
            reversePose: reversePose,
          )
        : _CurlTimeline.fromRenderFrame(effectiveFrame);
    final backwardLeafFrame = effectiveDirection == StPageFlipDirection.back
        ? (effectiveFrame?.backwardLeafFrame ??
              resolveArticlePageBackwardLeafFrame(
                direction: StPageFlipDirection.back,
                progress: settledProgress,
              ))
        : null;
    final foldTheta = _resolveFoldTheta(timeline);
    final pointCount = (horizontalSegments + 1) * (verticalSegments + 1);
    final points = List<_CurlMeshPoint>.filled(
      pointCount,
      const _CurlMeshPoint.empty(),
      growable: false,
    );
    var pivotAccumulator = 0.0;
    var maxDepth = 0.0;

    for (var row = 0; row <= verticalSegments; row += 1) {
      final rowT = row / verticalSegments;
      final cornerInfluence = effectiveCorner == StPageFlipCorner.top
          ? 1 - rowT
          : rowT;
      final rowPivot =
          (timeline.basePivot + (1 - cornerInfluence) * timeline.diagonalExtent)
              .clamp(0.0, pageSize.width)
              .toDouble();
      final rowRadius =
          ui.lerpDouble(
            timeline.leadingRadius,
            timeline.trailingRadius,
            cornerInfluence,
          ) ??
          timeline.leadingRadius;
      final seamX = rowPivot + foldTheta * rowRadius;
      pivotAccumulator += rowPivot;
      for (var col = 0; col <= horizontalSegments; col += 1) {
        final columnT = col / horizontalSegments;
        final localX = pageSize.width * columnT;
        final localY = pageSize.height * rowT;
        final point = _projectPoint(
          pageRect: pageRect,
          pageSize: pageSize,
          localX: localX,
          localY: localY,
          rowPivot: rowPivot,
          rowRadius: rowRadius,
          seamX: seamX,
          foldTheta: foldTheta,
          corner: effectiveCorner,
          timeline: timeline,
          backwardLeafFrame: backwardLeafFrame,
        );
        points[_indexFor(row, col)] = point;
        maxDepth = math.max(maxDepth, point.depth);
      }
    }

    final frontPositions = <double>[];
    final frontTexCoords = <double>[];
    final backPositions = <double>[];
    final backTexCoords = <double>[];
    for (var row = 0; row < verticalSegments; row += 1) {
      for (var col = 0; col < horizontalSegments; col += 1) {
        final topLeft = points[_indexFor(row, col)];
        final topRight = points[_indexFor(row, col + 1)];
        final bottomRight = points[_indexFor(row + 1, col + 1)];
        final bottomLeft = points[_indexFor(row + 1, col)];
        _appendVisibleTriangle(
          frontPositions: frontPositions,
          frontTexCoords: frontTexCoords,
          backPositions: backPositions,
          backTexCoords: backTexCoords,
          timeline: timeline,
          a: topLeft,
          b: topRight,
          c: bottomRight,
        );
        _appendVisibleTriangle(
          frontPositions: frontPositions,
          frontTexCoords: frontTexCoords,
          backPositions: backPositions,
          backTexCoords: backTexCoords,
          timeline: timeline,
          a: topLeft,
          b: bottomRight,
          c: bottomLeft,
        );
      }
    }

    final foldXNormalized =
        backwardLeafFrame?.seamXNormalized ??
        (pivotAccumulator / (verticalSegments + 1) / pageSize.width)
            .clamp(0.0, 1.0)
            .toDouble();
    final meshDerivedBottomClipPath = _buildBottomClipPathFromMesh(
      points,
      pageRect,
    );
    final effectiveBottomClipPath = deriveBottomClipPathFromMesh
        ? meshDerivedBottomClipPath
        : bottomClipPath == null
        ? (Path()..addRect(pageRect))
        : Path.combine(
            PathOperation.intersect,
            Path()..addRect(pageRect),
            bottomClipPath,
          );
    final frontDiagnostics = _resolveSurfaceDiagnostics(
      positions: frontPositions,
      textureCoordinates: frontTexCoords,
      pageRect: pageRect,
    );
    final backDiagnostics = _resolveSurfaceDiagnostics(
      positions: backPositions,
      textureCoordinates: backTexCoords,
      pageRect: pageRect,
    );
    final alignmentDiagnostics = backwardLeafFrame == null
        ? null
        : _resolveBackwardAlignmentDiagnostics(
            pageRect: pageRect,
            pageSize: pageSize,
            corner: effectiveCorner,
            timeline: timeline,
            backwardLeafFrame: backwardLeafFrame,
          );
    return ArticlePageCurlFrame(
      frontSurface: _buildSurface(
        frontPositions,
        frontTexCoords,
        maxDepth,
        diagnostics: frontDiagnostics,
      ),
      backSurface: _buildSurface(
        backPositions,
        backTexCoords,
        maxDepth,
        diagnostics: backDiagnostics,
      ),
      bottomClipPath: effectiveBottomClipPath,
      frontBounds: _resolveBounds(frontPositions),
      backBounds: _resolveBounds(backPositions),
      frontDiagnostics: frontDiagnostics,
      backDiagnostics: backDiagnostics,
      foldXNormalized: foldXNormalized,
      curlLift: (maxDepth / math.max(pageSize.width * 0.32, 1.0))
          .clamp(0.0, 1.0)
          .toDouble(),
      progress: settledProgress,
      rollProgress: timeline.rollProgress,
      cylinderProgress: timeline.cylinderProgress,
      unfoldProgress: timeline.unfoldProgress,
      alignmentDiagnostics: alignmentDiagnostics,
    );
  }

  int _indexFor(int row, int col) {
    return row * (horizontalSegments + 1) + col;
  }

  ArticlePageCurlMeshSurface? _buildSurface(
    List<double> positions,
    List<double> textureCoordinates,
    double maxDepth, {
    required ArticlePageCurlSurfaceDiagnostics? diagnostics,
  }) {
    if (positions.isEmpty ||
        textureCoordinates.isEmpty ||
        diagnostics == null) {
      return null;
    }
    return ArticlePageCurlMeshSurface(
      vertices: ui.Vertices.raw(
        ui.VertexMode.triangles,
        Float32List.fromList(positions),
        textureCoordinates: Float32List.fromList(textureCoordinates),
      ),
      maxDepth: maxDepth,
      diagnostics: diagnostics,
    );
  }

  Rect _resolveBounds(List<double> positions) {
    if (positions.isEmpty) {
      return Rect.zero;
    }
    var minX = double.infinity;
    var maxX = -double.infinity;
    var minY = double.infinity;
    var maxY = -double.infinity;
    for (var index = 0; index < positions.length; index += 2) {
      final x = positions[index];
      final y = positions[index + 1];
      if (x < minX) {
        minX = x;
      }
      if (x > maxX) {
        maxX = x;
      }
      if (y < minY) {
        minY = y;
      }
      if (y > maxY) {
        maxY = y;
      }
    }
    return Rect.fromLTRB(minX, minY, maxX, maxY);
  }

  ArticlePageCurlSurfaceDiagnostics? _resolveSurfaceDiagnostics({
    required List<double> positions,
    required List<double> textureCoordinates,
    required Rect pageRect,
  }) {
    if (positions.isEmpty || textureCoordinates.isEmpty) {
      return null;
    }
    final bounds = _resolveBounds(positions);
    var maxEdgeScale = 0.0;
    var edgeScaleSum = 0.0;
    var edgeScaleCount = 0;
    var maxTriangleAreaScale = 0.0;
    var triangleAreaScaleSum = 0.0;
    var triangleAreaScaleCount = 0;

    Offset readPosition(int vertexIndex) {
      final offset = vertexIndex * 2;
      return Offset(positions[offset], positions[offset + 1]);
    }

    Offset readTexture(int vertexIndex) {
      final offset = vertexIndex * 2;
      return Offset(textureCoordinates[offset], textureCoordinates[offset + 1]);
    }

    void recordEdge(
      Offset projectedA,
      Offset projectedB,
      Offset textureA,
      Offset textureB,
    ) {
      final textureLength = (textureB - textureA).distance;
      if (textureLength <= 0.0001) {
        return;
      }
      final projectedLength = (projectedB - projectedA).distance;
      final scale = projectedLength / textureLength;
      maxEdgeScale = math.max(maxEdgeScale, scale);
      edgeScaleSum += scale;
      edgeScaleCount += 1;
    }

    double triangleArea(Offset a, Offset b, Offset c) {
      return ((b.dx - a.dx) * (c.dy - a.dy) - (b.dy - a.dy) * (c.dx - a.dx))
              .abs() /
          2;
    }

    final triangleCount = positions.length ~/ 6;
    for (
      var triangleIndex = 0;
      triangleIndex < triangleCount;
      triangleIndex += 1
    ) {
      final baseVertex = triangleIndex * 3;
      final projectedA = readPosition(baseVertex);
      final projectedB = readPosition(baseVertex + 1);
      final projectedC = readPosition(baseVertex + 2);
      final textureA = readTexture(baseVertex);
      final textureB = readTexture(baseVertex + 1);
      final textureC = readTexture(baseVertex + 2);

      recordEdge(projectedA, projectedB, textureA, textureB);
      recordEdge(projectedB, projectedC, textureB, textureC);
      recordEdge(projectedC, projectedA, textureC, textureA);

      final textureArea = triangleArea(textureA, textureB, textureC);
      if (textureArea <= 0.0001) {
        continue;
      }
      final projectedArea = triangleArea(projectedA, projectedB, projectedC);
      final areaScale = projectedArea / textureArea;
      maxTriangleAreaScale = math.max(maxTriangleAreaScale, areaScale);
      triangleAreaScaleSum += areaScale;
      triangleAreaScaleCount += 1;
    }

    return ArticlePageCurlSurfaceDiagnostics(
      bounds: bounds,
      overflowLeft: math.max(0.0, pageRect.left - bounds.left),
      overflowRight: math.max(0.0, bounds.right - pageRect.right),
      overflowTop: math.max(0.0, pageRect.top - bounds.top),
      overflowBottom: math.max(0.0, bounds.bottom - pageRect.bottom),
      maxEdgeScale: maxEdgeScale,
      meanEdgeScale: edgeScaleCount == 0 ? 0.0 : edgeScaleSum / edgeScaleCount,
      maxTriangleAreaScale: maxTriangleAreaScale,
      meanTriangleAreaScale: triangleAreaScaleCount == 0
          ? 0.0
          : triangleAreaScaleSum / triangleAreaScaleCount,
    );
  }

  void _appendVisibleTriangle({
    required List<double> frontPositions,
    required List<double> frontTexCoords,
    required List<double> backPositions,
    required List<double> backTexCoords,
    required _CurlTimeline timeline,
    required _CurlMeshPoint a,
    required _CurlMeshPoint b,
    required _CurlMeshPoint c,
  }) {
    final triangle = <_CurlMeshPoint>[a, b, c];
    final frontPolygon = _clipTriangleBySeam(
      triangle,
      keepBack: false,
      timeline: timeline,
    );
    if (frontPolygon.length >= 3) {
      _appendPolygon(
        frontPositions,
        frontTexCoords,
        frontPolygon,
        useVersoTexture: false,
      );
    }
    final backPolygon = _clipTriangleBySeam(
      triangle,
      keepBack: true,
      timeline: timeline,
    );
    if (backPolygon.length >= 3) {
      _appendPolygon(
        backPositions,
        backTexCoords,
        backPolygon,
        useVersoTexture: true,
      );
    }
  }

  List<_CurlMeshPoint> _clipTriangleBySeam(
    List<_CurlMeshPoint> triangle, {
    required bool keepBack,
    required _CurlTimeline timeline,
  }) {
    final output = <_CurlMeshPoint>[];
    var previous = triangle.last;
    var previousInside = keepBack
        ? previous.seamMetric >= 0
        : previous.seamMetric <= 0;
    for (final current in triangle) {
      final currentInside = keepBack
          ? current.seamMetric >= 0
          : current.seamMetric <= 0;
      if (currentInside != previousInside) {
        output.add(_interpolateAtTheta(previous, current, 0));
      }
      if (currentInside) {
        output.add(current);
      }
      previous = current;
      previousInside = currentInside;
    }
    return output;
  }

  void _appendPolygon(
    List<double> positions,
    List<double> textureCoordinates,
    List<_CurlMeshPoint> polygon, {
    required bool useVersoTexture,
  }) {
    if (polygon.length < 3) {
      return;
    }
    final anchor = polygon.first;
    for (var index = 1; index < polygon.length - 1; index += 1) {
      _appendTriangle(
        positions,
        textureCoordinates,
        anchor,
        polygon[index],
        polygon[index + 1],
        useVersoTexture: useVersoTexture,
      );
    }
  }

  _CurlMeshPoint _interpolateAtTheta(
    _CurlMeshPoint from,
    _CurlMeshPoint to,
    double targetSeamMetric,
  ) {
    final seamDelta = to.seamMetric - from.seamMetric;
    final t = seamDelta.abs() < 0.0001
        ? 0.0
        : ((targetSeamMetric - from.seamMetric) / seamDelta)
              .clamp(0.0, 1.0)
              .toDouble();
    Offset interpolateOffset(Offset a, Offset b) {
      return Offset(
        ui.lerpDouble(a.dx, b.dx, t) ?? a.dx,
        ui.lerpDouble(a.dy, b.dy, t) ?? a.dy,
      );
    }

    return _CurlMeshPoint(
      projected: interpolateOffset(from.projected, to.projected),
      rectoTexture: interpolateOffset(from.rectoTexture, to.rectoTexture),
      versoTexture: interpolateOffset(from.versoTexture, to.versoTexture),
      theta: ui.lerpDouble(from.theta, to.theta, t) ?? from.theta,
      seamMetric: targetSeamMetric,
      depth: ui.lerpDouble(from.depth, to.depth, t) ?? from.depth,
    );
  }

  void _appendTriangle(
    List<double> positions,
    List<double> textureCoordinates,
    _CurlMeshPoint a,
    _CurlMeshPoint b,
    _CurlMeshPoint c, {
    required bool useVersoTexture,
  }) {
    positions
      ..add(a.projected.dx)
      ..add(a.projected.dy)
      ..add(b.projected.dx)
      ..add(b.projected.dy)
      ..add(c.projected.dx)
      ..add(c.projected.dy);
    textureCoordinates
      ..add((useVersoTexture ? a.versoTexture : a.rectoTexture).dx)
      ..add((useVersoTexture ? a.versoTexture : a.rectoTexture).dy)
      ..add((useVersoTexture ? b.versoTexture : b.rectoTexture).dx)
      ..add((useVersoTexture ? b.versoTexture : b.rectoTexture).dy)
      ..add((useVersoTexture ? c.versoTexture : c.rectoTexture).dx)
      ..add((useVersoTexture ? c.versoTexture : c.rectoTexture).dy);
  }

  Path _buildBottomClipPathFromMesh(
    List<_CurlMeshPoint> points,
    Rect pageRect,
  ) {
    final pageRectPath = Path()..addRect(pageRect);
    final leafCoveragePath = _buildLeafCoveragePath(points);
    final clippedLeafCoverage = Path.combine(
      PathOperation.intersect,
      pageRectPath,
      leafCoveragePath,
    );
    return Path.combine(
      PathOperation.difference,
      pageRectPath,
      clippedLeafCoverage,
    );
  }

  Path _buildLeafCoveragePath(List<_CurlMeshPoint> points) {
    final outline = <Offset>[];
    for (var col = 0; col <= horizontalSegments; col += 1) {
      outline.add(points[_indexFor(0, col)].projected);
    }
    for (var row = 1; row <= verticalSegments; row += 1) {
      outline.add(points[_indexFor(row, horizontalSegments)].projected);
    }
    for (var col = horizontalSegments - 1; col >= 0; col -= 1) {
      outline.add(points[_indexFor(verticalSegments, col)].projected);
    }
    for (var row = verticalSegments - 1; row >= 1; row -= 1) {
      outline.add(points[_indexFor(row, 0)].projected);
    }
    if (outline.isEmpty) {
      return Path();
    }
    final path = Path()..moveTo(outline.first.dx, outline.first.dy);
    for (final point in outline.skip(1)) {
      path.lineTo(point.dx, point.dy);
    }
    path.close();
    return path;
  }

  _CurlMeshPoint _projectPoint({
    required Rect pageRect,
    required Size pageSize,
    required double localX,
    required double localY,
    required double rowPivot,
    required double rowRadius,
    required double seamX,
    required double foldTheta,
    required StPageFlipCorner corner,
    required _CurlTimeline timeline,
    required ArticlePageBackwardLeafFrame? backwardLeafFrame,
  }) {
    if (backwardLeafFrame != null) {
      return _projectBackwardReplayPoint(
        pageRect: pageRect,
        pageSize: pageSize,
        localX: localX,
        localY: localY,
        corner: corner,
        timeline: timeline,
        backwardLeafFrame: backwardLeafFrame,
      );
    }
    if (timeline.reversePose != null) {
      return _projectReversePoint(
        pageRect: pageRect,
        pageSize: pageSize,
        localX: localX,
        localY: localY,
        corner: corner,
        foldTheta: foldTheta,
        timeline: timeline,
      );
    }
    final rowCurlDistance = math.max(0.0, localX - rowPivot);
    final theta = math.min(math.pi, rowCurlDistance / math.max(rowRadius, 1.0));
    final foldDepth = theta <= 0 ? 0.0 : (1 - math.cos(foldTheta)) * rowRadius;
    final frontDepth = theta <= foldTheta
        ? theta <= 0
              ? 0.0
              : (1 - math.cos(theta)) * rowRadius
        : foldDepth;
    final rigidAngleT = timeline.forwardAngle == null
        ? 0.0
        : (timeline.forwardAngle!.abs() / math.pi).clamp(0.0, 1.0).toDouble();
    final backTravelMultiplier = ui.lerpDouble(1.18, 1.42, rigidAngleT) ?? 1.25;
    final backTravel = theta <= foldTheta
        ? 0.0
        : ((theta - foldTheta) / math.max(math.pi - foldTheta, 0.0001))
                  .clamp(0.0, 1.0)
                  .toDouble() *
              rowRadius *
              backTravelMultiplier;
    final curledX = theta <= foldTheta
        ? rowPivot - frontDepth
        : (rowPivot - foldDepth) - backTravel;
    final cornerFactor = corner == StPageFlipCorner.top
        ? 1 - (localY / math.max(pageSize.height, 1.0))
        : localY / math.max(pageSize.height, 1.0);
    final displayDepth = theta <= foldTheta ? frontDepth : foldDepth;
    final curlHeightOffset =
        (1 - cornerFactor) *
        displayDepth *
        (corner == StPageFlipCorner.top
            ? -timeline.heightLiftBias
            : timeline.heightLiftBias);
    final curlInfluence = (theta <= 0 ? 0.0 : (theta / math.pi))
        .clamp(0.0, 1.0)
        .toDouble();
    final effectiveX = timeline.mirrored ? pageSize.width - curledX : curledX;
    final rectoTexX = timeline.mirrored ? pageSize.width - localX : localX;
    final versoTexX = timeline.mirrored ? localX : pageSize.width - localX;
    final seamMetric = localX - seamX;
    final worldX =
        pageRect.left + effectiveX + timeline.sheetShift * curlInfluence;
    final worldY = pageRect.top + localY + curlHeightOffset;
    final projected = Offset(worldX, worldY);
    return _CurlMeshPoint(
      projected: projected,
      rectoTexture: Offset(rectoTexX, localY),
      versoTexture: Offset(versoTexX, localY),
      theta: theta,
      seamMetric: seamMetric,
      depth: displayDepth,
    );
  }

  _CurlMeshPoint _projectReversePoint({
    required Rect pageRect,
    required Size pageSize,
    required double localX,
    required double localY,
    required StPageFlipCorner corner,
    required double foldTheta,
    required _CurlTimeline timeline,
  }) {
    final reversePose = timeline.reversePose!;
    final coveredWidth = reversePose.coveredWidth
        .clamp(0.0, pageSize.width)
        .toDouble();
    final flatWidth = reversePose.unrollWidth
        .clamp(0.0, coveredWidth)
        .toDouble();
    final visibleCurlWidth = math.max(1.0, coveredWidth - flatWidth);
    final cylinderRadius = math.max(
      reversePose.cylinderRadius,
      visibleCurlWidth / math.pi,
    );
    double theta;
    double visualX;
    double depth;
    if (localX <= flatWidth) {
      theta = 0.0;
      visualX = localX;
      depth = 0.0;
    } else if (localX <= coveredWidth) {
      final bandT = ((localX - flatWidth) / visibleCurlWidth)
          .clamp(0.0, 1.0)
          .toDouble();
      theta = bandT * math.pi;
      visualX = flatWidth + (1 - math.cos(theta)) * visibleCurlWidth * 0.5;
      depth = math.sin(theta) * cylinderRadius;
    } else {
      theta = math.pi;
      visualX = coveredWidth;
      depth = 0.0;
    }
    final cornerFactor = corner == StPageFlipCorner.top
        ? 1 - (localY / math.max(pageSize.height, 1.0))
        : localY / math.max(pageSize.height, 1.0);
    final liftPx =
        pageSize.height *
        reversePose.lift *
        0.16 *
        (theta <= 0 ? 0.0 : math.sin(theta));
    final curlHeightOffset =
        reversePose.cornerBiasY * (1 - cornerFactor) * liftPx;
    final worldX = pageRect.left + visualX;
    final worldY = pageRect.top + localY + curlHeightOffset;
    final projectionCenterX = pageRect.left + flatWidth;
    final projectionCenterY = pageRect.top + localY;
    final scale = depth <= 0
        ? 1.0
        : timeline.perspective / (timeline.perspective + depth * 0.35);
    final projected = Offset(
      projectionCenterX + (worldX - projectionCenterX) * scale,
      projectionCenterY + (worldY - projectionCenterY) * scale,
    );
    return _CurlMeshPoint(
      projected: projected,
      rectoTexture: Offset(localX, localY),
      versoTexture: Offset(pageSize.width - localX, localY),
      theta: theta,
      seamMetric: theta - foldTheta,
      depth: depth,
    );
  }

  _CurlMeshPoint _projectBackwardReplayPoint({
    required Rect pageRect,
    required Size pageSize,
    required double localX,
    required double localY,
    required StPageFlipCorner corner,
    required _CurlTimeline timeline,
    required ArticlePageBackwardLeafFrame backwardLeafFrame,
  }) {
    final coveredWidth =
        (backwardLeafFrame.coveredWidthNormalized * pageSize.width)
            .clamp(0.0, pageSize.width)
            .toDouble();
    final flatWidth =
        (backwardLeafFrame.laidDownWidthNormalized * pageSize.width)
            .clamp(0.0, coveredWidth)
            .toDouble();
    final visibleCurlWidth = math.max(1.0, coveredWidth - flatWidth).toDouble();
    final rectoRevealWidth =
        (backwardLeafFrame.rectoRevealWidthNormalized * pageSize.width)
            .clamp(0.0, visibleCurlWidth)
            .toDouble();
    final edgeBandWidth =
        (backwardLeafFrame.edgeBandWidthNormalized * pageSize.width)
            .clamp(0.0, math.max(0.0, visibleCurlWidth - rectoRevealWidth))
            .toDouble();
    final seamSplitWidth = (rectoRevealWidth + edgeBandWidth * 0.5)
        .clamp(visibleCurlWidth * 0.08, visibleCurlWidth * 0.92)
        .toDouble();
    final seamTheta = (seamSplitWidth / visibleCurlWidth * math.pi)
        .clamp(math.pi * 0.08, math.pi * 0.92)
        .toDouble();
    final cylinderRadius = math.max(
      visibleCurlWidth / math.pi,
      pageSize.width * 0.028,
    );

    double theta;
    double visualX;
    double depth;
    if (localX <= flatWidth) {
      theta = 0.0;
      visualX = localX;
      depth = 0.0;
    } else if (localX <= coveredWidth) {
      final bandT = ((localX - flatWidth) / visibleCurlWidth)
          .clamp(0.0, 1.0)
          .toDouble();
      theta = bandT * math.pi;
      visualX = flatWidth + (1 - math.cos(theta)) * visibleCurlWidth * 0.5;
      depth = math.sin(theta) * cylinderRadius;
    } else {
      theta = math.pi;
      visualX = coveredWidth;
      depth = 0.0;
    }

    final worldX = pageRect.left + visualX;
    final worldY = pageRect.top + localY;
    final projected = Offset(worldX, worldY);
    return _CurlMeshPoint(
      projected: projected,
      rectoTexture: Offset(localX, localY),
      versoTexture: Offset(pageSize.width - localX, localY),
      theta: theta,
      seamMetric: theta - seamTheta,
      depth: depth,
    );
  }

  ArticlePageCurlAlignmentDiagnostics _resolveBackwardAlignmentDiagnostics({
    required Rect pageRect,
    required Size pageSize,
    required StPageFlipCorner corner,
    required _CurlTimeline timeline,
    required ArticlePageBackwardLeafFrame backwardLeafFrame,
  }) {
    final seamX = resolveArticlePageBackwardSeamX(
      frame: backwardLeafFrame,
      pageSize: pageSize,
    );
    final topSpine = _projectBackwardReplayPoint(
      pageRect: pageRect,
      pageSize: pageSize,
      localX: 0,
      localY: 0,
      corner: corner,
      timeline: timeline,
      backwardLeafFrame: backwardLeafFrame,
    );
    final bottomSpine = _projectBackwardReplayPoint(
      pageRect: pageRect,
      pageSize: pageSize,
      localX: 0,
      localY: pageSize.height,
      corner: corner,
      timeline: timeline,
      backwardLeafFrame: backwardLeafFrame,
    );
    final topSeam = _projectBackwardReplayPoint(
      pageRect: pageRect,
      pageSize: pageSize,
      localX: seamX,
      localY: 0,
      corner: corner,
      timeline: timeline,
      backwardLeafFrame: backwardLeafFrame,
    );
    final bottomSeam = _projectBackwardReplayPoint(
      pageRect: pageRect,
      pageSize: pageSize,
      localX: seamX,
      localY: pageSize.height,
      corner: corner,
      timeline: timeline,
      backwardLeafFrame: backwardLeafFrame,
    );
    return ArticlePageCurlAlignmentDiagnostics(
      spineTopX: topSpine.projected.dx,
      spineBottomX: bottomSpine.projected.dx,
      seamTopX: topSeam.projected.dx,
      seamBottomX: bottomSeam.projected.dx,
    );
  }
}

double _resolveFoldTheta(_CurlTimeline timeline) {
  final seamThetaBias = timeline.mirrored || timeline.reversePose != null
      ? 0.04
      : switch (timeline.curlAngleBand) {
          StPageFlipCurlAngleBand.shallow => 0.045,
          StPageFlipCurlAngleBand.mid => 0.04,
          StPageFlipCurlAngleBand.steep => 0.035,
        };
  return math.pi / 2 + seamThetaBias;
}

@immutable
class _CurlMeshPoint {
  const _CurlMeshPoint({
    required this.projected,
    required this.rectoTexture,
    required this.versoTexture,
    required this.theta,
    required this.seamMetric,
    required this.depth,
  });

  const _CurlMeshPoint.empty()
    : projected = Offset.zero,
      rectoTexture = Offset.zero,
      versoTexture = Offset.zero,
      theta = 0,
      seamMetric = 0,
      depth = 0;

  final Offset projected;
  final Offset rectoTexture;
  final Offset versoTexture;
  final double theta;
  final double seamMetric;
  final double depth;
}

@immutable
class _CurlTimeline {
  const _CurlTimeline({
    required this.mirrored,
    required this.curlAngleBand,
    required this.basePivot,
    required this.diagonalExtent,
    required this.leadingRadius,
    required this.trailingRadius,
    required this.sheetShift,
    required this.perspective,
    required this.rollProgress,
    required this.cylinderProgress,
    required this.unfoldProgress,
    required this.heightLiftBias,
    required this.forwardAngle,
    required this.reversePose,
  });

  factory _CurlTimeline.fromPageTimeline(
    StPageFlipTimeline timeline, {
    required ReverseFlipPose? reversePose,
  }) {
    return _CurlTimeline(
      mirrored: timeline.mirrored,
      curlAngleBand: timeline.curlAngleBand,
      basePivot: timeline.basePivot,
      diagonalExtent: timeline.diagonalExtent,
      leadingRadius: timeline.leadingRadius,
      trailingRadius: timeline.trailingRadius,
      sheetShift: timeline.sheetShift,
      perspective: timeline.perspective,
      rollProgress: timeline.rollProgress,
      cylinderProgress: timeline.cylinderProgress,
      unfoldProgress: timeline.unfoldProgress,
      heightLiftBias: timeline.heightLiftBias,
      forwardAngle: null,
      reversePose: reversePose,
    );
  }

  factory _CurlTimeline.fromRenderFrame(StPageFlipRenderFrame renderFrame) {
    return _CurlTimeline(
      mirrored: renderFrame.timeline.mirrored,
      curlAngleBand: renderFrame.timeline.curlAngleBand,
      basePivot: renderFrame.timeline.basePivot,
      diagonalExtent: renderFrame.timeline.diagonalExtent,
      leadingRadius: renderFrame.timeline.leadingRadius,
      trailingRadius: renderFrame.timeline.trailingRadius,
      sheetShift: renderFrame.timeline.sheetShift,
      perspective: renderFrame.timeline.perspective,
      rollProgress: renderFrame.timeline.rollProgress,
      cylinderProgress: renderFrame.timeline.cylinderProgress,
      unfoldProgress: renderFrame.timeline.unfoldProgress,
      heightLiftBias: renderFrame.timeline.heightLiftBias,
      forwardAngle: renderFrame.direction == StPageFlipDirection.forward
          ? renderFrame.angle
          : null,
      reversePose: renderFrame.reversePose,
    );
  }

  final bool mirrored;
  final StPageFlipCurlAngleBand curlAngleBand;
  final double basePivot;
  final double diagonalExtent;
  final double leadingRadius;
  final double trailingRadius;
  final double sheetShift;
  final double perspective;
  final double rollProgress;
  final double cylinderProgress;
  final double unfoldProgress;
  final double heightLiftBias;
  final double? forwardAngle;
  final ReverseFlipPose? reversePose;
}
