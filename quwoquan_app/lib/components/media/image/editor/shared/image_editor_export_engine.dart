import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart' show compute;
import 'package:flutter/painting.dart';
import 'package:image/image.dart' as img;
import 'package:quwoquan_app/components/media/image/editor/panels/curves/image_editor_curve_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/mosaic/image_editor_mosaic_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/text/image_editor_text_models.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

/// 图片编辑像素导出引擎：预览与导出共用同一几何/合成真相源。
///
/// 所有函数是纯 bytes/ui.Image 变换，不依赖页面状态，可在 local_contract 中直接测试。
class ImageEditorExportEngine {
  const ImageEditorExportEngine._();

  /// 解码上限：超过该长边的图片按比例降采样，防止全尺寸解码 OOM。
  static const int kMaxDecodeDimension = 4096;

  /// 预览处理用降采样长边（曲线/马赛克预览底图）。
  static const int kPreviewDecodeDimension = 1440;

  /// 约束解码：保持宽高比，长边超过 [maxDimension] 时降采样。
  static Future<ui.Image> decodeConstrained(
    Uint8List bytes, {
    int maxDimension = kMaxDecodeDimension,
  }) async {
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    ui.Codec? codec;
    try {
      codec = await ui.instantiateImageCodecWithSize(
        buffer,
        getTargetSize: (int width, int height) {
          final longest = math.max(width, height);
          if (longest <= maxDimension) {
            return ui.TargetImageSize(width: width, height: height);
          }
          final scale = maxDimension / longest;
          return ui.TargetImageSize(
            width: (width * scale).round().clamp(1, width),
            height: (height * scale).round().clamp(1, height),
          );
        },
      );
      final frame = await codec.getNextFrame();
      return frame.image;
    } finally {
      codec?.dispose();
      // instantiateImageCodecWithSize 接管 ImmutableBuffer；codec.dispose()
      // 会释放其所有权，调用方不可再次 dispose。
    }
  }

  static Future<Uint8List?> encodePng(ui.Image image) async {
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    return data?.buffer.asUint8List();
  }

  /// 提交转码 JPEG 质量（编辑管线内部保持 PNG 无损，提交时一次性压缩）。
  static const int kDeliveryJpegQuality = 92;

  /// 将编辑结果 RGBA 像素编码为交付 JPEG（isolate 内执行，防 UI 卡顿）。
  ///
  /// 返回 null 表示编码失败，调用方应回退原文件。
  static Future<Uint8List?> encodeDeliveryJpeg(
    ui.Image image, {
    int quality = kDeliveryJpegQuality,
  }) async {
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    if (data == null) return null;
    return compute(
      _encodeJpegInIsolate,
      _JpegEncodeRequest(
        rgba: data.buffer.asUint8List(),
        width: image.width,
        height: image.height,
        quality: quality,
      ),
    );
  }

  /// 应用 4x5 颜色矩阵。
  static Future<ui.Image> applyColorMatrix(
    ui.Image image,
    List<double> matrix,
  ) async {
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    final rect = ui.Rect.fromLTWH(
      0,
      0,
      image.width.toDouble(),
      image.height.toDouble(),
    );
    final paint = ui.Paint()..colorFilter = ui.ColorFilter.matrix(matrix);
    canvas.drawImageRect(image, rect, rect, paint);
    return recorder.endRecording().toImage(image.width, image.height);
  }

  /// 按源图像素坐标裁剪，并输出紧贴裁剪范围的新图。
  static Future<ui.Image> cropImage(ui.Image image, ui.Rect sourceRect) async {
    final imageBounds = ui.Rect.fromLTWH(
      0,
      0,
      image.width.toDouble(),
      image.height.toDouble(),
    );
    final safeSource = sourceRect.intersect(imageBounds);
    if (safeSource.isEmpty) {
      throw ArgumentError.value(sourceRect, 'sourceRect', '裁剪范围必须与图像相交');
    }
    final outputWidth = math.max(1, safeSource.width.round());
    final outputHeight = math.max(1, safeSource.height.round());
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    canvas.drawImageRect(
      image,
      safeSource,
      ui.Rect.fromLTWH(0, 0, outputWidth.toDouble(), outputHeight.toDouble()),
      ui.Paint(),
    );
    return recorder.endRecording().toImage(outputWidth, outputHeight);
  }

  /// 以图像中心旋转/翻转，并裁回原始范围框。
  ///
  /// [scaleToFill] 必须由共享的 [RotateGeometry.scaleToFill] 计算，确保预览
  /// 与导出使用同一范围框几何。
  static Future<ui.Image> rotateAndFlip(
    ui.Image image, {
    required double totalDegrees,
    required double scaleToFill,
    required bool flipHorizontal,
    required bool flipVertical,
  }) async {
    if (!scaleToFill.isFinite || scaleToFill <= 0) {
      throw ArgumentError.value(scaleToFill, 'scaleToFill', '旋转填充缩放必须为有限正数');
    }
    final outputWidth = image.width.toDouble();
    final outputHeight = image.height.toDouble();
    final radians = totalDegrees * math.pi / 180;
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    canvas.translate(outputWidth / 2, outputHeight / 2);
    canvas.rotate(radians);
    canvas.scale(
      flipHorizontal ? -scaleToFill : scaleToFill,
      flipVertical ? -scaleToFill : scaleToFill,
    );
    canvas.translate(-outputWidth / 2, -outputHeight / 2);
    canvas.drawImage(image, ui.Offset.zero, ui.Paint());
    return recorder.endRecording().toImage(image.width, image.height);
  }

  /// 应用局部锚点。径向衰减与页面预览的 ShaderMask 完全一致。
  static Future<ui.Image> applyLocalAdjustments(
    ui.Image image,
    List<ImageEditorLocalRenderSpec> adjustments,
  ) async {
    final width = image.width.toDouble();
    final height = image.height.toDouble();
    final shortSide = math.min(width, height);
    final rect = ui.Rect.fromLTWH(0, 0, width, height);
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    canvas.drawImageRect(image, rect, rect, ui.Paint());
    for (final adjustment in adjustments) {
      final center = ui.Offset(
        adjustment.center.dx.clamp(0.0, 1.0) * width,
        adjustment.center.dy.clamp(0.0, 1.0) * height,
      );
      final radius = (adjustment.radiusOnShortSide * shortSide)
          .clamp(1.0, math.max(width, height))
          .toDouble();
      final mask = ui.Paint()
        ..shader = ui.Gradient.radial(
          center,
          radius,
          <ui.Color>[
            AppColors.white,
            AppColors.white.withValues(alpha: 0.90),
            AppColors.white.withValues(alpha: 0.58),
            AppColors.white.withValues(alpha: 0.22),
            AppColors.transparent,
          ],
          const <double>[0.0, 0.22, 0.56, 0.84, 1.0],
        );
      final adjusted = ui.Paint()
        ..colorFilter = ui.ColorFilter.matrix(adjustment.colorMatrix)
        ..blendMode = ui.BlendMode.srcIn;
      canvas.saveLayer(rect, ui.Paint());
      canvas.drawRect(rect, mask);
      canvas.drawImageRect(image, rect, rect, adjusted);
      canvas.restore();
    }
    return recorder.endRecording().toImage(image.width, image.height);
  }

  /// 应用曲线 LUT（CPU 逐像素，保持 alpha 不变）。
  static Future<ui.Image> applyCurves(
    ui.Image image,
    ImageEditorCurvesState curves,
  ) async {
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    if (data == null) {
      throw StateError('曲线处理无法读取 RGBA 像素');
    }
    final pixels = data.buffer.asUint8List();
    applyCurvesToRgbaPixels(pixels, curves);
    final buffer = await ui.ImmutableBuffer.fromUint8List(pixels);
    final descriptor = ui.ImageDescriptor.raw(
      buffer,
      width: image.width,
      height: image.height,
      pixelFormat: ui.PixelFormat.rgba8888,
    );
    ui.Codec? codec;
    try {
      codec = await descriptor.instantiateCodec();
      final frame = await codec.getNextFrame();
      return frame.image;
    } finally {
      codec?.dispose();
      descriptor.dispose();
      buffer.dispose();
    }
  }

  /// 曲线 LUT 逐像素应用（就地修改 RGBA 数组）。纯函数便于单测。
  static void applyCurvesToRgbaPixels(
    Uint8List pixels,
    ImageEditorCurvesState curves,
  ) {
    final lutR = curves.lutForChannel(ImageEditorCurveChannel.red);
    final lutG = curves.lutForChannel(ImageEditorCurveChannel.green);
    final lutB = curves.lutForChannel(ImageEditorCurveChannel.blue);
    final lutRgb = curves.lutForChannel(ImageEditorCurveChannel.rgb);
    for (var i = 0; i + 3 < pixels.length; i += 4) {
      pixels[i] = lutRgb[lutR[pixels[i]]];
      pixels[i + 1] = lutRgb[lutG[pixels[i + 1]]];
      pixels[i + 2] = lutRgb[lutB[pixels[i + 2]]];
    }
  }

  /// 生成整图马赛克化版本。
  ///
  /// [type] 为像素化时以 [mosaicCellSizeFor] 决定块大小；模糊时使用高斯模糊。
  static Future<ui.Image> buildMosaicizedImage(
    ui.Image image,
    ImageEditorMosaicType type,
  ) async {
    final width = image.width;
    final height = image.height;
    final rect = ui.Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble());
    if (type == ImageEditorMosaicType.blur) {
      final sigma = mosaicBlurSigmaFor(width, height);
      final recorder = ui.PictureRecorder();
      final canvas = ui.Canvas(recorder);
      final paint = ui.Paint()
        ..imageFilter = ui.ImageFilter.blur(
          sigmaX: sigma,
          sigmaY: sigma,
          tileMode: ui.TileMode.clamp,
        );
      canvas.drawImageRect(image, rect, rect, paint);
      return recorder.endRecording().toImage(width, height);
    }
    final cell = mosaicCellSizeFor(width, height);
    final smallWidth = math.max(1, (width / cell).round());
    final smallHeight = math.max(1, (height / cell).round());
    final downRecorder = ui.PictureRecorder();
    final downCanvas = ui.Canvas(downRecorder);
    downCanvas.drawImageRect(
      image,
      rect,
      ui.Rect.fromLTWH(0, 0, smallWidth.toDouble(), smallHeight.toDouble()),
      ui.Paint()..filterQuality = ui.FilterQuality.low,
    );
    final small = await downRecorder.endRecording().toImage(
      smallWidth,
      smallHeight,
    );
    final upRecorder = ui.PictureRecorder();
    final upCanvas = ui.Canvas(upRecorder);
    upCanvas.drawImageRect(
      small,
      ui.Rect.fromLTWH(0, 0, smallWidth.toDouble(), smallHeight.toDouble()),
      rect,
      ui.Paint()..filterQuality = ui.FilterQuality.none,
    );
    small.dispose();
    return upRecorder.endRecording().toImage(width, height);
  }

  /// 马赛克像素块边长（相对短边固定比例，与笔刷大小解耦）。
  static double mosaicCellSizeFor(int width, int height) {
    return math.max(4.0, math.min(width, height) / 44);
  }

  static double mosaicBlurSigmaFor(int width, int height) {
    return math.max(4.0, math.min(width, height) / 72);
  }

  /// 将马赛克笔画合成到原图（导出真相源，与预览 painter 共用 [buildMosaicStrokePath]）。
  static Future<ui.Image> applyMosaicStrokes(
    ui.Image image,
    List<ImageEditorMosaicStroke> strokes,
  ) async {
    if (strokes.isEmpty) {
      return image;
    }
    final width = image.width;
    final height = image.height;
    final rect = ui.Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble());
    final byType = <ImageEditorMosaicType, List<ImageEditorMosaicStroke>>{};
    for (final stroke in strokes) {
      byType.putIfAbsent(stroke.type, () => []).add(stroke);
    }
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    canvas.drawImage(image, ui.Offset.zero, ui.Paint());
    for (final entry in byType.entries) {
      final mosaicked = await buildMosaicizedImage(image, entry.key);
      canvas.saveLayer(rect, ui.Paint());
      final maskPaint = ui.Paint()..color = AppColors.white;
      canvas.drawPath(
        buildMosaicStrokePath(
          entry.value,
          ui.Size(width.toDouble(), height.toDouble()),
        ),
        maskPaint,
      );
      canvas.drawImageRect(
        mosaicked,
        rect,
        rect,
        ui.Paint()..blendMode = ui.BlendMode.srcIn,
      );
      canvas.restore();
      mosaicked.dispose();
    }
    return recorder.endRecording().toImage(width, height);
  }

  /// 笔画 → 填充 Path（预览 painter 与导出共用，保证同一几何）。
  static ui.Path buildMosaicStrokePath(
    List<ImageEditorMosaicStroke> strokes,
    ui.Size targetSize,
  ) {
    final path = ui.Path();
    final shortSide = math.min(targetSize.width, targetSize.height);
    for (final stroke in strokes) {
      final radius = stroke.brushRadiusOnShortSide * shortSide;
      if (stroke.points.isEmpty) {
        continue;
      }
      if (stroke.points.length == 1) {
        final p = stroke.points.first;
        path.addOval(
          ui.Rect.fromCircle(
            center: ui.Offset(
              p.dx * targetSize.width,
              p.dy * targetSize.height,
            ),
            radius: radius,
          ),
        );
        continue;
      }
      final polyline = ui.Path();
      final first = stroke.points.first;
      polyline.moveTo(
        first.dx * targetSize.width,
        first.dy * targetSize.height,
      );
      for (final point in stroke.points.skip(1)) {
        polyline.lineTo(
          point.dx * targetSize.width,
          point.dy * targetSize.height,
        );
      }
      final stroked = ui.Path();
      // Path 无原生 stroke->fill；用逐点圆盘 + 线段矩形近似生成填充区域，
      // 保持预览与导出一致（两端圆头等价 StrokeCap.round）。
      ui.Offset? previous;
      for (final point in stroke.points) {
        final current = ui.Offset(
          point.dx * targetSize.width,
          point.dy * targetSize.height,
        );
        stroked.addOval(ui.Rect.fromCircle(center: current, radius: radius));
        if (previous != null) {
          final delta = current - previous;
          final distance = delta.distance;
          if (distance > 0.01) {
            final normal =
                ui.Offset(-delta.dy / distance, delta.dx / distance) * radius;
            stroked.addPolygon(<ui.Offset>[
              previous + normal,
              current + normal,
              current - normal,
              previous - normal,
            ], true);
          }
        }
        previous = current;
      }
      path.addPath(stroked, ui.Offset.zero);
    }
    return path;
  }

  /// 将文字项合成到原图。字体几何以 [ImageEditorTextItem.fontSizeOnShortSide]
  /// 相对短边换算，与预览 Widget 同参数。
  static Future<ui.Image> applyTextItems(
    ui.Image image,
    List<ImageEditorTextItem> items,
  ) async {
    if (items.isEmpty) {
      return image;
    }
    final width = image.width.toDouble();
    final height = image.height.toDouble();
    final shortSide = math.min(width, height);
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    canvas.drawImage(image, ui.Offset.zero, ui.Paint());
    for (final item in items) {
      final fontSize = item.fontSizeOnShortSide * shortSide;
      final painter = buildTextPainter(item, fontSize, maxWidth: width * 0.9);
      final center = ui.Offset(item.center.dx * width, item.center.dy * height);
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate(item.rotation);
      final topLeft = ui.Offset(-painter.width / 2, -painter.height / 2);
      if (item.style == ImageEditorTextStyleKind.backgroundBar) {
        final padding = fontSize * 0.28;
        final barRect = ui.RRect.fromRectAndRadius(
          ui.Rect.fromLTWH(
            topLeft.dx - padding,
            topLeft.dy - padding * 0.6,
            painter.width + padding * 2,
            painter.height + padding * 1.2,
          ),
          ui.Radius.circular(fontSize * 0.24),
        );
        canvas.drawRRect(barRect, ui.Paint()..color = item.backgroundBarColor);
      }
      if (item.style == ImageEditorTextStyleKind.outline) {
        final outlinePainter = buildTextPainter(
          item,
          fontSize,
          maxWidth: width * 0.9,
          outlinePass: true,
        );
        outlinePainter.paint(canvas, topLeft);
      }
      painter.paint(canvas, topLeft);
      canvas.restore();
    }
    return recorder.endRecording().toImage(image.width, image.height);
  }

  /// 判断路径是否为编辑器烘焙产物（编辑管线临时 PNG）。
  static bool isEditorBakedArtifactPath(String path) {
    final name = path.split('/').last;
    return name.endsWith('.png') &&
        (name.startsWith('crop_') ||
            name.startsWith('rotate_') ||
            name.startsWith('filter_') ||
            name.startsWith('mosaic_') ||
            name.startsWith('text_') ||
            name.startsWith('pro_'));
  }

  /// 预览与导出共用的文字排版（同一字体引擎参数）。
  static TextPainter buildTextPainter(
    ImageEditorTextItem item,
    double fontSize, {
    required double maxWidth,
    bool outlinePass = false,
  }) {
    final style = outlinePass
        ? TextStyle(
            fontSize: fontSize,
            fontWeight: FontWeight.w600,
            foreground: ui.Paint()
              ..style = ui.PaintingStyle.stroke
              ..strokeWidth = fontSize * 0.12
              ..color = item.outlineColor,
          )
        : TextStyle(
            fontSize: fontSize,
            fontWeight: FontWeight.w600,
            color: item.color,
          );
    final painter = TextPainter(
      text: TextSpan(text: item.text, style: style),
      textDirection: TextDirection.ltr,
      textAlign: TextAlign.center,
      maxLines: null,
    );
    painter.layout(maxWidth: maxWidth);
    return painter;
  }
}

/// 局部调整的纯渲染参数；业务锚点在页面边界显式映射为该结构。
class ImageEditorLocalRenderSpec {
  ImageEditorLocalRenderSpec({
    required this.center,
    required this.radiusOnShortSide,
    required this.colorMatrix,
  }) {
    if (colorMatrix.length != 20) {
      throw ArgumentError.value(
        colorMatrix.length,
        'colorMatrix',
        '颜色矩阵必须包含 20 个元素',
      );
    }
  }

  final ui.Offset center;
  final double radiusOnShortSide;
  final List<double> colorMatrix;
}

class _JpegEncodeRequest {
  const _JpegEncodeRequest({
    required this.rgba,
    required this.width,
    required this.height,
    required this.quality,
  });

  final Uint8List rgba;
  final int width;
  final int height;
  final int quality;
}

Uint8List? _encodeJpegInIsolate(_JpegEncodeRequest request) {
  try {
    final image = img.Image.fromBytes(
      width: request.width,
      height: request.height,
      bytes: request.rgba.buffer,
      numChannels: 4,
      order: img.ChannelOrder.rgba,
    );
    return Uint8List.fromList(img.encodeJpg(image, quality: request.quality));
  } catch (_) {
    return null;
  }
}
