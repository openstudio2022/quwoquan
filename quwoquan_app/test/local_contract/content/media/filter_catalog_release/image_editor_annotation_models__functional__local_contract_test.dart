// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-003
import 'dart:ui' show Offset, Size;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_mosaic_models.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_text_models.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_export_engine.dart';

void main() {
  group('ImageEditorMosaicStroke', () {
    test('wire roundtrip 保持类型/半径/点序列', () {
      const stroke = ImageEditorMosaicStroke(
        type: ImageEditorMosaicType.blur,
        brushRadiusOnShortSide: 0.05,
        points: <Offset>[Offset(0.1, 0.2), Offset(0.3, 0.4)],
      );
      final restored = ImageEditorMosaicStroke.fromWire(
        Map<Object?, Object?>.from(stroke.toWire()),
      );
      expect(restored, isNotNull);
      expect(restored!.type, ImageEditorMosaicType.blur);
      expect(restored.brushRadiusOnShortSide, closeTo(0.05, 1e-9));
      expect(restored.points.length, 2);
      expect(restored.points[1].dx, closeTo(0.3, 1e-9));
    });

    test('未知类型或空点序列返回 null', () {
      expect(
        ImageEditorMosaicStroke.fromWire(<Object?, Object?>{
          'type': 'unknown',
          'radius': 0.05,
          'points': <Object?>[],
        }),
        isNull,
      );
      expect(
        ImageEditorMosaicStroke.fromWire(<Object?, Object?>{
          'type': 'pixelate',
          'radius': 0.05,
          'points': <Object?>[],
        }),
        isNull,
      );
    });

    test('滑杆值到笔刷半径映射单调且有界', () {
      final small = mosaicBrushRadiusFromSlider(0);
      final mid = mosaicBrushRadiusFromSlider(0.5);
      final large = mosaicBrushRadiusFromSlider(1);
      expect(small, lessThan(mid));
      expect(mid, lessThan(large));
      expect(small, greaterThan(0));
      expect(large, lessThanOrEqualTo(0.2));
    });

    test('笔画路径覆盖笔画点（预览与导出同一几何）', () {
      const stroke = ImageEditorMosaicStroke(
        type: ImageEditorMosaicType.pixelate,
        brushRadiusOnShortSide: 0.05,
        points: <Offset>[Offset(0.5, 0.5), Offset(0.7, 0.5)],
      );
      final path = ImageEditorExportEngine.buildMosaicStrokePath(const [
        stroke,
      ], const Size(200, 100));
      expect(path.contains(const Offset(100, 50)), isTrue);
      expect(path.contains(const Offset(120, 50)), isTrue);
      expect(path.contains(const Offset(10, 10)), isFalse);
    });
  });

  group('ImageEditorTextItem', () {
    test('wire roundtrip 保持文本/样式/颜色/几何', () {
      const item = ImageEditorTextItem(
        id: 7,
        text: 'hello',
        style: ImageEditorTextStyleKind.backgroundBar,
        colorIndex: 2,
        center: Offset(0.25, 0.75),
        fontSizeOnShortSide: 0.08,
        rotation: 0.5,
      );
      final restored = ImageEditorTextItem.fromWire(
        Map<Object?, Object?>.from(item.toWire()),
      );
      expect(restored, isNotNull);
      expect(restored!.id, 7);
      expect(restored.text, 'hello');
      expect(restored.style, ImageEditorTextStyleKind.backgroundBar);
      expect(restored.colorIndex, 2);
      expect(restored.center.dx, closeTo(0.25, 1e-9));
      expect(restored.fontSizeOnShortSide, closeTo(0.08, 1e-9));
      expect(restored.rotation, closeTo(0.5, 1e-9));
    });

    test('空文本返回 null；字号被夹在合法区间', () {
      expect(
        ImageEditorTextItem.fromWire(<Object?, Object?>{'text': '  '}),
        isNull,
      );
      const item = ImageEditorTextItem(
        id: 1,
        text: 'x',
        style: ImageEditorTextStyleKind.plain,
        colorIndex: 0,
        center: Offset(0.5, 0.5),
        fontSizeOnShortSide: 0.06,
        rotation: 0,
      );
      final grown = item.copyWith(fontSizeOnShortSide: 5);
      expect(
        grown.fontSizeOnShortSide,
        ImageEditorTextItem.maxFontSizeOnShortSide,
      );
      final shrunk = item.copyWith(fontSizeOnShortSide: 0.001);
      expect(
        shrunk.fontSizeOnShortSide,
        ImageEditorTextItem.minFontSizeOnShortSide,
      );
    });

    test('描边色与背景条色随文字亮度自适应对比', () {
      const white = ImageEditorTextItem(
        id: 1,
        text: 'x',
        style: ImageEditorTextStyleKind.outline,
        colorIndex: 0,
        center: Offset(0.5, 0.5),
        fontSizeOnShortSide: 0.06,
        rotation: 0,
      );
      const black = ImageEditorTextItem(
        id: 2,
        text: 'x',
        style: ImageEditorTextStyleKind.outline,
        colorIndex: 1,
        center: Offset(0.5, 0.5),
        fontSizeOnShortSide: 0.06,
        rotation: 0,
      );
      expect(
        white.outlineColor.computeLuminance(),
        lessThan(white.color.computeLuminance()),
      );
      expect(
        black.outlineColor.computeLuminance(),
        greaterThan(black.color.computeLuminance()),
      );
    });
  });
}
