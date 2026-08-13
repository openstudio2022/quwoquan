// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-007
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-008
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-007.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-007.t2
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-007.t3
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-008
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-008.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-008.t2
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-008.t3
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_export_engine.dart';
import 'package:vector_math/vector_math_64.dart' show Matrix4;

/// 细节/分区/颗粒真算法契约：unsharp 增强边缘对比、分区调节不越区、
/// 颗粒增大像素方差且确定性可复现，替换旧「折算成对比度矩阵」伪装。
void main() {
  /// 生成 width×height 的 RGBA 灰度测试图。
  Uint8List grayImage(int width, int height, int Function(int x, int y) lumaAt) {
    final pixels = Uint8List(width * height * 4);
    for (var y = 0; y < height; y++) {
      for (var x = 0; x < width; x++) {
        final i = (y * width + x) * 4;
        final v = lumaAt(x, y).clamp(0, 255);
        pixels[i] = v;
        pixels[i + 1] = v;
        pixels[i + 2] = v;
        pixels[i + 3] = 255;
      }
    }
    return pixels;
  }

  int lumaOf(Uint8List pixels, int width, int x, int y) =>
      pixels[(y * width + x) * 4];

  test('锐化 unsharp mask 增强边缘对比：边缘两侧亮度差扩大、平坦区不变', () {
    const w = 32, h = 16;
    // 左半 80、右半 180 的垂直边缘图。
    final pixels = grayImage(w, h, (x, _) => x < w ~/ 2 ? 80 : 180);
    final before = Uint8List.fromList(pixels);

    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      pixels,
      w,
      h,
      const ImageEditorDetailSpec(sharpen: 100),
    );

    final beforeDelta =
        lumaOf(before, w, w ~/ 2, h ~/ 2) - lumaOf(before, w, w ~/ 2 - 1, h ~/ 2);
    final afterDelta =
        lumaOf(pixels, w, w ~/ 2, h ~/ 2) - lumaOf(pixels, w, w ~/ 2 - 1, h ~/ 2);
    expect(
      afterDelta,
      greaterThan(beforeDelta),
      reason: '边缘两侧对比必须被 unsharp 扩大',
    );
    // 远离边缘的平坦区基本不变（无全局对比度伪装）。
    expect(
      (lumaOf(pixels, w, 2, h ~/ 2) - 80).abs(),
      lessThanOrEqualTo(2),
      reason: '平坦区不得被全局改变',
    );
    expect(
      (lumaOf(pixels, w, w - 3, h ~/ 2) - 180).abs(),
      lessThanOrEqualTo(2),
    );
  });

  test('高光调节只作用亮部：暗部像素逐字节不变', () {
    const w = 8, h = 8;
    // 上半暗（40）、下半亮（220）。
    final pixels = grayImage(w, h, (_, y) => y < h ~/ 2 ? 40 : 220);
    final before = Uint8List.fromList(pixels);

    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      pixels,
      w,
      h,
      const ImageEditorDetailSpec(highlights: -100),
    );

    expect(
      lumaOf(pixels, w, 2, h - 2),
      lessThan(lumaOf(before, w, 2, h - 2)),
      reason: '压高光必须降低亮部亮度',
    );
    for (var x = 0; x < w; x++) {
      expect(
        lumaOf(pixels, w, x, 1),
        lumaOf(before, w, x, 1),
        reason: '暗部像素不得被高光调节触碰',
      );
    }
  });

  test('阴影调节只作用暗部：亮部像素逐字节不变', () {
    const w = 8, h = 8;
    final pixels = grayImage(w, h, (_, y) => y < h ~/ 2 ? 40 : 220);
    final before = Uint8List.fromList(pixels);

    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      pixels,
      w,
      h,
      const ImageEditorDetailSpec(shadows: 100),
    );

    expect(
      lumaOf(pixels, w, 2, 1),
      greaterThan(lumaOf(before, w, 2, 1)),
      reason: '提阴影必须提升暗部亮度',
    );
    for (var x = 0; x < w; x++) {
      expect(
        lumaOf(pixels, w, x, h - 2),
        lumaOf(before, w, x, h - 2),
        reason: '亮部像素不得被阴影调节触碰',
      );
    }
  });

  test('颗粒增大像素方差且同 seed 结果确定可复现', () {
    const w = 24, h = 24;
    final pixels = grayImage(w, h, (_, _) => 128);
    final again = Uint8List.fromList(pixels);

    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      pixels,
      w,
      h,
      const ImageEditorDetailSpec(grain: 100, grainSeed: 7),
    );
    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      again,
      w,
      h,
      const ImageEditorDetailSpec(grain: 100, grainSeed: 7),
    );

    double variance(Uint8List data) {
      var sum = 0.0;
      var count = 0;
      for (var i = 0; i + 3 < data.length; i += 4) {
        sum += data[i];
        count++;
      }
      final mean = sum / count;
      var acc = 0.0;
      for (var i = 0; i + 3 < data.length; i += 4) {
        acc += (data[i] - mean) * (data[i] - mean);
      }
      return acc / count;
    }

    expect(variance(pixels), greaterThan(9), reason: '颗粒必须产生真实噪声方差');
    expect(pixels, orderedEquals(again), reason: '同 seed 噪声必须逐字节可复现');
  });

  test('真 vibrance：低饱和像素提升多、已饱和像素受保护、灰阶不动', () {
    Uint8List pixel(int r, int g, int b) =>
        Uint8List.fromList(<int>[r, g, b, 255]);
    double saturationOf(Uint8List p) {
      final r = p[0] / 255.0, g = p[1] / 255.0, b = p[2] / 255.0;
      final maxC = [r, g, b].reduce((a, c) => a > c ? a : c);
      final minC = [r, g, b].reduce((a, c) => a < c ? a : c);
      final delta = maxC - minC;
      final l = (maxC + minC) / 2;
      if (delta < 1e-9 || l <= 0 || l >= 1) return 0;
      return delta / (1 - (2 * l - 1).abs());
    }

    const spec = ImageEditorDetailSpec(vibrance: 100);
    // 低饱和蓝（远离肤色带）、高饱和蓝、中性灰。
    final lowSat = pixel(120, 130, 160);
    final highSat = pixel(20, 40, 245);
    final gray = pixel(128, 128, 128);
    final lowBefore = saturationOf(lowSat);
    final highBefore = saturationOf(highSat);
    final grayBefore = Uint8List.fromList(gray);

    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      lowSat, 1, 1, spec,
    );
    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      highSat, 1, 1, spec,
    );
    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      gray, 1, 1, spec,
    );

    final lowGain = saturationOf(lowSat) - lowBefore;
    final highGain = saturationOf(highSat) - highBefore;
    expect(lowGain, greaterThan(0), reason: '低饱和像素必须被提升');
    expect(
      lowGain,
      greaterThan(highGain),
      reason: '已饱和像素增益必须小于低饱和像素（保护不削顶）',
    );
    expect(saturationOf(highSat), lessThanOrEqualTo(1.0));
    expect(gray, orderedEquals(grayBefore), reason: '灰阶不参与 vibrance');
  });

  test('真 vibrance：肤色带增益弱于同饱和度的非肤色带', () {
    Uint8List pixel(int r, int g, int b) =>
        Uint8List.fromList(<int>[r, g, b, 255]);
    double saturationOf(Uint8List p) {
      final r = p[0] / 255.0, g = p[1] / 255.0, b = p[2] / 255.0;
      final maxC = [r, g, b].reduce((a, c) => a > c ? a : c);
      final minC = [r, g, b].reduce((a, c) => a < c ? a : c);
      final delta = maxC - minC;
      final l = (maxC + minC) / 2;
      if (delta < 1e-9 || l <= 0 || l >= 1) return 0;
      return delta / (1 - (2 * l - 1).abs());
    }

    const spec = ImageEditorDetailSpec(vibrance: 100);
    // 肤色（hue≈27）与青色（hue≈187），构造近似相同的中等饱和度。
    final skin = pixel(190, 150, 120);
    final cyan = pixel(120, 182, 190);
    final skinBefore = saturationOf(skin);
    final cyanBefore = saturationOf(cyan);

    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      skin, 1, 1, spec,
    );
    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      cyan, 1, 1, spec,
    );

    final skinGain = saturationOf(skin) - skinBefore;
    final cyanGain = saturationOf(cyan) - cyanBefore;
    expect(
      skinGain,
      lessThan(cyanGain),
      reason: '肤色带增益必须弱于非肤色带（人像保护）',
    );
  });

  test('降噪：平坦区噪声方差下降、强边缘对比保留', () {
    const w = 32, h = 32;
    // 左半 90 底 + 确定性噪声、右半 200 平坦：验证平滑与保边同时成立。
    final pixels = grayImage(w, h, (x, y) {
      if (x < w ~/ 2) {
        return 90 + (((x * 31 + y * 17) % 7) - 3) * 6;
      }
      return 200;
    });
    final before = Uint8List.fromList(pixels);

    double regionVariance(Uint8List data, int x0, int x1) {
      var sum = 0.0;
      var count = 0;
      for (var y = 2; y < h - 2; y++) {
        for (var x = x0; x < x1; x++) {
          sum += data[(y * w + x) * 4];
          count++;
        }
      }
      final mean = sum / count;
      var acc = 0.0;
      for (var y = 2; y < h - 2; y++) {
        for (var x = x0; x < x1; x++) {
          final v = data[(y * w + x) * 4];
          acc += (v - mean) * (v - mean);
        }
      }
      return acc / count;
    }

    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      pixels,
      w,
      h,
      const ImageEditorDetailSpec(denoise: 100),
    );

    expect(
      regionVariance(pixels, 2, w ~/ 2 - 3),
      lessThan(regionVariance(before, 2, w ~/ 2 - 3)),
      reason: '平坦噪声区方差必须下降',
    );
    // 强边缘（90/200 交界）两侧对比保留大半。
    final beforeEdge = lumaOf(before, w, w ~/ 2, h ~/ 2) -
        lumaOf(before, w, w ~/ 2 - 1, h ~/ 2);
    final afterEdge = lumaOf(pixels, w, w ~/ 2, h ~/ 2) -
        lumaOf(pixels, w, w ~/ 2 - 1, h ~/ 2);
    expect(
      afterEdge,
      greaterThan((beforeEdge * 0.5).round()),
      reason: '强边缘对比必须保留（保边）',
    );
  });

  test('局部锚点真算法：半径内细节与色彩生效、半径外逐字节不变（OPEN-002）', () {
    const w = 64, h = 64;
    // 全图统一中灰 + 微噪声，锚点在左上角落（半径 0.25 短边）。
    final pixels = grayImage(w, h, (x, y) => 128 + ((x * 7 + y * 13) % 5) - 2);
    final before = Uint8List.fromList(pixels);
    // 单位矩阵（无色彩变化），只有细节类锐化——旧矩阵近似下这不可能生效。
    final identityMatrix = <double>[
      1, 0, 0, 0, 0, //
      0, 1, 0, 0, 0, //
      0, 0, 1, 0, 0, //
      0, 0, 0, 1, 0, //
    ];
    ImageEditorExportEngine.applyLocalAdjustmentsToRgbaPixels(
      pixels,
      w,
      h,
      <ImageEditorLocalRenderSpec>[
        ImageEditorLocalRenderSpec(
          center: const Offset(0.2, 0.2),
          radiusOnShortSide: 0.25,
          colorMatrix: identityMatrix,
          detail: const ImageEditorDetailSpec(structure: 100),
        ),
      ],
    );

    // 锚点中心附近像素被细节调节触碰。
    var centerChanged = false;
    for (var y = 10; y < 16 && !centerChanged; y++) {
      for (var x = 10; x < 16; x++) {
        if (lumaOf(pixels, w, x, y) != lumaOf(before, w, x, y)) {
          centerChanged = true;
          break;
        }
      }
    }
    expect(centerChanged, isTrue, reason: '锚点半径内必须有细节调节效果');

    // 远离锚点（右下象限）逐字节不变。
    for (var y = h - 12; y < h; y++) {
      for (var x = w - 12; x < w; x++) {
        final i = (y * w + x) * 4;
        expect(
          pixels[i],
          before[i],
          reason: '锚点半径外像素必须逐字节不变 ($x,$y)',
        );
      }
    }
  });

  test('局部径向权重与预览渐变分段一致：核心区满权重、边界外为零', () {
    expect(ImageEditorExportEngine.localRadialWeight(0), 1.0);
    expect(
      ImageEditorExportEngine.localRadialWeight(0.22),
      closeTo(0.90, 0.001),
    );
    expect(
      ImageEditorExportEngine.localRadialWeight(0.56),
      closeTo(0.58, 0.001),
    );
    expect(
      ImageEditorExportEngine.localRadialWeight(0.84),
      closeTo(0.22, 0.001),
    );
    expect(ImageEditorExportEngine.localRadialWeight(1.0), 0.0);
    expect(ImageEditorExportEngine.localRadialWeight(1.2), 0.0);
    // 分段中点是线性插值。
    expect(
      ImageEditorExportEngine.localRadialWeight(0.11),
      closeTo(0.95, 0.001),
    );
  });

  group('PerspectiveGeometry — 透视校正同源几何 (GWT-008)', () {
    test('水平透视：左右边缘产生对称深度位移，方向随符号翻转', () {
      final positive = PerspectiveGeometry(
        width: 400,
        height: 300,
        horizontalDegrees: 20,
        verticalDegrees: 0,
      ).projectedCorners();
      final negative = PerspectiveGeometry(
        width: 400,
        height: 300,
        horizontalDegrees: -20,
        verticalDegrees: 0,
      ).projectedCorners();
      // 正角度：rotateY 使一侧靠近观察者（放大）、另一侧远离（收缩）。
      final positiveLeftHeight = (positive[3].dy - positive[0].dy).abs();
      final positiveRightHeight = (positive[2].dy - positive[1].dy).abs();
      expect(
        (positiveLeftHeight - positiveRightHeight).abs(),
        greaterThan(1),
        reason: '水平透视必须让左右边缘高度不等（梯形）',
      );
      // 反号后近远侧交换。
      final negativeLeftHeight = (negative[3].dy - negative[0].dy).abs();
      final negativeRightHeight = (negative[2].dy - negative[1].dy).abs();
      expect(
        positiveLeftHeight > positiveRightHeight,
        !(negativeLeftHeight > negativeRightHeight),
        reason: '透视方向必须随角度符号翻转',
      );
      // 垂直方向对称：上下角位移镜像。
      expect(
        positiveLeftHeight,
        closeTo(negativeRightHeight, 0.5),
        reason: '±同角度的近侧边高必须对称',
      );
    });

    test('垂直透视：上下边缘产生梯形位移', () {
      final corners = PerspectiveGeometry(
        width: 400,
        height: 300,
        horizontalDegrees: 0,
        verticalDegrees: 18,
      ).projectedCorners();
      final topWidth = (corners[1].dx - corners[0].dx).abs();
      final bottomWidth = (corners[2].dx - corners[3].dx).abs();
      expect(
        (topWidth - bottomWidth).abs(),
        greaterThan(1),
        reason: '垂直透视必须让上下边缘宽度不等',
      );
    });

    test('填充缩放：变换后画面完整覆盖原范围框（无露底）', () {
      final geometry = PerspectiveGeometry(
        width: 400,
        height: 300,
        horizontalDegrees: 25,
        verticalDegrees: -15,
      );
      expect(geometry.scaleToFill(), greaterThan(1.0));
      final quad = geometry.projectedCorners();
      // 原范围框四角必须在投影四边形内（凸包含，叉积同侧）。
      final rectCorners = <Offset>[
        const Offset(0, 0),
        const Offset(400, 0),
        const Offset(400, 300),
        const Offset(0, 300),
      ];
      for (final point in rectCorners) {
        for (var i = 0; i < 4; i++) {
          final a = quad[i];
          final b = quad[(i + 1) % 4];
          final cross =
              (b.dx - a.dx) * (point.dy - a.dy) -
              (b.dy - a.dy) * (point.dx - a.dx);
          expect(
            cross,
            greaterThanOrEqualTo(-0.5),
            reason: '原范围框角 $point 必须在填充后的投影四边形内',
          );
        }
      }
    });

    test('预览核与烘焙矩阵同源：中心化核加平移等于完整矩阵', () {
      final geometry = PerspectiveGeometry(
        width: 320,
        height: 240,
        horizontalDegrees: 12,
        verticalDegrees: -8,
      );
      final full = geometry.transformWithFill().storage;
      final rebuilt =
          (Matrix4.translationValues(160, 120, 0) *
                  geometry.centeredTransformWithFill() *
                  Matrix4.translationValues(-160, -120, 0))
              .storage;
      for (var i = 0; i < 16; i++) {
        expect(full[i], closeTo(rebuilt[i], 1e-9));
      }
    });

    test('恒等参数：无缩放、角点原位', () {
      final geometry = PerspectiveGeometry(
        width: 400,
        height: 300,
        horizontalDegrees: 0,
        verticalDegrees: 0,
      );
      expect(geometry.isIdentity, isTrue);
      expect(geometry.scaleToFill(), 1.0);
      final corners = geometry.projectedCorners();
      expect(corners[0].dx, closeTo(0, 1e-6));
      expect(corners[2].dx, closeTo(400, 1e-6));
      expect(corners[2].dy, closeTo(300, 1e-6));
    });
  });

  test('全零 spec 是恒等变换', () {
    const w = 8, h = 8;
    final pixels = grayImage(w, h, (x, y) => (x * 13 + y * 7) % 256);
    final before = Uint8List.fromList(pixels);
    ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
      pixels,
      w,
      h,
      const ImageEditorDetailSpec(),
    );
    expect(pixels, orderedEquals(before));
  });
}
