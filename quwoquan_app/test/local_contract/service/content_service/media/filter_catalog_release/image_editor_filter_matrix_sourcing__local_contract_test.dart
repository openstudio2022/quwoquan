// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#req-005
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-009
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-009.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-009.t2
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-009.t3
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-009.t4
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-009.t5
//
// 滤镜链同源合同（GWT-009）：滤镜纯色彩矩阵不得响应细节类参数（细节走
// ImageEditorDetailSpec 逐像素管线，与整体面板同源）；fade 为显式声明的
// 黑场抬升精确线性实现。
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_matrix.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_export_engine.dart';

ImageEditorFilterPreset _preset(ImageEditorFilterAdjustments adjustments) {
  return ImageEditorFilterPreset(
    id: 'preset-test',
    categoryId: 'cat',
    name: '测试',
    sort: 0,
    enabled: true,
    defaultStrength: 100,
    adjustments: adjustments,
  );
}

/// 对像素 (r,g,b) 应用 4x5 矩阵。
List<double> _apply(List<double> m, double r, double g, double b) {
  return <double>[
    m[0] * r + m[1] * g + m[2] * b + m[4],
    m[5] * r + m[6] * g + m[7] * b + m[9],
    m[10] * r + m[11] * g + m[12] * b + m[14],
  ];
}

void main() {
  test('细节类参数不进滤镜矩阵：仅含细节参数的滤镜矩阵为恒等', () {
    final preset = _preset(
      const ImageEditorFilterAdjustments(
        vibrance: 60,
        texture: 40,
        sharpen: 50,
        structure: 30,
        highlight: -20,
        shadow: 25,
        grain: 35,
        lightSense: 45,
      ),
    );
    final matrix = buildImageEditorFilterColorMatrix(preset, 100);
    final identity = imageEditorIdentityColorMatrix();
    for (var i = 0; i < 20; i++) {
      expect(
        matrix[i],
        closeTo(identity[i], 1e-9),
        reason: '细节参数折算进矩阵即为系数伪装（index $i）',
      );
    }
  });

  test('细节类参数经 buildImageEditorFilterDetailValues 完整导出并随强度缩放', () {
    final preset = _preset(
      const ImageEditorFilterAdjustments(
        vibrance: 60,
        sharpen: 50,
        grain: 40,
        contrast: 30,
        brightness: 10,
      ),
    );
    final full = buildImageEditorFilterDetailValues(preset, 100);
    expect(full.keys.toSet(), <String>{'vibrance', 'sharpen', 'grain'});
    expect(full['vibrance'], greaterThan(0));
    // 纯色彩参数不得混入细节表。
    expect(full.containsKey('contrast'), isFalse);
    expect(full.containsKey('brightness'), isFalse);

    final half = buildImageEditorFilterDetailValues(preset, 50);
    expect(
      half['vibrance']!,
      closeTo(full['vibrance']! / 2, 1e-9),
      reason: '细节参数必须随强度线性缩放（与矩阵同一缩放）',
    );
    expect(imageEditorFilterHasDetailParams(preset), isTrue);
    expect(
      imageEditorFilterHasDetailParams(
        _preset(const ImageEditorFilterAdjustments(contrast: 30)),
      ),
      isFalse,
    );
  });

  test('fade 是精确黑场抬升：黑点抬升至 lift、白点不动', () {
    final matrix = buildImageEditorBaseColorMatrix(<String, double>{
      'fade': 100.0,
    });
    final black = _apply(matrix, 0, 0, 0);
    final white = _apply(matrix, 255, 255, 255);
    final expectedLift = 255 * kImageEditorFadeMaxLift;
    for (final channel in black) {
      expect(
        channel,
        closeTo(expectedLift, 0.5),
        reason: 'fade 满值黑点必须精确抬升到 lift×255',
      );
    }
    for (final channel in white) {
      expect(channel, closeTo(255, 0.5), reason: 'fade 白点必须不动');
    }
    // 半强度：抬升按比例。
    final halfMatrix = buildImageEditorBaseColorMatrix(<String, double>{
      'fade': 50.0,
    });
    final halfBlack = _apply(halfMatrix, 0, 0, 0);
    expect(halfBlack.first, closeTo(expectedLift / 2, 0.5));
  });

  test('纯色彩矩阵仍承载标准线性调节（亮度/对比示例）', () {
    final matrix = buildImageEditorBaseColorMatrix(<String, double>{
      'brightness': 20.0,
    });
    final mid = _apply(matrix, 128, 128, 128);
    expect(mid.first, closeTo(128 + 0.2 * 255, 0.5));
  });

  test('含细节滤镜：CPU 预览像素组合与烘焙 applyBaseAdjustments 逐字节一致', () async {
    const w = 32, h = 32;
    final preset = _preset(
      const ImageEditorFilterAdjustments(
        contrast: 20,
        vibrance: 45,
        sharpen: 35,
        grain: 25,
      ),
    );
    const strength = 80.0;
    final matrix = buildImageEditorFilterColorMatrix(preset, strength);
    final detailValues = buildImageEditorFilterDetailValues(preset, strength);
    final detail = ImageEditorDetailSpec(
      vibrance: detailValues['vibrance'] ?? 0,
      sharpen: detailValues['sharpen'] ?? 0,
      grain: detailValues['grain'] ?? 0,
    );
    final source = Uint8List(w * h * 4);
    for (var p = 0, i = 0; p < w * h; p++, i += 4) {
      final v = 40 + ((p * 7) % 170);
      source[i] = v;
      source[i + 1] = (v + 20).clamp(0, 255);
      source[i + 2] = (v - 15).clamp(0, 255);
      source[i + 3] = 255;
    }

    // 预览路径：CPU session 的像素函数组合。
    final previewPixels = Uint8List.fromList(source);
    ImageEditorExportEngine.applyColorMatrixToRgbaPixels(
      previewPixels,
      matrix,
    );
    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      previewPixels, w, h, detail,
    );

    // 烘焙路径：applyBaseAdjustments。
    final buffer = await ui.ImmutableBuffer.fromUint8List(source);
    final descriptor = ui.ImageDescriptor.raw(
      buffer, width: w, height: h, pixelFormat: ui.PixelFormat.rgba8888,
    );
    final codec = await descriptor.instantiateCodec();
    final frame = await codec.getNextFrame();
    final baked = await ImageEditorExportEngine.applyBaseAdjustments(
      frame.image,
      colorMatrix: matrix,
      detail: detail,
    );
    final bakedData = await baked.toByteData(
      format: ui.ImageByteFormat.rawRgba,
    );
    final bakedPixels = bakedData!.buffer.asUint8List();
    for (var i = 0; i < previewPixels.length; i++) {
      expect(
        bakedPixels[i],
        previewPixels[i],
        reason: '滤镜 CPU 预览与烘焙必须同一管线逐字节一致（byte $i）',
      );
    }
  });

  test('纯色彩滤镜：细节表为空，矩阵即全部效果（GPU 分轨依据）', () {
    final preset = _preset(
      const ImageEditorFilterAdjustments(
        contrast: 30,
        saturation: -20,
        temperature: 15,
      ),
    );
    expect(imageEditorFilterHasDetailParams(preset), isFalse);
    expect(buildImageEditorFilterDetailValues(preset, 100), isEmpty);
    // 矩阵非恒等（承载全部效果）。
    final matrix = buildImageEditorFilterColorMatrix(preset, 100);
    final identity = imageEditorIdentityColorMatrix();
    expect(
      List<double>.generate(20, (i) => (matrix[i] - identity[i]).abs())
          .reduce((a, b) => a + b),
      greaterThan(0.01),
    );
  });
}
