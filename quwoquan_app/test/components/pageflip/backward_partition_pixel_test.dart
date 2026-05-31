import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_leaf_verso_pixel_probe.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

void main() {
  test(
    'BACK verso painter keeps UV fixed to material-local coordinates',
    () async {
      const pageSize = Size(400, 600);
      const paintPolygon = <Offset>[
        Offset(-80, 120),
        Offset(120, 120),
        Offset(120, 420),
        Offset(-80, 420),
      ];
      const materialLocalPolygon = <Offset>[
        Offset(-70, 120),
        Offset(330, 120),
        Offset(330, 420),
        Offset(-70, 420),
      ];
      final image = await _createHalfSplitBackImage(pageSize);
      final snapshot = ArticlePageTextureSnapshot(
        image: image,
        logicalSize: pageSize,
        pixelRatio: 1,
        semanticSurfaceKind: 'back',
      );

      final rendered = await renderBackwardLeafVersoProbeImage(
        leafVersoSnapshot: snapshot,
        pageSize: pageSize,
        polygon: paintPolygon,
        materialLocalPolygon: materialLocalPolygon,
      );
      expect(rendered, isNotNull);
      final bytes = await _rawRgbaBytes(rendered!);

      final paintOrigin = _polygonBounds(paintPolygon)!.inflate(1).topLeft;
      final localCenter = Offset.lerp(paintPolygon[0], paintPolygon[2], 0.5)!;
      final renderedColor = _colorAtBytes(
        rendered.width,
        rendered.height,
        bytes,
        localCenter - paintOrigin,
      );

      expect(
        renderedColor,
        _isNearColor(const Color(0xFF000000)),
        reason:
            'BACK verso fixed material UV must preserve the material-local direction '
            'for the angled baseline instead of applying an extra X reversal.',
      );

      rendered.dispose();
      snapshot.dispose();
    },
  );
}

Future<ui.Image> _createHalfSplitBackImage(Size size) async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder, Offset.zero & size);
  canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF00E5FF));
  canvas.drawRect(
    Rect.fromLTWH(0, 0, size.width * 0.5, size.height),
    Paint()..color = const Color(0xFF000000),
  );
  final picture = recorder.endRecording();
  final image = await picture.toImage(size.width.round(), size.height.round());
  picture.dispose();
  return image;
}

Future<Uint8List> _rawRgbaBytes(ui.Image image) async {
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  expect(data, isNotNull);
  return data!.buffer.asUint8List();
}

Color _colorAtBytes(int width, int height, Uint8List bytes, Offset point) {
  final x = point.dx.round().clamp(0, width - 1);
  final y = point.dy.round().clamp(0, height - 1);
  final index = (y * width + x) * 4;
  return Color.fromARGB(
    bytes[index + 3],
    bytes[index],
    bytes[index + 1],
    bytes[index + 2],
  );
}

Matcher _isNearColor(Color expected) {
  return predicate<Color>((actual) {
    int byte(double channel) => (channel * 255).round();
    return (byte(actual.r) - byte(expected.r)).abs() <= 4 &&
        (byte(actual.g) - byte(expected.g)).abs() <= 4 &&
        (byte(actual.b) - byte(expected.b)).abs() <= 4;
  }, 'near $expected');
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
    if (point.dx < left) {
      left = point.dx;
    }
    if (point.dy < top) {
      top = point.dy;
    }
    if (point.dx > right) {
      right = point.dx;
    }
    if (point.dy > bottom) {
      bottom = point.dy;
    }
  }
  return Rect.fromLTRB(left, top, right, bottom);
}
