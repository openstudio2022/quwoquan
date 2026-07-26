// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-001
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/curves/image_editor_curve_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/mosaic/image_editor_mosaic_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/text/image_editor_text_models.dart';
import 'package:quwoquan_app/components/media/image/editor/shared/image_editor_export_engine.dart';

/// 生成 [width]x[height] 的纯色测试图。
Future<ui.Image> _solidImage(
  int width,
  int height, {
  ui.Color color = const ui.Color(0xFF808080),
}) async {
  final recorder = ui.PictureRecorder();
  final canvas = ui.Canvas(recorder);
  canvas.drawRect(
    ui.Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble()),
    ui.Paint()..color = color,
  );
  return recorder.endRecording().toImage(width, height);
}

Future<Uint8List> _rgbaOf(ui.Image image) async {
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  return data!.buffer.asUint8List();
}

int _pixelChannel(Uint8List rgba, int width, int x, int y, int channel) {
  return rgba[(y * width + x) * 4 + channel];
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ImageEditorExportEngine.decodeConstrained', () {
    test('小图保持原尺寸，超限大图按长边降采样', () async {
      final small = await _solidImage(64, 32);
      final smallBytes = await ImageEditorExportEngine.encodePng(small);
      final decoded = await ImageEditorExportEngine.decodeConstrained(
        smallBytes!,
      );
      expect(decoded.width, 64);
      expect(decoded.height, 32);

      final wide = await _solidImage(400, 100);
      final wideBytes = await ImageEditorExportEngine.encodePng(wide);
      final constrained = await ImageEditorExportEngine.decodeConstrained(
        wideBytes!,
        maxDimension: 200,
      );
      expect(constrained.width, 200);
      expect(constrained.height, 50);
    });
  });

  group('applyColorMatrix', () {
    test('亮度矩阵抬高像素值且保持尺寸', () async {
      final image = await _solidImage(16, 16);
      // 亮度 +40：对角单位阵 + 偏移。
      final matrix = <double>[
        1,
        0,
        0,
        0,
        40,
        0,
        1,
        0,
        0,
        40,
        0,
        0,
        1,
        0,
        40,
        0,
        0,
        0,
        1,
        0,
      ];
      final adjusted = await ImageEditorExportEngine.applyColorMatrix(
        image,
        matrix,
      );
      expect(adjusted.width, 16);
      expect(adjusted.height, 16);
      final rgba = await _rgbaOf(adjusted);
      expect(_pixelChannel(rgba, 16, 8, 8, 0), greaterThan(0x80 + 30));
    });
  });

  group('cropImage / rotateAndFlip', () {
    test('裁剪输出紧贴源范围且像素来自正确区域', () async {
      final recorder = ui.PictureRecorder();
      final canvas = ui.Canvas(recorder);
      canvas.drawRect(
        const ui.Rect.fromLTWH(0, 0, 4, 4),
        ui.Paint()..color = const ui.Color(0xFFFF0000),
      );
      canvas.drawRect(
        const ui.Rect.fromLTWH(4, 0, 4, 4),
        ui.Paint()..color = const ui.Color(0xFF0000FF),
      );
      final image = await recorder.endRecording().toImage(8, 4);

      final cropped = await ImageEditorExportEngine.cropImage(
        image,
        const ui.Rect.fromLTWH(4, 0, 4, 4),
      );

      expect(cropped.width, 4);
      expect(cropped.height, 4);
      final rgba = await _rgbaOf(cropped);
      expect(_pixelChannel(rgba, 4, 2, 2, 0), lessThan(10));
      expect(_pixelChannel(rgba, 4, 2, 2, 2), greaterThan(245));
    });

    test('水平翻转与 180 度旋转保持原尺寸并改变对应像素方位', () async {
      final flipRecorder = ui.PictureRecorder();
      final flipCanvas = ui.Canvas(flipRecorder);
      flipCanvas.drawRect(
        const ui.Rect.fromLTWH(0, 0, 2, 2),
        ui.Paint()..color = const ui.Color(0xFFFF0000),
      );
      flipCanvas.drawRect(
        const ui.Rect.fromLTWH(2, 0, 2, 2),
        ui.Paint()..color = const ui.Color(0xFF0000FF),
      );
      final flipSource = await flipRecorder.endRecording().toImage(4, 2);
      final flipped = await ImageEditorExportEngine.rotateAndFlip(
        flipSource,
        totalDegrees: 0,
        scaleToFill: 1,
        flipHorizontal: true,
        flipVertical: false,
      );
      final flippedRgba = await _rgbaOf(flipped);
      expect(_pixelChannel(flippedRgba, 4, 0, 1, 2), greaterThan(245));
      expect(_pixelChannel(flippedRgba, 4, 3, 1, 0), greaterThan(245));

      final rotateRecorder = ui.PictureRecorder();
      final rotateCanvas = ui.Canvas(rotateRecorder);
      rotateCanvas.drawRect(
        const ui.Rect.fromLTWH(0, 0, 4, 2),
        ui.Paint()..color = const ui.Color(0xFFFF0000),
      );
      rotateCanvas.drawRect(
        const ui.Rect.fromLTWH(0, 2, 4, 2),
        ui.Paint()..color = const ui.Color(0xFF0000FF),
      );
      final rotateSource = await rotateRecorder.endRecording().toImage(4, 4);
      final rotated = await ImageEditorExportEngine.rotateAndFlip(
        rotateSource,
        totalDegrees: 180,
        scaleToFill: 1,
        flipHorizontal: false,
        flipVertical: false,
      );
      expect(rotated.width, 4);
      expect(rotated.height, 4);
      final rotatedRgba = await _rgbaOf(rotated);
      expect(_pixelChannel(rotatedRgba, 4, 2, 0, 2), greaterThan(245));
      expect(_pixelChannel(rotatedRgba, 4, 2, 3, 0), greaterThan(245));
    });
  });

  group('applyLocalAdjustments', () {
    test('径向锚点只改变中心区域，远端像素保持原样', () async {
      final image = await _solidImage(100, 100);
      final adjusted = await ImageEditorExportEngine.applyLocalAdjustments(
        image,
        <ImageEditorLocalRenderSpec>[
          ImageEditorLocalRenderSpec(
            center: const ui.Offset(0.5, 0.5),
            radiusOnShortSide: 0.25,
            colorMatrix: const <double>[
              1,
              0,
              0,
              0,
              60,
              0,
              1,
              0,
              0,
              60,
              0,
              0,
              1,
              0,
              60,
              0,
              0,
              0,
              1,
              0,
            ],
          ),
        ],
      );
      final rgba = await _rgbaOf(adjusted);

      expect(_pixelChannel(rgba, 100, 50, 50, 0), greaterThan(0x80 + 50));
      expect(
        (_pixelChannel(rgba, 100, 2, 2, 0) - 0x80).abs(),
        lessThanOrEqualTo(1),
      );
    });
  });

  group('applyCurves', () {
    test('提亮曲线抬高中间调像素', () async {
      final image = await _solidImage(16, 16);
      final curves = ImageEditorCurvesState(
        rgb: const [
          ImageEditorCurvePoint(0, 0.25),
          ImageEditorCurvePoint(1, 1),
        ],
      );
      final adjusted = await ImageEditorExportEngine.applyCurves(image, curves);
      final rgba = await _rgbaOf(adjusted);
      expect(_pixelChannel(rgba, 16, 8, 8, 0), greaterThan(0x80 + 20));
      expect(_pixelChannel(rgba, 16, 8, 8, 3), 255);
    });
  });

  group('applyMosaicStrokes', () {
    test('笔画区域像素被改变，笔画外保持原样', () async {
      // 左右两色图：左黑右白，在中心涂抹像素化马赛克。
      final recorder = ui.PictureRecorder();
      final canvas = ui.Canvas(recorder);
      canvas.drawRect(
        const ui.Rect.fromLTWH(0, 0, 50, 100),
        ui.Paint()..color = const ui.Color(0xFF000000),
      );
      canvas.drawRect(
        const ui.Rect.fromLTWH(50, 0, 50, 100),
        ui.Paint()..color = const ui.Color(0xFFFFFFFF),
      );
      final image = await recorder.endRecording().toImage(100, 100);
      const stroke = ImageEditorMosaicStroke(
        type: ImageEditorMosaicType.pixelate,
        brushRadiusOnShortSide: 0.12,
        points: <ui.Offset>[ui.Offset(0.5, 0.5)],
      );
      final composed = await ImageEditorExportEngine.applyMosaicStrokes(
        image,
        const [stroke],
      );
      expect(composed.width, 100);
      final rgba = await _rgbaOf(composed);
      // 笔画中心（黑白边界处）像素化后应为混合灰而非纯黑/纯白。
      final centerValue = _pixelChannel(rgba, 100, 49, 50, 0);
      expect(centerValue, greaterThan(10));
      expect(centerValue, lessThan(245));
      // 远离笔画的角落保持原色。
      expect(_pixelChannel(rgba, 100, 2, 2, 0), lessThan(10));
      expect(_pixelChannel(rgba, 100, 97, 2, 0), greaterThan(245));
    });
  });

  group('applyTextItems', () {
    test('文字项渲染改变中心区域像素，空列表恒等', () async {
      final image = await _solidImage(200, 100);
      final unchanged = await ImageEditorExportEngine.applyTextItems(
        image,
        const [],
      );
      expect(identical(unchanged, image), isTrue);

      const item = ImageEditorTextItem(
        id: 1,
        text: 'AA',
        style: ImageEditorTextStyleKind.backgroundBar,
        colorIndex: 1,
        center: ui.Offset(0.5, 0.5),
        fontSizeOnShortSide: 0.25,
        rotation: 0,
      );
      final composed = await ImageEditorExportEngine.applyTextItems(
        image,
        const [item],
      );
      final rgba = await _rgbaOf(composed);
      // 背景条样式：中心附近必有非底色像素（底色 0x80 灰）。
      var changed = 0;
      for (var y = 40; y < 60; y++) {
        for (var x = 90; x < 110; x++) {
          if ((_pixelChannel(rgba, 200, x, y, 0) - 0x80).abs() > 12) {
            changed++;
          }
        }
      }
      expect(changed, greaterThan(20));
    });
  });

  group('buildMosaicizedImage', () {
    test('像素化与模糊均保持输出尺寸', () async {
      final image = await _solidImage(80, 40);
      final pixelated = await ImageEditorExportEngine.buildMosaicizedImage(
        image,
        ImageEditorMosaicType.pixelate,
      );
      expect(pixelated.width, 80);
      expect(pixelated.height, 40);
      final blurred = await ImageEditorExportEngine.buildMosaicizedImage(
        image,
        ImageEditorMosaicType.blur,
      );
      expect(blurred.width, 80);
      expect(blurred.height, 40);
    });
  });

  group('encodeDeliveryJpeg（提交转码）', () {
    test('JPEG 编码可解码回同尺寸图像且颜色近似', () async {
      final image = await _solidImage(
        64,
        48,
        color: const ui.Color(0xFF2266AA),
      );
      final jpeg = await ImageEditorExportEngine.encodeDeliveryJpeg(image);
      expect(jpeg, isNotNull);
      // JPEG 魔数
      expect(jpeg![0], 0xFF);
      expect(jpeg[1], 0xD8);
      final decoded = await ImageEditorExportEngine.decodeConstrained(jpeg);
      expect(decoded.width, 64);
      expect(decoded.height, 48);
      final rgba = await _rgbaOf(decoded);
      expect((_pixelChannel(rgba, 64, 32, 24, 0) - 0x22).abs(), lessThan(16));
      expect((_pixelChannel(rgba, 64, 32, 24, 2) - 0xAA).abs(), lessThan(16));
    });

    test('isEditorBakedArtifactPath 只识别编辑器烘焙产物', () {
      expect(
        ImageEditorExportEngine.isEditorBakedArtifactPath(
          '/tmp/qwq/crop_1721444000000.png',
        ),
        isTrue,
      );
      expect(
        ImageEditorExportEngine.isEditorBakedArtifactPath(
          '/tmp/qwq/pro_curves_1721444000000.png',
        ),
        isTrue,
      );
      expect(
        ImageEditorExportEngine.isEditorBakedArtifactPath(
          '/var/album/IMG_2233.HEIC',
        ),
        isFalse,
      );
      expect(
        ImageEditorExportEngine.isEditorBakedArtifactPath(
          '/tmp/qwq/delivery_1721444000000.jpg',
        ),
        isFalse,
      );
    });
  });
}
