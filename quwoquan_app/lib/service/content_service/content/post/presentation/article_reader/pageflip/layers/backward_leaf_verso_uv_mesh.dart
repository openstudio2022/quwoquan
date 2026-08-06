import 'dart:typed_data';
import 'dart:ui' as ui;
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

const double _polygonEpsilon = 0.001;

@immutable
class BackwardLeafVersoUvMesh {
  const BackwardLeafVersoUvMesh({
    required this.positions,
    required this.textureCoordinates,
    required this.indices,
    required this.paintBounds,
    required this.clipPolygon,
  });

  final List<Offset> positions;
  final List<Offset> textureCoordinates;
  final List<int> indices;
  final Rect paintBounds;
  final List<Offset> clipPolygon;

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

BackwardLeafVersoUvMesh? buildBackwardLeafVersoMaterialUvMesh({
  required Size pageSize,
  required List<Offset> materialLocalPolygon,
  int columns = 12,
  int rows = 16,
}) {
  if (pageSize.isEmpty ||
      materialLocalPolygon.length != 4 ||
      columns < 1 ||
      rows < 1) {
    return null;
  }
  final materialBounds = _polygonBounds(materialLocalPolygon);
  if (materialBounds == null ||
      materialBounds.width <= _polygonEpsilon ||
      materialBounds.height <= _polygonEpsilon ||
      _polygonArea(materialLocalPolygon) <= _polygonEpsilon) {
    return null;
  }

  final topLeft = materialLocalPolygon[0];
  final topRight = materialLocalPolygon[1];
  final bottomRight = materialLocalPolygon[2];
  final bottomLeft = materialLocalPolygon[3];
  final positions = <Offset>[];
  final textureCoordinates = <Offset>[];
  for (var row = 0; row <= rows; row += 1) {
    final v = row / rows;
    final left = Offset.lerp(topLeft, bottomLeft, v)!;
    final right = Offset.lerp(topRight, bottomRight, v)!;
    final materialY = pageSize.height * v;
    for (var column = 0; column <= columns; column += 1) {
      final u = column / columns;
      final materialX = pageSize.width * u;
      positions.add(Offset.lerp(left, right, u)!);
      textureCoordinates.add(Offset(materialX, materialY));
    }
  }

  final indices = <int>[];
  final stride = columns + 1;
  for (var row = 0; row < rows; row += 1) {
    for (var column = 0; column < columns; column += 1) {
      final topLeftIndex = row * stride + column;
      final topRightIndex = topLeftIndex + 1;
      final bottomLeftIndex = topLeftIndex + stride;
      final bottomRightIndex = bottomLeftIndex + 1;
      indices
        ..add(topLeftIndex)
        ..add(bottomLeftIndex)
        ..add(topRightIndex)
        ..add(topRightIndex)
        ..add(bottomLeftIndex)
        ..add(bottomRightIndex);
    }
  }

  return BackwardLeafVersoUvMesh(
    positions: List<Offset>.unmodifiable(positions),
    textureCoordinates: List<Offset>.unmodifiable(textureCoordinates),
    indices: List<int>.unmodifiable(indices),
    paintBounds: materialBounds,
    clipPolygon: List<Offset>.unmodifiable(materialLocalPolygon),
  );
}

BackwardLeafVersoUvMesh? buildBackwardLeafVersoPairedUvMesh({
  required Size pageSize,
  required List<Offset> displayLocalPolygon,
  required List<Offset> sourceAreaPolygon,
}) {
  if (pageSize.isEmpty ||
      displayLocalPolygon.length < 3 ||
      displayLocalPolygon.length != sourceAreaPolygon.length ||
      _polygonArea(displayLocalPolygon) <= _polygonEpsilon ||
      _polygonArea(sourceAreaPolygon) <= _polygonEpsilon) {
    return null;
  }

  final indices = <int>[];
  for (var index = 1; index < displayLocalPolygon.length - 1; index += 1) {
    indices
      ..add(0)
      ..add(index)
      ..add(index + 1);
  }
  return BackwardLeafVersoUvMesh(
    positions: List<Offset>.unmodifiable(displayLocalPolygon),
    textureCoordinates: List<Offset>.unmodifiable(sourceAreaPolygon),
    indices: List<int>.unmodifiable(indices),
    paintBounds:
        _polygonBounds(displayLocalPolygon) ?? (Offset.zero & pageSize),
    clipPolygon: List<Offset>.unmodifiable(displayLocalPolygon),
  );
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
