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
  });

  final ui.Vertices vertices;
  final double maxDepth;
}

@immutable
class ArticlePageCurlFrame {
  const ArticlePageCurlFrame({
    required this.frontSurface,
    required this.backSurface,
    required this.bottomClipPath,
    required this.foldXNormalized,
    required this.curlLift,
    required this.progress,
    required this.rollProgress,
    required this.cylinderProgress,
    required this.unfoldProgress,
  });

  final ArticlePageCurlMeshSurface? frontSurface;
  final ArticlePageCurlMeshSurface? backSurface;
  final Path bottomClipPath;
  final double foldXNormalized;
  final double curlLift;
  final double progress;
  final double rollProgress;
  final double cylinderProgress;
  final double unfoldProgress;
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
    final settledProgress = (effectiveFrame?.progress ?? progress)
        .clamp(0.0, 1.0)
        .toDouble();
    final timeline = effectiveFrame == null
        ? _CurlTimeline.fromPageTimeline(
            resolvePageCurlTimeline(
              direction: effectiveDirection,
              renderDirection: reversePose != null &&
                      effectiveDirection == StPageFlipDirection.back
                  ? StPageFlipDirection.forward
                  : effectiveDirection,
              progress: settledProgress,
              localPagePoint: effectiveDragPoint,
              pageSize: pageSize,
              corner: effectiveCorner,
              reversePose: reversePose,
            ),
            reversePose: reversePose,
          )
        : _CurlTimeline.fromRenderFrame(effectiveFrame);
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
          corner: effectiveCorner,
          timeline: timeline,
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
          a: topLeft,
          b: topRight,
          c: bottomRight,
        );
        _appendVisibleTriangle(
          frontPositions: frontPositions,
          frontTexCoords: frontTexCoords,
          backPositions: backPositions,
          backTexCoords: backTexCoords,
          a: topLeft,
          b: bottomRight,
          c: bottomLeft,
        );
      }
    }

    final foldXNormalized =
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
        : timeline.reversePose == null && !timeline.mirrored
        ? Path.combine(
            PathOperation.intersect,
            bottomClipPath,
            meshDerivedBottomClipPath,
          )
        : bottomClipPath;
    return ArticlePageCurlFrame(
      frontSurface: _buildSurface(frontPositions, frontTexCoords, maxDepth),
      backSurface: _buildSurface(backPositions, backTexCoords, maxDepth),
      bottomClipPath: effectiveBottomClipPath,
      foldXNormalized: foldXNormalized,
      curlLift: (maxDepth / math.max(pageSize.width * 0.32, 1.0))
          .clamp(0.0, 1.0)
          .toDouble(),
      progress: settledProgress,
      rollProgress: timeline.rollProgress,
      cylinderProgress: timeline.cylinderProgress,
      unfoldProgress: timeline.unfoldProgress,
    );
  }

  int _indexFor(int row, int col) {
    return row * (horizontalSegments + 1) + col;
  }

  ArticlePageCurlMeshSurface? _buildSurface(
    List<double> positions,
    List<double> textureCoordinates,
    double maxDepth,
  ) {
    if (positions.isEmpty || textureCoordinates.isEmpty) {
      return null;
    }
    return ArticlePageCurlMeshSurface(
      vertices: ui.Vertices.raw(
        ui.VertexMode.triangles,
        Float32List.fromList(positions),
        textureCoordinates: Float32List.fromList(textureCoordinates),
      ),
      maxDepth: maxDepth,
    );
  }

  void _appendVisibleTriangle({
    required List<double> frontPositions,
    required List<double> frontTexCoords,
    required List<double> backPositions,
    required List<double> backTexCoords,
    required _CurlMeshPoint a,
    required _CurlMeshPoint b,
    required _CurlMeshPoint c,
  }) {
    final triangle = <_CurlMeshPoint>[a, b, c];
    final frontPolygon = _clipTriangleByTheta(triangle, keepBack: false);
    if (frontPolygon.length >= 3) {
      _appendPolygon(
        frontPositions,
        frontTexCoords,
        frontPolygon,
        useVersoTexture: false,
      );
    }
    final backPolygon = _clipTriangleByTheta(triangle, keepBack: true);
    if (backPolygon.length >= 3) {
      _appendPolygon(
        backPositions,
        backTexCoords,
        backPolygon,
        useVersoTexture: true,
      );
    }
  }

  List<_CurlMeshPoint> _clipTriangleByTheta(
    List<_CurlMeshPoint> triangle, {
    required bool keepBack,
  }) {
    const foldTheta = math.pi / 2;
    final output = <_CurlMeshPoint>[];
    var previous = triangle.last;
    var previousInside = keepBack
        ? previous.theta >= foldTheta
        : previous.theta <= foldTheta;
    for (final current in triangle) {
      final currentInside = keepBack
          ? current.theta >= foldTheta
          : current.theta <= foldTheta;
      if (currentInside != previousInside) {
        output.add(_interpolateAtTheta(previous, current, foldTheta));
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
    double targetTheta,
  ) {
    final thetaDelta = to.theta - from.theta;
    final t = thetaDelta.abs() < 0.0001
        ? 0.0
        : ((targetTheta - from.theta) / thetaDelta).clamp(0.0, 1.0).toDouble();
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
      theta: targetTheta,
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
    required StPageFlipCorner corner,
    required _CurlTimeline timeline,
  }) {
    if (timeline.reversePose != null) {
      return _projectReversePoint(
        pageRect: pageRect,
        pageSize: pageSize,
        localX: localX,
        localY: localY,
        corner: corner,
        timeline: timeline,
      );
    }
    final rowCurlDistance = math.max(0.0, localX - rowPivot);
    final theta = math.min(math.pi, rowCurlDistance / math.max(rowRadius, 1.0));
    final depth = theta <= 0 ? 0.0 : (1 - math.cos(theta)) * rowRadius;
    final liftDepth = theta <= 0 ? 0.0 : math.sin(theta) * rowRadius;
    final curledX = theta <= 0
        ? localX
        : rowPivot + math.sin(theta) * rowRadius;
    final cornerFactor = corner == StPageFlipCorner.top
        ? 1 - (localY / math.max(pageSize.height, 1.0))
        : localY / math.max(pageSize.height, 1.0);
    final curlHeightOffset =
        (1 - cornerFactor) *
        liftDepth *
        (corner == StPageFlipCorner.top
            ? -timeline.heightLiftBias
            : timeline.heightLiftBias);
    final curlInfluence = (theta <= 0 ? 0.0 : (theta / math.pi))
        .clamp(0.0, 1.0)
        .toDouble();
    final effectiveX = timeline.mirrored ? pageSize.width - curledX : curledX;
    final rectoTexX = timeline.mirrored ? pageSize.width - localX : localX;
    final versoTexX = timeline.mirrored ? localX : pageSize.width - localX;
    final worldX =
        pageRect.left + effectiveX + timeline.sheetShift * curlInfluence;
    final worldY = pageRect.top + localY + curlHeightOffset;
    final projected = Offset(worldX, worldY);
    return _CurlMeshPoint(
      projected: projected,
      rectoTexture: Offset(rectoTexX, localY),
      versoTexture: Offset(versoTexX, localY),
      theta: theta,
      depth: depth,
    );
  }

  _CurlMeshPoint _projectReversePoint({
    required Rect pageRect,
    required Size pageSize,
    required double localX,
    required double localY,
    required StPageFlipCorner corner,
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
      depth: depth,
    );
  }
}

@immutable
class _CurlMeshPoint {
  const _CurlMeshPoint({
    required this.projected,
    required this.rectoTexture,
    required this.versoTexture,
    required this.theta,
    required this.depth,
  });

  const _CurlMeshPoint.empty()
    : projected = Offset.zero,
      rectoTexture = Offset.zero,
      versoTexture = Offset.zero,
      theta = 0,
      depth = 0;

  final Offset projected;
  final Offset rectoTexture;
  final Offset versoTexture;
  final double theta;
  final double depth;
}

@immutable
class _CurlTimeline {
  const _CurlTimeline({
    required this.mirrored,
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
    required this.reversePose,
  });

  factory _CurlTimeline.fromPageTimeline(
    StPageFlipTimeline timeline, {
    required ReverseFlipPose? reversePose,
  }) {
    return _CurlTimeline(
      mirrored: timeline.mirrored,
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
      reversePose: reversePose,
    );
  }

  factory _CurlTimeline.fromRenderFrame(StPageFlipRenderFrame renderFrame) {
    return _CurlTimeline.fromPageTimeline(
      renderFrame.timeline,
      reversePose: renderFrame.reversePose,
    );
  }

  final bool mirrored;
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
  final ReverseFlipPose? reversePose;
}
