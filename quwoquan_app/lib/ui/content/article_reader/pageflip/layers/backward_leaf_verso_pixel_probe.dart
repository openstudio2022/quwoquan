import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_leaf_verso_uv_mesh.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

@immutable
class BackwardVersoPixelProbe {
  const BackwardVersoPixelProbe({
    required this.localPoints,
    required this.texturePoints,
  });

  final List<Offset> localPoints;
  final List<Offset> texturePoints;

  bool get isEmpty => localPoints.isEmpty;

  static const empty = BackwardVersoPixelProbe(
    localPoints: <Offset>[],
    texturePoints: <Offset>[],
  );
}

BackwardVersoPixelProbe resolveBackwardVersoPixelProbe({
  required Size pageSize,
  required List<Offset> polygon,
  required List<Offset> materialLocalPolygon,
  int maxPoints = 3,
}) {
  if (pageSize.isEmpty ||
      polygon.length < 3 ||
      materialLocalPolygon.length != 4 ||
      maxPoints <= 0) {
    return BackwardVersoPixelProbe.empty;
  }
  final bounds = _polygonBounds(polygon);
  if (bounds == null || bounds.width <= 0 || bounds.height <= 0) {
    return BackwardVersoPixelProbe.empty;
  }

  final preferredXFractions = <double>[0.14, 0.5, 0.86, 0.32, 0.68];
  final preferredYFractions = <double>[0.5, 0.35, 0.65];
  final minSpacing = math.max(
    3.0,
    math.min(bounds.width, bounds.height) * 0.14,
  );

  final localPoints = <Offset>[];
  for (final yFraction in preferredYFractions) {
    for (final xFraction in preferredXFractions) {
      final candidate = Offset(
        bounds.left + bounds.width * xFraction,
        bounds.top + bounds.height * yFraction,
      );
      if (!_pointInPolygon(candidate, polygon)) {
        continue;
      }
      if (localPoints.any(
        (existing) => (existing - candidate).distance < minSpacing,
      )) {
        continue;
      }
      localPoints.add(candidate);
      if (localPoints.length >= maxPoints) {
        final texturePoints = localPoints
            .map(
              (point) => _texturePointForMaterialLocalPoint(
                point: point,
                materialLocalPolygon: materialLocalPolygon,
                pageSize: pageSize,
              ),
            )
            .toList(growable: false);
        return BackwardVersoPixelProbe(
          localPoints: List<Offset>.unmodifiable(localPoints),
          texturePoints: List<Offset>.unmodifiable(texturePoints),
        );
      }
    }
  }

  if (localPoints.isEmpty) {
    return BackwardVersoPixelProbe.empty;
  }
  final texturePoints = localPoints
      .map(
        (point) => _texturePointForMaterialLocalPoint(
          point: point,
          materialLocalPolygon: materialLocalPolygon,
          pageSize: pageSize,
        ),
      )
      .toList(growable: false);
  return BackwardVersoPixelProbe(
    localPoints: List<Offset>.unmodifiable(localPoints),
    texturePoints: List<Offset>.unmodifiable(texturePoints),
  );
}

void paintBackwardLeafVersoSurface({
  required Canvas canvas,
  required ArticlePageTextureSnapshot leafVersoSnapshot,
  required Size pageSize,
  required List<Offset> polygon,
  required List<Offset> materialLocalPolygon,
  Offset paintOrigin = Offset.zero,
}) {
  final mesh = buildBackwardLeafVersoMaterialUvMesh(
    pageSize: pageSize,
    materialLocalPolygon: materialLocalPolygon,
  );
  if (mesh == null || polygon.length < 3) {
    return;
  }
  final path = Path()
    ..moveTo(
      polygon.first.dx - paintOrigin.dx,
      polygon.first.dy - paintOrigin.dy,
    );
  for (final point in polygon.skip(1)) {
    path.lineTo(point.dx - paintOrigin.dx, point.dy - paintOrigin.dy);
  }
  path.close();
  final drawVertices = _buildBackwardVersoDrawVertices(
    mesh: mesh,
    paintOrigin: paintOrigin,
    imageSize: Size(
      leafVersoSnapshot.image.width.toDouble(),
      leafVersoSnapshot.image.height.toDouble(),
    ),
    pageSize: pageSize,
  );
  final imageShader = ui.ImageShader(
    leafVersoSnapshot.image,
    ui.TileMode.clamp,
    ui.TileMode.clamp,
    Matrix4.identity().storage,
  );
  canvas.save();
  canvas.clipPath(path, doAntiAlias: false);
  canvas.drawVertices(
    drawVertices,
    BlendMode.src,
    Paint()
      ..isAntiAlias = false
      ..filterQuality = FilterQuality.none
      ..shader = imageShader,
  );
  canvas.restore();
}

ui.Vertices _buildBackwardVersoDrawVertices({
  required BackwardLeafVersoUvMesh mesh,
  required Offset paintOrigin,
  required Size imageSize,
  required Size pageSize,
}) {
  final positionValues = Float32List(mesh.positions.length * 2);
  final textureValues = Float32List(mesh.positions.length * 2);
  final textureScaleX = pageSize.width <= 0
      ? 1.0
      : imageSize.width / pageSize.width;
  final textureScaleY = pageSize.height <= 0
      ? 1.0
      : imageSize.height / pageSize.height;
  for (var index = 0; index < mesh.positions.length; index += 1) {
    final valueIndex = index * 2;
    final position = mesh.positions[index] - paintOrigin;
    final texture = mesh.textureCoordinates[index];
    positionValues[valueIndex] = position.dx;
    positionValues[valueIndex + 1] = position.dy;
    textureValues[valueIndex] = texture.dx * textureScaleX;
    textureValues[valueIndex + 1] = texture.dy * textureScaleY;
  }
  return ui.Vertices.raw(
    ui.VertexMode.triangles,
    positionValues,
    textureCoordinates: textureValues,
    indices: Uint16List.fromList(mesh.indices),
  );
}

Future<ui.Image?> renderBackwardLeafVersoProbeImage({
  required ArticlePageTextureSnapshot leafVersoSnapshot,
  required Size pageSize,
  required List<Offset> polygon,
  required List<Offset> materialLocalPolygon,
}) async {
  final mesh = buildBackwardLeafVersoMaterialUvMesh(
    pageSize: pageSize,
    materialLocalPolygon: materialLocalPolygon,
  );
  if (mesh == null) {
    return null;
  }

  final recorder = ui.PictureRecorder();
  final paintBounds = (_polygonBounds(polygon) ?? mesh.paintBounds).inflate(1);
  final canvas = Canvas(recorder, Offset.zero & paintBounds.size);
  paintBackwardLeafVersoSurface(
    canvas: canvas,
    leafVersoSnapshot: leafVersoSnapshot,
    pageSize: pageSize,
    polygon: polygon,
    materialLocalPolygon: materialLocalPolygon,
    paintOrigin: paintBounds.topLeft,
  );
  final picture = recorder.endRecording();
  final width = math.max(
    1,
    (paintBounds.width * leafVersoSnapshot.pixelWidthPerLogical).round(),
  );
  final height = math.max(
    1,
    (paintBounds.height * leafVersoSnapshot.pixelHeightPerLogical).round(),
  );
  final image = await picture.toImage(width, height);
  picture.dispose();
  return image;
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

Offset _texturePointForMaterialLocalPoint({
  required Offset point,
  required List<Offset> materialLocalPolygon,
  required Size pageSize,
}) {
  if (materialLocalPolygon.length != 4 || pageSize.isEmpty) {
    return Offset.zero;
  }
  final origin = materialLocalPolygon[0];
  final xAxis = materialLocalPolygon[1] - origin;
  final yAxis = materialLocalPolygon[3] - origin;
  final relative = point - origin;
  final determinant = xAxis.dx * yAxis.dy - xAxis.dy * yAxis.dx;
  if (determinant.abs() <= 0.000001) {
    return Offset.zero;
  }
  final u = (relative.dx * yAxis.dy - relative.dy * yAxis.dx) / determinant;
  final v = (xAxis.dx * relative.dy - xAxis.dy * relative.dx) / determinant;
  final materialX = (pageSize.width * u).clamp(0.0, pageSize.width);
  final materialY = (pageSize.height * v).clamp(0.0, pageSize.height);
  return Offset(materialX, materialY);
}

bool _pointInPolygon(Offset point, List<Offset> polygon) {
  var inside = false;
  for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    final pi = polygon[i];
    final pj = polygon[j];
    final intersects =
        ((pi.dy > point.dy) != (pj.dy > point.dy)) &&
        (point.dx <
            (pj.dx - pi.dx) *
                    (point.dy - pi.dy) /
                    ((pj.dy - pi.dy) + 0.000001) +
                pi.dx);
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}
