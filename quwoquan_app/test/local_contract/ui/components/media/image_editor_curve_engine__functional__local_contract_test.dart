import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/curves/image_editor_curve_models.dart';
import 'package:quwoquan_app/components/media/image/editor/shared/image_editor_export_engine.dart';

void main() {
  group('buildCurveLut', () {
    test('恒等曲线生成恒等 LUT', () {
      final lut = buildCurveLut(ImageEditorCurvesState.identityPoints);
      for (var i = 0; i < 256; i++) {
        expect((lut[i] - i).abs() <= 1, isTrue, reason: 'lut[$i]=${lut[i]}');
      }
    });

    test('单调递增控制点生成单调 LUT（Fritsch–Carlson 无过冲）', () {
      final lut = buildCurveLut(const [
        ImageEditorCurvePoint(0, 0),
        ImageEditorCurvePoint(0.25, 0.15),
        ImageEditorCurvePoint(0.75, 0.9),
        ImageEditorCurvePoint(1, 1),
      ]);
      for (var i = 1; i < 256; i++) {
        expect(
          lut[i] >= lut[i - 1],
          isTrue,
          reason: 'lut 应单调递增: lut[${i - 1}]=${lut[i - 1]}, lut[$i]=${lut[i]}',
        );
      }
      expect(lut[0], 0);
      expect(lut[255], 255);
    });

    test('S 曲线提升中段对比度（暗部压低、亮部抬高）', () {
      final lut = buildCurveLut(const [
        ImageEditorCurvePoint(0, 0),
        ImageEditorCurvePoint(0.3, 0.2),
        ImageEditorCurvePoint(0.7, 0.8),
        ImageEditorCurvePoint(1, 1),
      ]);
      expect(lut[64], lessThan(64));
      expect(lut[192], greaterThan(192));
    });

    test('提亮曲线整体抬高中间调', () {
      final lut = buildCurveLut(const [
        ImageEditorCurvePoint(0, 0),
        ImageEditorCurvePoint(0.5, 0.65),
        ImageEditorCurvePoint(1, 1),
      ]);
      expect(lut[128], greaterThan(128));
    });

    test('乱序输入点会被排序后插值', () {
      final unordered = buildCurveLut(const [
        ImageEditorCurvePoint(1, 1),
        ImageEditorCurvePoint(0.5, 0.65),
        ImageEditorCurvePoint(0, 0),
      ]);
      final ordered = buildCurveLut(const [
        ImageEditorCurvePoint(0, 0),
        ImageEditorCurvePoint(0.5, 0.65),
        ImageEditorCurvePoint(1, 1),
      ]);
      expect(unordered, orderedEquals(ordered));
    });
  });

  group('ImageEditorCurvesState', () {
    test('默认状态为恒等且 isIdentity 为 true', () {
      final state = ImageEditorCurvesState();
      expect(state.isIdentity, isTrue);
      for (final channel in ImageEditorCurveChannel.values) {
        expect(state.channelIsIdentity(channel), isTrue);
      }
    });

    test('修改单通道后不再恒等，withChannelPoints 不影响其它通道', () {
      final state = ImageEditorCurvesState().withChannelPoints(
        ImageEditorCurveChannel.red,
        const [ImageEditorCurvePoint(0, 0.1), ImageEditorCurvePoint(1, 0.9)],
      );
      expect(state.isIdentity, isFalse);
      expect(state.channelIsIdentity(ImageEditorCurveChannel.red), isFalse);
      expect(state.channelIsIdentity(ImageEditorCurveChannel.rgb), isTrue);
      expect(state.channelIsIdentity(ImageEditorCurveChannel.green), isTrue);
      expect(state.channelIsIdentity(ImageEditorCurveChannel.blue), isTrue);
    });

    test('wire roundtrip 保持控制点', () {
      final state = ImageEditorCurvesState(
        rgb: const [
          ImageEditorCurvePoint(0, 0),
          ImageEditorCurvePoint(0.4, 0.55),
          ImageEditorCurvePoint(1, 1),
        ],
        blue: const [
          ImageEditorCurvePoint(0, 0.05),
          ImageEditorCurvePoint(1, 0.95),
        ],
      );
      final restored = ImageEditorCurvesState.fromWire(
        Map<Object?, Object?>.from(state.toWire()),
      );
      expect(restored.rgb.length, 3);
      expect(restored.rgb[1].x, closeTo(0.4, 1e-9));
      expect(restored.rgb[1].y, closeTo(0.55, 1e-9));
      expect(restored.blue.first.y, closeTo(0.05, 1e-9));
      expect(restored.green.length, 2);
    });

    test('超出上限的控制点被截断到 maxPointsPerChannel', () {
      final points = List<ImageEditorCurvePoint>.generate(
        12,
        (i) => ImageEditorCurvePoint(i / 11, i / 11),
      );
      final state = ImageEditorCurvesState(rgb: points);
      expect(
        state.rgb.length,
        lessThanOrEqualTo(ImageEditorCurvesState.maxPointsPerChannel),
      );
    });
  });

  group('applyCurvesToRgbaPixels', () {
    test('恒等曲线不改变像素，alpha 恒不变', () {
      final pixels = Uint8List.fromList([10, 20, 30, 255, 200, 150, 100, 128]);
      final copy = Uint8List.fromList(pixels);
      ImageEditorExportEngine.applyCurvesToRgbaPixels(
        copy,
        ImageEditorCurvesState(),
      );
      expect(copy, orderedEquals(pixels));
    });

    test('RGB 主曲线提亮所有通道，单通道曲线只影响对应通道', () {
      final brighten = ImageEditorCurvesState(
        rgb: const [ImageEditorCurvePoint(0, 0.2), ImageEditorCurvePoint(1, 1)],
      );
      final pixels = Uint8List.fromList([100, 100, 100, 255]);
      ImageEditorExportEngine.applyCurvesToRgbaPixels(pixels, brighten);
      expect(pixels[0], greaterThan(100));
      expect(pixels[1], greaterThan(100));
      expect(pixels[2], greaterThan(100));
      expect(pixels[3], 255);

      final redOnly = ImageEditorCurvesState(
        red: const [ImageEditorCurvePoint(0, 0.3), ImageEditorCurvePoint(1, 1)],
      );
      final pixels2 = Uint8List.fromList([100, 100, 100, 255]);
      ImageEditorExportEngine.applyCurvesToRgbaPixels(pixels2, redOnly);
      expect(pixels2[0], greaterThan(100));
      expect(pixels2[1], 100);
      expect(pixels2[2], 100);
    });
  });
}
