import 'dart:typed_data';
import 'dart:ui' as ui;
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_leaf_verso_texture_mapping.dart';

const double _polygonEpsilon = 0.001;

@immutable
class BackwardLeafVersoUvMesh {
  const BackwardLeafVersoUvMesh({
    required this.positions,
    required this.textureCoordinates,
    required this.indices,
    required this.paintBounds,
    required this.textureDestinationRect,
  });

  final List<Offset> positions;
  final List<Offset> textureCoordinates;
  final List<int> indices;
  final Rect paintBounds;
  final Rect textureDestinationRect;

  ui.Vertices toVertices({Offset paintOrigin = Offset.zero}) {
    final positionValues = Float32List(positions.length * 2);
    final textureValues = Float32List(textureCoordinates.length * 2);
    for (var index = 0; index < positions.length; index += 1) {
      final valueIndex = index * 2;
      final position = positions[index] - paintOrigin;
      final texture = textureCoordinates[index];
      positionValues[valueIndex] = position.dx;
      positionValues[valueIndex + 1] = position.dy;
      textureValues[valueIndex] = texture.dx;
      textureValues[valueIndex + 1] = texture.dy;
    }
    return ui.Vertices.raw(
      ui.VertexMode.triangles,
      positionValues,
      textureCoordinates: textureValues,
      indices: Uint16List.fromList(indices),
    );
  }
}

BackwardLeafVersoUvMesh? buildBackwardLeafVersoUvMesh({
  required Size pageSize,
  required List<Offset> polygon,
}) {
  if (pageSize.isEmpty || polygon.length < 3) {
    return null;
  }
  final positions = _dedupePolygonPoints(polygon);
  if (positions.length < 3 || _polygonArea(positions) <= _polygonEpsilon) {
    return null;
  }
  final polygonBounds = _polygonBounds(positions);
  if (polygonBounds == null ||
      polygonBounds.width <= _polygonEpsilon ||
      polygonBounds.height <= _polygonEpsilon) {
    return null;
  }
  final textureDestinationRect = _textureDestinationRect(
    pageSize: pageSize,
    polygonBounds: polygonBounds,
  );
  final paintBounds = polygonBounds.expandToInclude(textureDestinationRect);
  final textureCoordinates = <Offset>[];
  for (final localPoint in positions) {
    // Route-B BACK local geometry may legitimately live outside the page rect.
    // Keep geometry raw; ImageShader clamp handles texture-edge sampling.
    textureCoordinates.add(
      backwardVersoTexturePoint(pageSize: pageSize, localPoint: localPoint),
    );
  }

  final indices = <int>[];
  for (var triangle = 0; triangle < positions.length - 2; triangle += 1) {
    indices
      ..add(0)
      ..add(triangle + 1)
      ..add(triangle + 2);
  }
  return BackwardLeafVersoUvMesh(
    positions: List<Offset>.unmodifiable(positions),
    textureCoordinates: List<Offset>.unmodifiable(textureCoordinates),
    indices: List<int>.unmodifiable(indices),
    paintBounds: paintBounds,
    textureDestinationRect: textureDestinationRect,
  );
}

Rect _textureDestinationRect({
  required Size pageSize,
  required Rect polygonBounds,
}) {
  double originForAxis({
    required double min,
    required double max,
    required double size,
  }) {
    if (min < 0) {
      return min;
    }
    if (max > size) {
      return max - size;
    }
    return 0;
  }

  return Rect.fromLTWH(
    originForAxis(
      min: polygonBounds.left,
      max: polygonBounds.right,
      size: pageSize.width,
    ),
    originForAxis(
      min: polygonBounds.top,
      max: polygonBounds.bottom,
      size: pageSize.height,
    ),
    pageSize.width,
    pageSize.height,
  );
}

List<Offset> _dedupePolygonPoints(List<Offset> polygon) {
  final points = <Offset>[];
  for (final point in polygon) {
    if (points.isEmpty || !_offsetsNear(points.last, point)) {
      points.add(point);
    }
  }
  if (points.length > 1 && _offsetsNear(points.first, points.last)) {
    points.removeLast();
  }
  return points;
}

bool _offsetsNear(Offset a, Offset b) {
  return (a.dx - b.dx).abs() <= _polygonEpsilon &&
      (a.dy - b.dy).abs() <= _polygonEpsilon;
}

double _polygonArea(List<Offset> polygon) {
  var twiceArea = 0.0;
  for (var index = 0; index < polygon.length; index += 1) {
    final current = polygon[index];
    final next = polygon[(index + 1) % polygon.length];
    twiceArea += current.dx * next.dy - next.dx * current.dy;
  }
  return twiceArea.abs() / 2.0;
}

Rect? _polygonBounds(List<Offset> polygon) {
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
