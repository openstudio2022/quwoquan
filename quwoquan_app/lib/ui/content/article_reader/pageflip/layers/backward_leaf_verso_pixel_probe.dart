import 'dart:math' as math;
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

Offset backwardVersoTexturePoint({
  required Size pageSize,
  required Offset localPoint,
}) {
  return Offset(pageSize.width - localPoint.dx, localPoint.dy);
}

BackwardVersoPixelProbe resolveBackwardVersoPixelProbe({
  required Size pageSize,
  required List<Offset> polygon,
  int maxPoints = 3,
}) {
  if (pageSize.isEmpty || polygon.length < 3 || maxPoints <= 0) {
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
      if (localPoints.any((existing) => (existing - candidate).distance < minSpacing)) {
        continue;
      }
      localPoints.add(candidate);
      if (localPoints.length >= maxPoints) {
        final texturePoints = localPoints
            .map(
              (point) => backwardVersoTexturePoint(
                pageSize: pageSize,
                localPoint: point,
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
        (point) =>
            backwardVersoTexturePoint(pageSize: pageSize, localPoint: point),
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
}) {
  final mesh = buildBackwardLeafVersoUvMesh(
    pageSize: pageSize,
    polygon: polygon,
  );
  if (mesh == null) {
    return;
  }
  final shader = ui.ImageShader(
    leafVersoSnapshot.image,
    ui.TileMode.clamp,
    ui.TileMode.clamp,
    Matrix4.diagonal3Values(
      leafVersoSnapshot.pixelWidthPerLogical,
      leafVersoSnapshot.pixelHeightPerLogical,
      1,
    ).storage,
  );
  canvas.drawVertices(
    mesh.toVertices(),
    BlendMode.src,
    Paint()
      ..isAntiAlias = false
      ..filterQuality = FilterQuality.none
      ..shader = shader,
  );
}

Future<ui.Image?> renderBackwardLeafVersoProbeImage({
  required ArticlePageTextureSnapshot leafVersoSnapshot,
  required Size pageSize,
  required List<Offset> polygon,
}) async {
  final mesh = buildBackwardLeafVersoUvMesh(
    pageSize: pageSize,
    polygon: polygon,
  );
  if (mesh == null) {
    return null;
  }

  final recorder = ui.PictureRecorder();
  final canvas = Canvas(
    recorder,
    Rect.fromLTWH(0, 0, pageSize.width, pageSize.height),
  );
  paintBackwardLeafVersoSurface(
    canvas: canvas,
    leafVersoSnapshot: leafVersoSnapshot,
    pageSize: pageSize,
    polygon: polygon,
  );
  final picture = recorder.endRecording();
  final width = math.max(
    1,
    (pageSize.width * leafVersoSnapshot.pixelWidthPerLogical).round(),
  );
  final height = math.max(
    1,
    (pageSize.height * leafVersoSnapshot.pixelHeightPerLogical).round(),
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

bool _pointInPolygon(Offset point, List<Offset> polygon) {
  var inside = false;
  for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    final pi = polygon[i];
    final pj = polygon[j];
    final intersects =
        ((pi.dy > point.dy) != (pj.dy > point.dy)) &&
        (point.dx <
            (pj.dx - pi.dx) * (point.dy - pi.dy) / ((pj.dy - pi.dy) + 0.000001) +
                pi.dx);
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}
