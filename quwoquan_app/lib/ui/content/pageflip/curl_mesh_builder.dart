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
  }) {
    final effectiveFrame = renderFrame;
    final effectiveDirection = effectiveFrame?.renderDirection ?? direction;
    final effectiveCorner = effectiveFrame?.corner ?? corner;
    final effectiveDragPoint = effectiveFrame?.localPagePoint ?? dragPoint;
    final settledProgress = (effectiveFrame?.progress ?? progress)
        .clamp(0.0, 1.0)
        .toDouble();
    final timeline = effectiveFrame == null
        ? _resolveTimeline(
            direction: effectiveDirection,
            progress: settledProgress,
            dragPoint: effectiveDragPoint,
            pageSize: pageSize,
            corner: effectiveCorner,
            reversePose: reversePose,
          )
        : _CurlTimeline.fromRenderFrame(effectiveFrame, pageSize);
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
          perspective: timeline.perspective,
          direction: effectiveDirection,
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
        final center = _centerPoint(topLeft, topRight, bottomRight, bottomLeft);
        _appendVisibleTriangle(
          frontPositions: frontPositions,
          frontTexCoords: frontTexCoords,
          backPositions: backPositions,
          backTexCoords: backTexCoords,
          a: topLeft,
          b: topRight,
          c: center,
        );
        _appendVisibleTriangle(
          frontPositions: frontPositions,
          frontTexCoords: frontTexCoords,
          backPositions: backPositions,
          backTexCoords: backTexCoords,
          a: topRight,
          b: bottomRight,
          c: center,
        );
        _appendVisibleTriangle(
          frontPositions: frontPositions,
          frontTexCoords: frontTexCoords,
          backPositions: backPositions,
          backTexCoords: backTexCoords,
          a: bottomRight,
          b: bottomLeft,
          c: center,
        );
        _appendVisibleTriangle(
          frontPositions: frontPositions,
          frontTexCoords: frontTexCoords,
          backPositions: backPositions,
          backTexCoords: backTexCoords,
          a: bottomLeft,
          b: topLeft,
          c: center,
        );
      }
    }

    final foldXNormalized =
        (pivotAccumulator / (verticalSegments + 1) / pageSize.width)
            .clamp(0.0, 1.0)
            .toDouble();
    return ArticlePageCurlFrame(
      frontSurface: _buildSurface(frontPositions, frontTexCoords, maxDepth),
      backSurface: _buildSurface(backPositions, backTexCoords, maxDepth),
      bottomClipPath: bottomClipPath ?? (Path()..addRect(pageRect)),
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

  _CurlMeshPoint _centerPoint(
    _CurlMeshPoint a,
    _CurlMeshPoint b,
    _CurlMeshPoint c,
    _CurlMeshPoint d,
  ) {
    return _CurlMeshPoint(
      projected: Offset(
        (a.projected.dx + b.projected.dx + c.projected.dx + d.projected.dx) / 4,
        (a.projected.dy + b.projected.dy + c.projected.dy + d.projected.dy) / 4,
      ),
      rectoTexture: Offset(
        (a.rectoTexture.dx +
                b.rectoTexture.dx +
                c.rectoTexture.dx +
                d.rectoTexture.dx) /
            4,
        (a.rectoTexture.dy +
                b.rectoTexture.dy +
                c.rectoTexture.dy +
                d.rectoTexture.dy) /
            4,
      ),
      versoTexture: Offset(
        (a.versoTexture.dx +
                b.versoTexture.dx +
                c.versoTexture.dx +
                d.versoTexture.dx) /
            4,
        (a.versoTexture.dy +
                b.versoTexture.dy +
                c.versoTexture.dy +
                d.versoTexture.dy) /
            4,
      ),
      theta: (a.theta + b.theta + c.theta + d.theta) / 4,
      depth: (a.depth + b.depth + c.depth + d.depth) / 4,
    );
  }

  _CurlTimeline _resolveTimeline({
    required StPageFlipDirection direction,
    required double progress,
    required Offset dragPoint,
    required Size pageSize,
    required StPageFlipCorner corner,
    required ReverseFlipPose? reversePose,
  }) {
    if (direction == StPageFlipDirection.back) {
      // 竖屏回翻且有三阶段 pose 时，走三阶段主线。
      if (reversePose != null) {
        return _resolveReverseTimeline(
          reversePose: reversePose,
          dragPoint: dragPoint,
          pageSize: pageSize,
        );
      }
      // 横屏回翻或无 reversePose 的降级路径。
      return _resolveMirroredForwardTimeline(
        progress: progress,
        dragPoint: dragPoint,
        pageSize: pageSize,
      );
    }
    return _resolveForwardTimeline(
      progress: progress,
      dragPoint: dragPoint,
      pageSize: pageSize,
    );
  }

  _CurlTimeline _resolveReverseTimeline({
    required ReverseFlipPose reversePose,
    required Offset dragPoint,
    required Size pageSize,
  }) {
    // 从三阶段 pose 提取 pivot（leadingEdgeX 镜像到前翻坐标系）。
    final mirroredPivot =
        (pageSize.width - reversePose.leadingEdgeX).clamp(0.0, pageSize.width);
    final curlWidth = math.max(1.0, pageSize.width - mirroredPivot);
    final progress = reversePose.progress.clamp(0.0, 1.0).toDouble();
    final diagonalExtent =
        ui.lerpDouble(
          pageSize.width * 0.06,
          pageSize.width * 0.32,
          Curves.easeOutCubic.transform(progress),
        ) ??
        (pageSize.width * 0.18);
    final radiusBase =
        ui.lerpDouble(
          math.max(curlWidth / math.pi, pageSize.width * 0.085),
          pageSize.width * 0.058,
          Curves.easeInOut.transform(progress),
        ) ??
        (pageSize.width * 0.085);
    // 三阶段 rollProgress 来自 emergence，cylinder/unfold 来自各自阶段。
    final rollProgress = reversePose.emergenceProgress.clamp(0.0, 1.0).toDouble();
    final cylinderProgress =
        reversePose.cylinderProgress.clamp(0.0, 1.0).toDouble();
    final unfoldProgress =
        reversePose.unrollProgress.clamp(0.0, 1.0).toDouble();
    final sheetShift =
        -(ui.lerpDouble(
              0.0,
              pageSize.width * 0.18,
              Curves.easeOut.transform(progress),
            ) ??
            0.0);
    return _CurlTimeline(
      mirrored: true,
      basePivot: mirroredPivot,
      diagonalExtent: diagonalExtent,
      leadingRadius: radiusBase * 1.12,
      trailingRadius: radiusBase * 0.72,
      sheetShift: -sheetShift,
      perspective: pageSize.width * 2.7,
      rollProgress: rollProgress,
      cylinderProgress: cylinderProgress,
      unfoldProgress: unfoldProgress,
      heightLiftBias: 0.22,
      reversePose: reversePose,
    );
  }

  _CurlTimeline _resolveForwardTimeline({
    required double progress,
    required Offset dragPoint,
    required Size pageSize,
  }) {
    final localDragX = dragPoint.dx.clamp(0.0, pageSize.width).toDouble();
    final curlWidth = math.max(1.0, pageSize.width - localDragX);
    final diagonalExtent =
        ui.lerpDouble(
          pageSize.width * 0.06,
          pageSize.width * 0.32,
          Curves.easeOutCubic.transform(progress),
        ) ??
        (pageSize.width * 0.18);
    final radiusBase =
        ui.lerpDouble(
          math.max(curlWidth / math.pi, pageSize.width * 0.085),
          pageSize.width * 0.058,
          Curves.easeInOut.transform(progress),
        ) ??
        (pageSize.width * 0.085);
    final sheetShift =
        -(ui.lerpDouble(
              0.0,
              pageSize.width * 0.18,
              Curves.easeOut.transform(progress),
            ) ??
            0.0);
    return _CurlTimeline(
      mirrored: false,
      basePivot: localDragX,
      diagonalExtent: diagonalExtent,
      leadingRadius: radiusBase * 1.12,
      trailingRadius: radiusBase * 0.72,
      sheetShift: sheetShift,
      perspective: pageSize.width * 2.7,
      rollProgress: progress,
      cylinderProgress: 0.0,
      unfoldProgress: 0.0,
      heightLiftBias: 0.22,
      reversePose: null,
    );
  }

  _CurlTimeline _resolveMirroredForwardTimeline({
    required double progress,
    required Offset dragPoint,
    required Size pageSize,
  }) {
    // Mirror the drag point horizontally so the forward curl algorithm
    // produces a left-to-right curl instead of right-to-left.
    final mirroredDragPoint = Offset(
      pageSize.width - dragPoint.dx.clamp(0.0, pageSize.width),
      dragPoint.dy,
    );
    final timeline = _resolveForwardTimeline(
      progress: progress,
      dragPoint: mirroredDragPoint,
      pageSize: pageSize,
    );
    return _CurlTimeline(
      mirrored: true,
      basePivot: timeline.basePivot,
      diagonalExtent: timeline.diagonalExtent,
      leadingRadius: timeline.leadingRadius,
      trailingRadius: timeline.trailingRadius,
      sheetShift: -timeline.sheetShift,
      perspective: timeline.perspective,
      rollProgress: timeline.rollProgress,
      cylinderProgress: 0.0,
      unfoldProgress: 0.0,
      heightLiftBias: timeline.heightLiftBias,
      reversePose: null,
    );
  }

  _CurlMeshPoint _projectPoint({
    required Rect pageRect,
    required Size pageSize,
    required double localX,
    required double localY,
    required double rowPivot,
    required double rowRadius,
    required double perspective,
    required StPageFlipDirection direction,
    required StPageFlipCorner corner,
    required _CurlTimeline timeline,
  }) {
    final rowCurlDistance = math.max(0.0, localX - rowPivot);
    final theta = math.min(math.pi, rowCurlDistance / math.max(rowRadius, 1.0));
    final depth = theta <= 0 ? 0.0 : (1 - math.cos(theta)) * rowRadius;
    final curledX = theta <= 0
        ? localX
        : rowPivot + math.sin(theta) * rowRadius;
    final cornerFactor = corner == StPageFlipCorner.top
        ? 1 - (localY / math.max(pageSize.height, 1.0))
        : localY / math.max(pageSize.height, 1.0);
    final curlHeightOffset =
        (1 - cornerFactor) *
        depth *
        (corner == StPageFlipCorner.top
            ? -timeline.heightLiftBias
            : timeline.heightLiftBias);
    final effectiveX = timeline.mirrored ? pageSize.width - curledX : curledX;
    final rectoTexX = timeline.mirrored ? pageSize.width - localX : localX;
    final versoTexX = timeline.mirrored ? localX : pageSize.width - localX;
    final worldX = pageRect.left + effectiveX + timeline.sheetShift;
    final worldY = pageRect.top + localY + curlHeightOffset;
    final projectionCenterX = pageRect.center.dx + timeline.sheetShift;
    final projectionCenterY = pageRect.center.dy;
    final scale = perspective / (perspective + depth);
    final projected = Offset(
      projectionCenterX + (worldX - projectionCenterX) * scale,
      projectionCenterY + (worldY - projectionCenterY) * scale,
    );
    return _CurlMeshPoint(
      projected: projected,
      rectoTexture: Offset(rectoTexX, localY),
      versoTexture: Offset(versoTexX, localY),
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

  factory _CurlTimeline.fromRenderFrame(
    StPageFlipRenderFrame renderFrame,
    Size pageSize,
  ) {
    final timeline = renderFrame.timeline;
    final backwardLeafFrame = renderFrame.backwardLeafFrame;
    if (renderFrame.direction == StPageFlipDirection.back &&
        backwardLeafFrame != null) {
      final displayCurlWidth =
          (pageSize.width * backwardLeafFrame.curlWidthNormalized)
              .clamp(pageSize.width * 0.04, pageSize.width * 0.32)
              .toDouble();
      final radiusBase = math.max(
        displayCurlWidth / math.pi,
        pageSize.width * 0.045,
      );
      final meshPivot =
          (pageSize.width * (1 - backwardLeafFrame.curlPivotNormalized))
              .clamp(0.0, pageSize.width)
              .toDouble();
      return _CurlTimeline(
        mirrored: true,
        basePivot: meshPivot,
        diagonalExtent: math.max(
          pageSize.width * 0.04,
          displayCurlWidth * 0.65,
        ),
        leadingRadius: radiusBase * 1.08,
        trailingRadius: radiusBase * 0.72,
        sheetShift:
            (ui.lerpDouble(
                  0.0,
                  pageSize.width * 0.04,
                  backwardLeafFrame.unrollProgress,
                ) ??
                0.0)
                .toDouble(),
        perspective: timeline.perspective,
        rollProgress: backwardLeafFrame.emergenceProgress,
        cylinderProgress: backwardLeafFrame.unrollProgress,
        unfoldProgress: backwardLeafFrame.settleProgress,
        heightLiftBias: backwardLeafFrame.edgeLift,
        reversePose: null,
      );
    }
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
      reversePose: null,
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
