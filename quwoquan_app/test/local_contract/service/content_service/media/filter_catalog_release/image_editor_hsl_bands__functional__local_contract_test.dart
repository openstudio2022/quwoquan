// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-006
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-006.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-006.t2
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-006.t3
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_export_engine.dart';

/// HSL 分色相带真算法契约：只有目标色相带像素被调节，
/// 非目标带与灰阶像素逐字节不变，跨 0° 环绕带两侧均生效。
void main() {
  // 8 通道带区间与 UI（kImageEditorHslChannels）同源的测试镜像。
  const orangeBand = ImageEditorHslBandSpec(
    hueMin: 15,
    hueMax: 45,
    saturation: 100,
  );
  const redBand = ImageEditorHslBandSpec(hueMin: 345, hueMax: 15, hueShift: 100);
  const blueBand = ImageEditorHslBandSpec(
    hueMin: 195,
    hueMax: 255,
    luminance: 100,
  );

  Uint8List pixelOf(int r, int g, int b) =>
      Uint8List.fromList(<int>[r, g, b, 255]);

  test('只调橙色饱和度：橙色像素变化、蓝色与灰阶像素逐字节不变', () {
    // 橙色 hue≈30（核心区）、蓝色 hue≈225、中性灰。
    final orange = pixelOf(200, 130, 60);
    final blue = pixelOf(60, 100, 200);
    final gray = pixelOf(128, 128, 128);
    final orangeBefore = Uint8List.fromList(orange);
    final blueBefore = Uint8List.fromList(blue);
    final grayBefore = Uint8List.fromList(gray);

    ImageEditorExportEngine.applyHslBandsToRgbaPixels(orange, [orangeBand]);
    ImageEditorExportEngine.applyHslBandsToRgbaPixels(blue, [orangeBand]);
    ImageEditorExportEngine.applyHslBandsToRgbaPixels(gray, [orangeBand]);

    expect(orange, isNot(orderedEquals(orangeBefore)), reason: '目标带像素必须被调节');
    expect(blue, orderedEquals(blueBefore), reason: '非目标带像素必须逐字节不变');
    expect(gray, orderedEquals(grayBefore), reason: '灰阶像素不参与分带调节');
    expect(orange[3], 255, reason: 'alpha 不变');
  });

  test('饱和度正向调节后目标像素饱和度上升、色相基本不变', () {
    final orange = pixelOf(200, 130, 60);
    final before = _rgbToHsl(orange[0], orange[1], orange[2]);
    ImageEditorExportEngine.applyHslBandsToRgbaPixels(orange, [orangeBand]);
    final after = _rgbToHsl(orange[0], orange[1], orange[2]);
    expect(after.$2, greaterThan(before.$2), reason: '饱和度必须上升');
    expect((after.$1 - before.$1).abs(), lessThan(6), reason: '色相应基本不变');
  });

  test('跨 0° 红带环绕两侧均生效：355° 与 5° 像素都被 hueShift 调节', () {
    // hue≈355（红偏品）与 hue≈5（红偏橙）。
    final redHigh = pixelOf(220, 40, 55);
    final redLow = pixelOf(220, 55, 40);
    final highBefore = _rgbToHsl(redHigh[0], redHigh[1], redHigh[2]);
    final lowBefore = _rgbToHsl(redLow[0], redLow[1], redLow[2]);

    ImageEditorExportEngine.applyHslBandsToRgbaPixels(redHigh, [redBand]);
    ImageEditorExportEngine.applyHslBandsToRgbaPixels(redLow, [redBand]);

    final highAfter = _rgbToHsl(redHigh[0], redHigh[1], redHigh[2]);
    final lowAfter = _rgbToHsl(redLow[0], redLow[1], redLow[2]);
    // hueShift=100 → +30°；核心区权重 1。
    expect(
      _circularHueDelta(highBefore.$1, highAfter.$1),
      closeTo(30, 5),
      reason: '环绕高侧（355°）必须被推移约 30°',
    );
    expect(
      _circularHueDelta(lowBefore.$1, lowAfter.$1),
      closeTo(30, 5),
      reason: '环绕低侧（5°）必须被推移约 30°',
    );
  });

  test('带边界平滑过渡：过渡区像素调节量小于核心区', () {
    // 橙带 [15,45]：hue≈30 为核心，hue≈15 恰在带起点（权重≈0.5）。
    final core = pixelOf(200, 130, 60); // hue≈30
    final edge = pixelOf(210, 90, 58); // hue≈13 附近（过渡区）
    final coreBefore = _rgbToHsl(core[0], core[1], core[2]);
    final edgeBefore = _rgbToHsl(edge[0], edge[1], edge[2]);

    ImageEditorExportEngine.applyHslBandsToRgbaPixels(core, [orangeBand]);
    ImageEditorExportEngine.applyHslBandsToRgbaPixels(edge, [orangeBand]);

    final coreDelta =
        _rgbToHsl(core[0], core[1], core[2]).$2 - coreBefore.$2;
    final edgeDelta =
        _rgbToHsl(edge[0], edge[1], edge[2]).$2 - edgeBefore.$2;
    expect(coreDelta, greaterThan(0));
    expect(
      edgeDelta,
      lessThan(coreDelta),
      reason: '过渡区调节量必须小于核心区（平滑衰减）',
    );
  });

  test('明度按余量调节不削顶：亮部像素调亮后仍不溢出', () {
    final brightBlue = pixelOf(150, 180, 250);
    ImageEditorExportEngine.applyHslBandsToRgbaPixels(brightBlue, [blueBand]);
    expect(brightBlue[0], inInclusiveRange(0, 255));
    expect(brightBlue[2], inInclusiveRange(0, 255));
    final after = _rgbToHsl(brightBlue[0], brightBlue[1], brightBlue[2]);
    expect(after.$3, lessThanOrEqualTo(1.0));
    expect(after.$3, greaterThan(0.7), reason: '亮部像素调亮后应更亮且不削顶');
  });

  test('全零调节是恒等变换', () {
    final pixel = pixelOf(200, 130, 60);
    final before = Uint8List.fromList(pixel);
    ImageEditorExportEngine.applyHslBandsToRgbaPixels(pixel, const [
      ImageEditorHslBandSpec(hueMin: 15, hueMax: 45),
    ]);
    expect(pixel, orderedEquals(before));
  });
}

/// (hue 0..360, saturation 0..1, lightness 0..1)
(double, double, double) _rgbToHsl(int r8, int g8, int b8) {
  final r = r8 / 255.0;
  final g = g8 / 255.0;
  final b = b8 / 255.0;
  final maxC = [r, g, b].reduce((a, c) => a > c ? a : c);
  final minC = [r, g, b].reduce((a, c) => a < c ? a : c);
  final delta = maxC - minC;
  final l = (maxC + minC) / 2;
  if (delta < 1e-9) {
    return (0, 0, l);
  }
  final s = delta / (1 - (2 * l - 1).abs());
  double h;
  if (maxC == r) {
    h = 60 * (((g - b) / delta) % 6);
  } else if (maxC == g) {
    h = 60 * (((b - r) / delta) + 2);
  } else {
    h = 60 * (((r - g) / delta) + 4);
  }
  if (h < 0) h += 360;
  return (h, s, l);
}

double _circularHueDelta(double from, double to) {
  var delta = (to - from) % 360;
  if (delta < 0) delta += 360;
  return delta > 180 ? 360 - delta : delta;
}
