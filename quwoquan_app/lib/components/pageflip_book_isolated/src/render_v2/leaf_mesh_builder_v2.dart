import 'dart:math' as math;
import 'dart:ui';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/leaf_coverage_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/leaf_pose_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/scene/pageflip_book_scene.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

@immutable
class LeafMeshSurfaceV2 {
  const LeafMeshSurfaceV2({required this.vertices});

  final ui.Vertices vertices;
}

@immutable
class LeafMeshFrameV2 {
  const LeafMeshFrameV2({
    required this.frontSurface,
    required this.backSurface,
    required this.coverage,
    required this.progress,
    required this.foldXNormalized,
    required this.curlLiftNormalized,
  });

  final LeafMeshSurfaceV2 frontSurface;
  final LeafMeshSurfaceV2? backSurface;
  final LeafCoverageV2 coverage;
  final double progress;
  final double foldXNormalized;
  final double curlLiftNormalized;

  Path get bottomClipPath => coverage.bottomClipPath;

  Path get leafClipPath => coverage.leafClipPath;

  Path get leafSilhouettePath => coverage.leafSilhouettePath;

  Rect get leafBounds => coverage.leafBounds;
}

@immutable
class IsolatedLeafRenderSceneV2 {
  const IsolatedLeafRenderSceneV2({
    required this.stageSize,
    required this.pageRect,
    required this.textures,
    required this.meshFrame,
    required this.lightConfig,
    required this.direction,
    required this.drawCoveredCurrentUnderlay,
  });

  final Size stageSize;
  final Rect pageRect;
  final ArticlePageTextureBundle textures;
  final LeafMeshFrameV2 meshFrame;
  final ArticlePageCurlLightConfig lightConfig;
  final PageflipBookIsolatedDirection direction;
  final bool drawCoveredCurrentUnderlay;
}

class LeafMeshBuilderV2 {
  const LeafMeshBuilderV2({this.rowSegments = 18, this.minColumnStep = 18});

  final int rowSegments;
  final double minColumnStep;

  LeafMeshFrameV2 build({required PageflipBookIsolatedScene scene}) {
    final pose = scene.pose!;
    final pageRect = scene.pageRect;
    final pageWidth = math.max(1.0, pose.pageSize.width).toDouble();
    final pageHeight = math.max(1.0, pose.pageSize.height).toDouble();
    final columnSegments = math.max(
      18,
      (pageWidth / minColumnStep).round() + 6,
    );
    final columns = List<double>.generate(
      columnSegments + 1,
      (index) => pageWidth * (index / columnSegments),
      growable: false,
    );
    final rows = List<double>.generate(
      rowSegments + 1,
      (index) => pageHeight * (index / rowSegments),
      growable: false,
    );
    final projectedPoints = <_ProjectedLeafPoint>[];
    var rowPivotAccumulator = 0.0;
    var maxLiftOffset = 0.0;
    for (final row in rows) {
      rowPivotAccumulator += pose.resolveRowPivot(row);
      for (final column in columns) {
        final point = _projectPoint(
          pageRect: pageRect,
          pose: pose,
          localX: column,
          localY: row,
        );
        maxLiftOffset = math.max(maxLiftOffset, point.curlHeightOffset.abs());
        projectedPoints.add(point);
      }
    }
    final frontPositions = <double>[];
    final frontTextureCoordinates = <double>[];
    final backPositions = <double>[];
    final backTextureCoordinates = <double>[];
    final columnCount = columns.length;
    final rowCount = rows.length;
    for (var row = 0; row < rowCount - 1; row += 1) {
      for (var column = 0; column < columnCount - 1; column += 1) {
        final topLeft = projectedPoints[row * columnCount + column];
        final topRight = projectedPoints[row * columnCount + column + 1];
        final bottomLeft = projectedPoints[(row + 1) * columnCount + column];
        final bottomRight =
            projectedPoints[(row + 1) * columnCount + column + 1];
        _appendTriangle(
          <_ProjectedLeafPoint>[topLeft, bottomLeft, topRight],
          frontPositions: frontPositions,
          frontUvs: frontTextureCoordinates,
          backPositions: backPositions,
          backUvs: backTextureCoordinates,
        );
        _appendTriangle(
          <_ProjectedLeafPoint>[topRight, bottomLeft, bottomRight],
          frontPositions: frontPositions,
          frontUvs: frontTextureCoordinates,
          backPositions: backPositions,
          backUvs: backTextureCoordinates,
        );
      }
    }
    final leafSilhouettePath = _buildLeafCoveragePath(
      points: projectedPoints,
      columnCount: columnCount,
      rowCount: rowCount,
    );
    final pageRectPath = Path()..addRect(pageRect);
    final leafClipPath = Path.combine(
      PathOperation.intersect,
      pageRectPath,
      leafSilhouettePath,
    );
    final bottomClipPath = Path.combine(
      PathOperation.difference,
      pageRectPath,
      leafClipPath,
    );
    final coverage = LeafCoverageV2(
      leafSilhouettePath: leafSilhouettePath,
      leafClipPath: leafClipPath,
      bottomClipPath: bottomClipPath,
      leafBounds: leafClipPath.getBounds(),
    );
    final frontSurface = _buildSurface(
      positions: frontPositions,
      textureCoordinates: frontTextureCoordinates,
    )!;
    final backSurface = _buildSurface(
      positions: backPositions,
      textureCoordinates: backTextureCoordinates,
    );
    return LeafMeshFrameV2(
      frontSurface: frontSurface,
      backSurface: backSurface,
      coverage: coverage,
      progress: pose.progress,
      foldXNormalized: rowCount <= 0
          ? pose.foldXNormalized
          : _resolveViewportFoldXNormalized(
              pose: pose,
              normalizedPivot: ((rowPivotAccumulator / rowCount) / pageWidth)
                  .clamp(0.0, 1.0)
                  .toDouble(),
            ),
      curlLiftNormalized: pageHeight <= 0
          ? 0
          : (maxLiftOffset / pageHeight).clamp(0.0, 1.0).toDouble(),
    );
  }

  LeafMeshSurfaceV2? _buildSurface({
    required List<double> positions,
    required List<double> textureCoordinates,
  }) {
    if (positions.isEmpty || textureCoordinates.isEmpty) {
      return null;
    }
    final resolvedPositions = <Offset>[];
    final resolvedTextureCoordinates = <Offset>[];
    for (var index = 0; index < positions.length; index += 2) {
      resolvedPositions.add(Offset(positions[index], positions[index + 1]));
      resolvedTextureCoordinates.add(
        Offset(textureCoordinates[index], textureCoordinates[index + 1]),
      );
    }
    return LeafMeshSurfaceV2(
      vertices: ui.Vertices(
        ui.VertexMode.triangles,
        resolvedPositions,
        textureCoordinates: resolvedTextureCoordinates,
      ),
    );
  }

  _ProjectedLeafPoint _projectPoint({
    required Rect pageRect,
    required LeafPoseV2 pose,
    required double localX,
    required double localY,
  }) {
    final pageWidth = math.max(1.0, pose.pageSize.width).toDouble();
    final pageHeight = math.max(1.0, pose.pageSize.height).toDouble();
    final rowPivot = pose.resolveRowPivot(localY);
    final theta = pose.thetaForPoint(localX, localY);
    final curlDepth = theta <= 0.0001
        ? 0.0
        : pose.curlRadius * (1 - math.cos(theta));
    final curledX = theta <= 0.0001
        ? localX
        : rowPivot + math.sin(theta) * pose.curlRadius;
    final cornerFactor = pose.resolveCornerFactor(localY);
    final curlHeightOffset = theta <= 0.0001
        ? 0.0
        : (1 - cornerFactor) *
              pose.liftAmount *
              math.sin(theta) *
              (pose.corner == PageflipBookIsolatedCorner.top
                  ? -pose.heightLiftBias
                  : pose.heightLiftBias);
    final viewportX = pose.direction.isForward ? curledX : pageWidth - curledX;
    final projectedLocal = Offset(
      viewportX,
      (localY + curlHeightOffset).clamp(0.0, pageHeight).toDouble(),
    );
    final rectoUv = pose.direction.isForward
        ? Offset(localX, localY)
        : Offset(pageWidth - localX, localY);
    final versoUv = pose.direction.isForward
        ? Offset(pageWidth - localX, localY)
        : Offset(localX, localY);
    return _ProjectedLeafPoint(
      position: pageRect.topLeft + projectedLocal,
      rectoUv: rectoUv,
      versoUv: versoUv,
      theta: theta,
      curlHeightOffset: curlHeightOffset,
      depth: curlDepth,
    );
  }

  double _resolveViewportFoldXNormalized({
    required LeafPoseV2 pose,
    required double normalizedPivot,
  }) {
    return pose.direction.isForward
        ? normalizedPivot
        : (1 - normalizedPivot).clamp(0.0, 1.0).toDouble();
  }

  void _appendTriangle(
    List<_ProjectedLeafPoint> triangle, {
    required List<double> frontPositions,
    required List<double> frontUvs,
    required List<double> backPositions,
    required List<double> backUvs,
  }) {
    const foldTheta = math.pi / 2;
    final frontPolygon = _clipTriangleByTheta(
      triangle,
      keepBack: false,
      splitTheta: foldTheta,
    );
    final backPolygon = _clipTriangleByTheta(
      triangle,
      keepBack: true,
      splitTheta: foldTheta,
    );
    if (frontPolygon.length >= 3) {
      _appendPolygon(frontPolygon, frontPositions, frontUvs, useVerso: false);
    }
    if (backPolygon.length >= 3) {
      _appendPolygon(backPolygon, backPositions, backUvs, useVerso: true);
    }
  }

  List<_ProjectedLeafPoint> _clipTriangleByTheta(
    List<_ProjectedLeafPoint> triangle, {
    required bool keepBack,
    required double splitTheta,
  }) {
    final polygon = <_ProjectedLeafPoint>[];
    for (var edge = 0; edge < triangle.length; edge += 1) {
      final start = triangle[edge];
      final end = triangle[(edge + 1) % triangle.length];
      final startInside = keepBack
          ? start.theta >= splitTheta - 1e-6
          : start.theta <= splitTheta + 1e-6;
      final endInside = keepBack
          ? end.theta >= splitTheta - 1e-6
          : end.theta <= splitTheta + 1e-6;
      if (startInside) {
        polygon.add(start);
      }
      if (startInside != endInside) {
        polygon.add(_interpolateAtTheta(start, end, splitTheta));
      }
      if (!startInside && endInside) {
        polygon.add(end);
      }
    }
    return polygon;
  }

  _ProjectedLeafPoint _interpolateAtTheta(
    _ProjectedLeafPoint start,
    _ProjectedLeafPoint end,
    double targetTheta,
  ) {
    final delta = end.theta - start.theta;
    if (delta.abs() < 1e-6) {
      return start;
    }
    final t = ((targetTheta - start.theta) / delta).clamp(0.0, 1.0).toDouble();
    return _ProjectedLeafPoint(
      position: Offset.lerp(start.position, end.position, t) ?? start.position,
      rectoUv: Offset.lerp(start.rectoUv, end.rectoUv, t) ?? start.rectoUv,
      versoUv: Offset.lerp(start.versoUv, end.versoUv, t) ?? start.versoUv,
      theta: targetTheta,
      curlHeightOffset:
          ui.lerpDouble(start.curlHeightOffset, end.curlHeightOffset, t) ??
          start.curlHeightOffset,
      depth: ui.lerpDouble(start.depth, end.depth, t) ?? start.depth,
    );
  }

  void _appendPolygon(
    List<_ProjectedLeafPoint> polygon,
    List<double> positions,
    List<double> uvs, {
    required bool useVerso,
  }) {
    for (var index = 1; index < polygon.length - 1; index += 1) {
      _appendVertex(positions, uvs, polygon[0], useVerso: useVerso);
      _appendVertex(positions, uvs, polygon[index], useVerso: useVerso);
      _appendVertex(positions, uvs, polygon[index + 1], useVerso: useVerso);
    }
  }

  void _appendVertex(
    List<double> positions,
    List<double> uvs,
    _ProjectedLeafPoint point, {
    required bool useVerso,
  }) {
    positions
      ..add(point.position.dx)
      ..add(point.position.dy);
    final uv = useVerso ? point.versoUv : point.rectoUv;
    uvs
      ..add(uv.dx)
      ..add(uv.dy);
  }

  Path _buildLeafCoveragePath({
    required List<_ProjectedLeafPoint> points,
    required int columnCount,
    required int rowCount,
  }) {
    if (points.isEmpty || columnCount <= 0 || rowCount <= 0) {
      return Path();
    }
    final outline = <Offset>[];
    for (var column = 0; column < columnCount; column += 1) {
      outline.add(points[column].position);
    }
    for (var row = 1; row < rowCount; row += 1) {
      outline.add(points[row * columnCount + columnCount - 1].position);
    }
    for (var column = columnCount - 2; column >= 0; column -= 1) {
      outline.add(points[(rowCount - 1) * columnCount + column].position);
    }
    for (var row = rowCount - 2; row > 0; row -= 1) {
      outline.add(points[row * columnCount].position);
    }
    if (outline.length < 3) {
      return Path();
    }
    final path = Path()..moveTo(outline.first.dx, outline.first.dy);
    for (final point in outline.skip(1)) {
      path.lineTo(point.dx, point.dy);
    }
    path.close();
    return path;
  }
}

@immutable
class _ProjectedLeafPoint {
  const _ProjectedLeafPoint({
    required this.position,
    required this.rectoUv,
    required this.versoUv,
    required this.theta,
    required this.curlHeightOffset,
    required this.depth,
  });

  final Offset position;
  final Offset rectoUv;
  final Offset versoUv;
  final double theta;
  final double curlHeightOffset;
  final double depth;
}
