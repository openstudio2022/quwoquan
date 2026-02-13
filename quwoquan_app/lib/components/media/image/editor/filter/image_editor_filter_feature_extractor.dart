import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_recommendation_models.dart';

class ImageEditorFilterFeatureExtractor {
  const ImageEditorFilterFeatureExtractor();

  Future<ImageEditorFilterImageFeatures> extractFromBytes(Uint8List bytes) async {
    if (bytes.isEmpty) return const ImageEditorFilterImageFeatures();
    try {
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final image = frame.image;
      final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (data == null) return const ImageEditorFilterImageFeatures();
      final pixels = data.buffer.asUint8List();
      final width = image.width;
      final height = image.height;
      final sampleStep = math.max(1, math.max(width, height) ~/ 140);
      var count = 0;
      var sumLuma = 0.0;
      var sumLuma2 = 0.0;
      var sumSat = 0.0;
      var sumWarmth = 0.0;
      var edgeSum = 0.0;
      var shadowCount = 0;
      var highlightCount = 0;
      var skinCount = 0;
      var greenCount = 0;
      var blueCount = 0;
      var warmCount = 0;
      var grayCount = 0;
      int toIndex(int x, int y) => (y * width + x) * 4;
      for (var y = 0; y < height; y += sampleStep) {
        for (var x = 0; x < width; x += sampleStep) {
          final i = toIndex(x, y);
          final r = pixels[i].toDouble();
          final g = pixels[i + 1].toDouble();
          final b = pixels[i + 2].toDouble();
          final maxV = math.max(r, math.max(g, b));
          final minV = math.min(r, math.min(g, b));
          final luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0;
          final sat = maxV <= 0 ? 0.0 : (maxV - minV) / maxV;
          final warmth = (r - b) / (r + b + 1.0);
          if (luma < 0.22) shadowCount++;
          if (luma > 0.78) highlightCount++;
          if (g > r + 10 && g > b + 10) greenCount++;
          if (b > r + 10 && b > g + 6) blueCount++;
          if (r > g && g > b && r > b + 10) warmCount++;
          if (sat < 0.16) grayCount++;
          if (_isSkinLikePixel(r: r, g: g, b: b, luma: luma, sat: sat)) {
            skinCount++;
          }
          sumLuma += luma;
          sumLuma2 += luma * luma;
          sumSat += sat;
          sumWarmth += warmth;
          count++;

          final nx = math.min(width - 1, x + sampleStep);
          final ny = math.min(height - 1, y + sampleStep);
          final ix = toIndex(nx, y);
          final iy = toIndex(x, ny);
          final lumax = (0.2126 * pixels[ix] +
                  0.7152 * pixels[ix + 1] +
                  0.0722 * pixels[ix + 2]) /
              255.0;
          final lumay = (0.2126 * pixels[iy] +
                  0.7152 * pixels[iy + 1] +
                  0.0722 * pixels[iy + 2]) /
              255.0;
          edgeSum += (luma - lumax).abs() + (luma - lumay).abs();
        }
      }
      if (count == 0) return const ImageEditorFilterImageFeatures();
      final meanLuma = sumLuma / count;
      final variance = (sumLuma2 / count) - meanLuma * meanLuma;
      return ImageEditorFilterImageFeatures(
        meanLuma: meanLuma,
        contrast: math.sqrt(variance.clamp(0.0, 1.0).toDouble()),
        meanSaturation: (sumSat / count).clamp(0.0, 1.0).toDouble(),
        warmth: (sumWarmth / count).clamp(-1.0, 1.0).toDouble(),
        texture: (edgeSum / count).clamp(0.0, 1.0).toDouble(),
        shadowRatio: (shadowCount / count).clamp(0.0, 1.0).toDouble(),
        highlightRatio: (highlightCount / count).clamp(0.0, 1.0).toDouble(),
        skinRatio: (skinCount / count).clamp(0.0, 1.0).toDouble(),
        greenRatio: (greenCount / count).clamp(0.0, 1.0).toDouble(),
        blueRatio: (blueCount / count).clamp(0.0, 1.0).toDouble(),
        warmColorRatio: (warmCount / count).clamp(0.0, 1.0).toDouble(),
        grayRatio: (grayCount / count).clamp(0.0, 1.0).toDouble(),
        aspectRatio: width <= 0 || height <= 0 ? 1.0 : width / height,
      );
    } catch (_) {
      return const ImageEditorFilterImageFeatures();
    }
  }

  bool _isSkinLikePixel({
    required double r,
    required double g,
    required double b,
    required double luma,
    required double sat,
  }) {
    if (luma < 0.15 || luma > 0.92) return false;
    if (sat < 0.08 || sat > 0.68) return false;
    return r > 95 &&
        g > 40 &&
        b > 20 &&
        r > g &&
        r > b &&
        (r - g) > 8 &&
        (r - b) > 12;
  }
}
