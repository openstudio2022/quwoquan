import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart' show compute;
import 'package:flutter/painting.dart';
import 'package:vector_math/vector_math_64.dart' show Matrix4, Vector3;
import 'package:image/image.dart' as img;
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_curve_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_mosaic_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_text_models.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';

/// 烘焙未达成：用户显式动作（裁剪 / 旋转 / 滤镜 / 马赛克 / 文字）没有产出可用结果。
///
/// 这类失败必须走错误态并被观测，不得降级成空结果让调用方判空，否则「没做成」
/// 会和「本来就没有」混成同一个 null。
class ImageEditorBakeException implements Exception {
  const ImageEditorBakeException(this.reason);

  final String reason;

  @override
  String toString() => 'ImageEditorBakeException: $reason';
}

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

  /// 编码失败抛出 [ImageEditorBakeException]；不以可空返回值表达失败。
  static Future<Uint8List> encodePng(ui.Image image) async {
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    if (data == null) {
      throw ImageEditorBakeException(
        'png encode returned no pixels (${image.width}x${image.height})',
      );
    }
    return data.buffer.asUint8List();
  }

  /// 提交转码 JPEG 质量（编辑管线内部保持 PNG 无损，提交时一次性压缩）。
  static const int kDeliveryJpegQuality = 92;

  /// 将编辑结果 RGBA 像素编码为交付 JPEG（isolate 内执行，防 UI 卡顿）。
  ///
  /// 编码失败抛出，由调用方决定回退策略；不以可空返回值表达失败。
  static Future<Uint8List> encodeDeliveryJpeg(
    ui.Image image, {
    int quality = kDeliveryJpegQuality,
  }) async {
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    if (data == null) {
      throw ImageEditorBakeException(
        'delivery jpeg encode returned no pixels '
        '(${image.width}x${image.height})',
      );
    }
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

  /// 透视校正（绕中心 3D 旋转投影），预览 Transform 与烘焙共用
  /// [PerspectiveGeometry] 的同一矩阵与填充缩放。
  static Future<ui.Image> applyPerspective(
    ui.Image image, {
    required double horizontalDegrees,
    required double verticalDegrees,
  }) async {
    final width = image.width.toDouble();
    final height = image.height.toDouble();
    final geometry = PerspectiveGeometry(
      width: width,
      height: height,
      horizontalDegrees: horizontalDegrees,
      verticalDegrees: verticalDegrees,
    );
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    canvas.transform(geometry.transformWithFill().storage);
    canvas.drawImage(image, ui.Offset.zero, ui.Paint());
    return recorder.endRecording().toImage(image.width, image.height);
  }

  /// 局部锚点径向衰减的分段渐变（预览 ShaderMask 与 CPU 权重共用真相源）。
  static const List<double> kLocalRadialStops = <double>[
    0.0,
    0.22,
    0.56,
    0.84,
    1.0,
  ];
  static const List<double> kLocalRadialAlphas = <double>[
    1.0,
    0.90,
    0.58,
    0.22,
    0.0,
  ];

  /// CPU 侧径向权重（与 [kLocalRadialStops]/[kLocalRadialAlphas] 分段线性
  /// 插值一致，保证预览 ShaderMask 与烘焙同一衰减曲线）。
  static double localRadialWeight(double normalizedDistance) {
    if (normalizedDistance <= 0) {
      return kLocalRadialAlphas.first;
    }
    if (normalizedDistance >= 1) {
      return 0;
    }
    for (var i = 1; i < kLocalRadialStops.length; i++) {
      if (normalizedDistance <= kLocalRadialStops[i]) {
        final t =
            (normalizedDistance - kLocalRadialStops[i - 1]) /
            (kLocalRadialStops[i] - kLocalRadialStops[i - 1]);
        return kLocalRadialAlphas[i - 1] +
            (kLocalRadialAlphas[i] - kLocalRadialAlphas[i - 1]) * t;
      }
    }
    return 0;
  }

  /// 应用局部锚点（真算法，OPEN-002 关闭）：对每个锚点先在副本上应用
  /// 纯色彩矩阵与细节/分区/颗粒逐像素管线，再按径向权重混合回原图。
  /// 径向衰减与页面预览的 ShaderMask 共用同一分段渐变。
  static Future<ui.Image> applyLocalAdjustments(
    ui.Image image,
    List<ImageEditorLocalRenderSpec> adjustments,
  ) async {
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    if (data == null) {
      throw StateError('局部调节无法读取 RGBA 像素');
    }
    final pixels = data.buffer.asUint8List();
    applyLocalAdjustmentsToRgbaPixels(
      pixels,
      image.width,
      image.height,
      adjustments,
    );
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

  /// 局部锚点逐像素应用（就地修改 RGBA 数组）。纯函数便于单测。
  static void applyLocalAdjustmentsToRgbaPixels(
    Uint8List pixels,
    int width,
    int height,
    List<ImageEditorLocalRenderSpec> adjustments,
  ) {
    if (adjustments.isEmpty || width <= 0 || height <= 0) {
      return;
    }
    final shortSide = math.min(width, height).toDouble();
    for (final adjustment in adjustments) {
      final centerX = adjustment.center.dx.clamp(0.0, 1.0) * width;
      final centerY = adjustment.center.dy.clamp(0.0, 1.0) * height;
      final radius = (adjustment.radiusOnShortSide * shortSide)
          .clamp(1.0, math.max(width, height).toDouble())
          .toDouble();
      // 锚点副本：矩阵 + 细节管线（与整体面板同一像素真相源）。
      final adjusted = Uint8List.fromList(pixels);
      applyColorMatrixToRgbaPixels(adjusted, adjustment.colorMatrix);
      final detail = adjustment.detail;
      if (detail != null && !detail.isIdentity) {
        applyDetailAdjustmentsToRgbaPixels(adjusted, width, height, detail);
      }
      // 只遍历锚点包围盒，按径向权重混合。
      final minX = math.max(0, (centerX - radius).floor());
      final maxX = math.min(width - 1, (centerX + radius).ceil());
      final minY = math.max(0, (centerY - radius).floor());
      final maxY = math.min(height - 1, (centerY + radius).ceil());
      for (var y = minY; y <= maxY; y++) {
        for (var x = minX; x <= maxX; x++) {
          final dx = x - centerX;
          final dy = y - centerY;
          final distance = math.sqrt(dx * dx + dy * dy) / radius;
          final weight = localRadialWeight(distance);
          if (weight <= 0) {
            continue;
          }
          final i = (y * width + x) * 4;
          pixels[i] =
              (pixels[i] + (adjusted[i] - pixels[i]) * weight).round().clamp(
                0,
                255,
              );
          pixels[i + 1] =
              (pixels[i + 1] + (adjusted[i + 1] - pixels[i + 1]) * weight)
                  .round()
                  .clamp(0, 255);
          pixels[i + 2] =
              (pixels[i + 2] + (adjusted[i + 2] - pixels[i + 2]) * weight)
                  .round()
                  .clamp(0, 255);
        }
      }
    }
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

  /// HSL 分色相带调节（CPU 逐像素，保持 alpha 不变）。
  ///
  /// 与「HSL 取平均进全局矩阵」的旧近似不同：每个像素先转 HSL，按其色相
  /// 落入的色相带（含 ±[kHslBandFeatherDegrees] 平滑过渡）与像素饱和度门控
  /// 计算权重，只对目标带像素施加 hue/saturation/luminance 调节。
  static Future<ui.Image> applyHslBands(
    ui.Image image,
    List<ImageEditorHslBandSpec> bands,
  ) async {
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    if (data == null) {
      throw StateError('HSL 处理无法读取 RGBA 像素');
    }
    final pixels = data.buffer.asUint8List();
    applyHslBandsToRgbaPixels(pixels, bands);
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

  /// 4x5 颜色矩阵的 CPU 逐像素版本（预览/烘焙同源组合管线用）。
  static void applyColorMatrixToRgbaPixels(
    Uint8List pixels,
    List<double> matrix,
  ) {
    if (matrix.length != 20) {
      throw ArgumentError.value(matrix.length, 'matrix', '颜色矩阵必须包含 20 个元素');
    }
    for (var i = 0; i + 3 < pixels.length; i += 4) {
      final r = pixels[i].toDouble();
      final g = pixels[i + 1].toDouble();
      final b = pixels[i + 2].toDouble();
      final a = pixels[i + 3].toDouble();
      pixels[i] =
          (matrix[0] * r + matrix[1] * g + matrix[2] * b + matrix[3] * a + matrix[4])
              .round()
              .clamp(0, 255);
      pixels[i + 1] =
          (matrix[5] * r + matrix[6] * g + matrix[7] * b + matrix[8] * a + matrix[9])
              .round()
              .clamp(0, 255);
      pixels[i + 2] =
          (matrix[10] * r +
                  matrix[11] * g +
                  matrix[12] * b +
                  matrix[13] * a +
                  matrix[14])
              .round()
              .clamp(0, 255);
    }
  }

  /// 整体面板的真实像素组合烘焙：纯色彩矩阵 → 分区高光/阴影 → 细节
  /// unsharp（锐化/纹理/结构）→ 颗粒。预览与导出共用同一函数序。
  static Future<ui.Image> applyBaseAdjustments(
    ui.Image image, {
    required List<double> colorMatrix,
    required ImageEditorDetailSpec detail,
  }) async {
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    if (data == null) {
      throw StateError('整体调节无法读取 RGBA 像素');
    }
    final pixels = data.buffer.asUint8List();
    applyColorMatrixToRgbaPixels(pixels, colorMatrix);
    applyDetailAdjustmentsToRgbaPixels(
      pixels,
      image.width,
      image.height,
      detail,
    );
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

  /// 分区高光/阴影 + unsharp 细节（锐化/纹理/结构）+ 颗粒，逐像素就地应用。
  ///
  /// 这是对旧「细节类折算成对比度/亮度矩阵系数」伪装的替换：unsharp 在 luma
  /// 通道做（原图减模糊图增强边缘，不引入色偏），高光/阴影按亮度分区加权，
  /// 颗粒用确定性 hash 噪声（同参数结果可复现，便于测试与预览一致）。
  static void applyDetailAdjustmentsToRgbaPixels(
    Uint8List pixels,
    int width,
    int height,
    ImageEditorDetailSpec detail,
  ) {
    if (width <= 0 || height <= 0 || pixels.length < width * height * 4) {
      return;
    }
    final hasTonal =
        detail.highlights.abs() > 0.001 || detail.shadows.abs() > 0.001;
    final hasSharpen = detail.sharpen.abs() > 0.001;
    final hasTexture = detail.texture.abs() > 0.001;
    final hasStructure = detail.structure.abs() > 0.001;
    final hasVibrance = detail.vibrance.abs() > 0.001;
    final hasDenoise = detail.denoise > 0.001;
    final hasAmbiance = detail.ambiance.abs() > 0.001;
    final hasVignette = detail.vignette.abs() > 0.001;
    final hasGrain = detail.grain > 0.001;
    if (!hasTonal &&
        !hasSharpen &&
        !hasTexture &&
        !hasStructure &&
        !hasVibrance &&
        !hasDenoise &&
        !hasAmbiance &&
        !hasVignette &&
        !hasGrain) {
      return;
    }
    final count = width * height;
    // 降噪最先执行（后续调节不放大噪声），直接改写 pixels。
    if (hasDenoise) {
      _applyDenoiseToRgbaPixels(pixels, width, height, detail.denoise);
    }
    final luma = Float32List(count);
    for (var p = 0, i = 0; p < count; p++, i += 4) {
      luma[p] =
          0.2126 * pixels[i] + 0.7152 * pixels[i + 1] + 0.0722 * pixels[i + 2];
    }
    // 每像素 luma 增益（乘性，保持色相）。
    final gain = Float32List(count)..fillRange(0, count, 1);

    if (hasTonal) {
      for (var p = 0; p < count; p++) {
        final l = luma[p] / 255.0;
        // 高光区权重（亮部）与阴影区权重（暗部），中区平滑衰减。
        final highlightWeight = _smoothstep(0.45, 0.85, l);
        final shadowWeight = 1 - _smoothstep(0.15, 0.55, l);
        var scale = 1.0;
        if (detail.highlights.abs() > 0.001) {
          scale +=
              detail.highlights / 100 * kTonalMaxAdjust * highlightWeight;
        }
        if (detail.shadows.abs() > 0.001) {
          scale += detail.shadows / 100 * kTonalMaxAdjust * shadowWeight;
        }
        gain[p] *= scale.clamp(0.1, 4.0);
      }
    }

    if (hasAmbiance) {
      // 光感：暗部按 (1-l)^2 提亮、亮部按 l^2 微压（保护不削顶），
      // 正值增强暗部细节、负值反向压暗。
      final k = detail.ambiance / 100;
      for (var p = 0; p < count; p++) {
        final l = luma[p] / 255.0;
        final shadowLift = (1 - l) * (1 - l) * kAmbianceShadowLift;
        final highlightCompress = l * l * kAmbianceHighlightCompress;
        final scale = 1.0 + k * (shadowLift - highlightCompress);
        gain[p] *= scale.clamp(0.1, 4.0);
      }
    }

    void addUnsharp(double amount, int radius, double strength) {
      if (amount.abs() <= 0.001 || radius < 1) {
        return;
      }
      final blurred = _boxBlurLuma(luma, width, height, radius);
      final k = amount / 100 * strength;
      for (var p = 0; p < count; p++) {
        final base = luma[p];
        if (base <= 0.5) {
          continue;
        }
        final enhanced = base + k * (base - blurred[p]);
        gain[p] *= (enhanced / base).clamp(0.2, 3.0);
      }
    }

    if (hasSharpen) {
      addUnsharp(detail.sharpen, kSharpenRadiusPx, kSharpenStrength);
    }
    if (hasTexture) {
      addUnsharp(
        detail.texture,
        math.max(2, math.min(width, height) ~/ 150),
        kTextureStrength,
      );
    }
    if (hasStructure) {
      addUnsharp(
        detail.structure,
        math.max(4, math.min(width, height) ~/ 50),
        kStructureStrength,
      );
    }
    if (hasAmbiance) {
      // 光感的局部对比：超大半径 unsharp（低幅度），增强空间光影层次。
      addUnsharp(
        detail.ambiance,
        math.max(8, math.min(width, height) ~/ 24),
        kAmbianceLocalContrast,
      );
    }

    if (hasVignette) {
      // 晕影：从中心向边角的径向亮度衰减/增强，平滑过渡不产生硬边。
      final k = detail.vignette / 100 * kVignetteMaxDarken;
      final centerX = (width - 1) / 2;
      final centerY = (height - 1) / 2;
      final maxDistance = math.sqrt(centerX * centerX + centerY * centerY);
      for (var p = 0; p < count; p++) {
        final x = p % width;
        final y = p ~/ width;
        final dx = x - centerX;
        final dy = y - centerY;
        final distance = math.sqrt(dx * dx + dy * dy) / maxDistance;
        final falloff = _smoothstep(
          kVignetteInnerRadius,
          1.0,
          distance,
        );
        if (falloff <= 0) {
          continue;
        }
        gain[p] *= (1 - k * falloff).clamp(0.1, 4.0);
      }
    }

    final grainAmplitude = detail.grain / 100 * kGrainMaxAmplitude;
    for (var p = 0, i = 0; p < count; p++, i += 4) {
      var scale = gain[p];
      var offset = 0.0;
      if (hasGrain) {
        offset = _hashNoise(p % width, p ~/ width, detail.grainSeed) *
            grainAmplitude;
      }
      if (scale == 1.0 && offset == 0.0) {
        continue;
      }
      pixels[i] = (pixels[i] * scale + offset).round().clamp(0, 255);
      pixels[i + 1] = (pixels[i + 1] * scale + offset).round().clamp(0, 255);
      pixels[i + 2] = (pixels[i + 2] * scale + offset).round().clamp(0, 255);
    }

    if (hasVibrance) {
      _applyVibranceToRgbaPixels(pixels, detail.vibrance);
    }
  }

  /// 滑杆满值对应的自然饱和度最大调整幅度。
  static const double kVibranceMaxScale = 0.7;

  /// 肤色带（橙色系）保护：自然饱和度对该带只施加衰减权重。
  static const double kVibranceSkinProtect = 0.4;

  /// 真 vibrance：逐像素按当前饱和度反比施加增益——低饱和像素提升多、
  /// 已饱和像素受保护不削顶，肤色带（hue 15°–50°）衰减，灰阶不动。
  /// 替换旧「vibrance × 0.65 折算进全局饱和度矩阵」的近似。
  static void _applyVibranceToRgbaPixels(Uint8List pixels, double vibrance) {
    final k = vibrance / 100 * kVibranceMaxScale;
    for (var i = 0; i + 3 < pixels.length; i += 4) {
      final r = pixels[i] / 255.0;
      final g = pixels[i + 1] / 255.0;
      final b = pixels[i + 2] / 255.0;
      final maxC = math.max(r, math.max(g, b));
      final minC = math.min(r, math.min(g, b));
      final delta = maxC - minC;
      if (delta < 1e-6) {
        continue;
      }
      final lightness = (maxC + minC) / 2;
      if (lightness <= 0 || lightness >= 1) {
        continue;
      }
      final saturation = delta / (1 - (2 * lightness - 1).abs());
      double hue;
      if (maxC == r) {
        hue = 60 * (((g - b) / delta) % 6);
      } else if (maxC == g) {
        hue = 60 * (((b - r) / delta) + 2);
      } else {
        hue = 60 * (((r - g) / delta) + 4);
      }
      if (hue < 0) hue += 360;
      final skinWeight = (hue >= 15 && hue <= 50)
          ? kVibranceSkinProtect
          : 1.0;
      // 增益随已饱和程度衰减：s→1 时增益→0（不削顶），s→0 时不动灰阶。
      final gain = k * (1 - saturation) * skinWeight;
      final nextSaturation = (saturation + gain * saturation).clamp(0.0, 1.0);
      if ((nextSaturation - saturation).abs() < 1e-6) {
        continue;
      }
      final c = (1 - (2 * lightness - 1).abs()) * nextSaturation;
      final x = c * (1 - ((hue / 60) % 2 - 1).abs());
      final m = lightness - c / 2;
      double r1, g1, b1;
      if (hue < 60) {
        r1 = c;
        g1 = x;
        b1 = 0;
      } else if (hue < 120) {
        r1 = x;
        g1 = c;
        b1 = 0;
      } else if (hue < 180) {
        r1 = 0;
        g1 = c;
        b1 = x;
      } else if (hue < 240) {
        r1 = 0;
        g1 = x;
        b1 = c;
      } else if (hue < 300) {
        r1 = x;
        g1 = 0;
        b1 = c;
      } else {
        r1 = c;
        g1 = 0;
        b1 = x;
      }
      pixels[i] = ((r1 + m) * 255).round().clamp(0, 255);
      pixels[i + 1] = ((g1 + m) * 255).round().clamp(0, 255);
      pixels[i + 2] = ((b1 + m) * 255).round().clamp(0, 255);
    }
  }

  /// 降噪半径与保边阈值。
  static const int kDenoiseRadiusPx = 2;
  static const double kDenoiseMaxMix = 0.85;
  static const double kDenoiseEdgeLow = 4.0;
  static const double kDenoiseEdgeHigh = 26.0;

  /// 保边降噪：亮度边缘引导的选择性平滑——平坦区向模糊值收敛（去噪），
  /// 边缘区权重衰减保留细节；对 RGB 三通道用同一边缘权重（同时抑制色噪）。
  static void _applyDenoiseToRgbaPixels(
    Uint8List pixels,
    int width,
    int height,
    double denoise,
  ) {
    final count = width * height;
    final amount = (denoise / 100).clamp(0.0, 1.0) * kDenoiseMaxMix;
    final luma = Float32List(count);
    for (var p = 0, i = 0; p < count; p++, i += 4) {
      luma[p] =
          0.2126 * pixels[i] + 0.7152 * pixels[i + 1] + 0.0722 * pixels[i + 2];
    }
    final blurLuma = _boxBlurLuma(luma, width, height, kDenoiseRadiusPx);
    // 逐通道复用同一缓冲做模糊，控制内存峰值。
    final channel = Float32List(count);
    for (var c = 0; c < 3; c++) {
      for (var p = 0, i = c; p < count; p++, i += 4) {
        channel[p] = pixels[i].toDouble();
      }
      final blurred = _boxBlurLuma(channel, width, height, kDenoiseRadiusPx);
      for (var p = 0, i = c; p < count; p++, i += 4) {
        final edge = (luma[p] - blurLuma[p]).abs();
        // 边缘权重：平坦区 1 → 边缘 0（smoothstep 反向）。
        final t = ((edge - kDenoiseEdgeLow) /
                (kDenoiseEdgeHigh - kDenoiseEdgeLow))
            .clamp(0.0, 1.0);
        final edgeWeight = 1 - t * t * (3 - 2 * t);
        final mix = amount * edgeWeight;
        if (mix <= 0) {
          continue;
        }
        pixels[i] = (channel[p] + (blurred[p] - channel[p]) * mix)
            .round()
            .clamp(0, 255);
      }
    }
  }

  /// 滑杆满值对应的分区亮度最大调整幅度。
  static const double kTonalMaxAdjust = 0.35;

  /// 光感（ambiance）满值的暗部提亮与亮部压制幅度、局部对比强度。
  /// 亮部压制系数远小于暗部提亮：乘性 gain 对亮像素绝对变化放大，
  /// 语义主体是「暗部细节提亮」。
  static const double kAmbianceShadowLift = 0.45;
  static const double kAmbianceHighlightCompress = 0.08;
  static const double kAmbianceLocalContrast = 0.35;

  /// 晕影满值的边角最大压暗比例与内圈无衰减半径（归一化距离）。
  static const double kVignetteMaxDarken = 0.55;
  static const double kVignetteInnerRadius = 0.35;

  /// 由「应为中性灰」的采样色反解白平衡（温度/色调滑杆值 -100..100）。
  ///
  /// 与 `_temperatureMatrix`（R/B ±0.18）、`_tintMatrix`（G ∓0.12）的正向
  /// 定义互逆：吸管点选与灰世界自动共用同一反解，预览/烘焙同源。
  static ({double temperature, double tint}) resolveWhiteBalanceFromNeutralSample({
    required double red,
    required double green,
    required double blue,
  }) {
    final safeRed = math.max(red, 1.0);
    final safeGreen = math.max(green, 1.0);
    final temperature = (((safeGreen / safeRed) - 1) / 0.18 * 100).clamp(
      -100.0,
      100.0,
    );
    final tint = (((red + blue) / 2 / safeGreen - 1) / 0.12 * 100).clamp(
      -100.0,
      100.0,
    );
    return (temperature: temperature.toDouble(), tint: tint.toDouble());
  }

  /// 锐化 unsharp 半径（细边缘）与强度。
  static const int kSharpenRadiusPx = 1;
  static const double kSharpenStrength = 1.2;

  /// 纹理（中频细节）与结构（局部对比）强度。
  static const double kTextureStrength = 0.8;
  static const double kStructureStrength = 0.6;

  /// 颗粒满值振幅（8bit 亮度单位）。
  static const double kGrainMaxAmplitude = 24.0;

  /// 分离 box blur（水平+垂直各一遍），O(n) 滑动窗口。
  static Float32List _boxBlurLuma(
    Float32List source,
    int width,
    int height,
    int radius,
  ) {
    final horizontal = Float32List(source.length);
    final window = 2 * radius + 1;
    for (var y = 0; y < height; y++) {
      final row = y * width;
      var sum = 0.0;
      for (var x = -radius; x <= radius; x++) {
        sum += source[row + x.clamp(0, width - 1)];
      }
      for (var x = 0; x < width; x++) {
        horizontal[row + x] = sum / window;
        final outgoing = (x - radius).clamp(0, width - 1);
        final incoming = (x + radius + 1).clamp(0, width - 1);
        sum += source[row + incoming] - source[row + outgoing];
      }
    }
    final result = Float32List(source.length);
    for (var x = 0; x < width; x++) {
      var sum = 0.0;
      for (var y = -radius; y <= radius; y++) {
        sum += horizontal[y.clamp(0, height - 1) * width + x];
      }
      for (var y = 0; y < height; y++) {
        result[y * width + x] = sum / window;
        final outgoing = (y - radius).clamp(0, height - 1);
        final incoming = (y + radius + 1).clamp(0, height - 1);
        sum += horizontal[incoming * width + x] -
            horizontal[outgoing * width + x];
      }
    }
    return result;
  }

  /// 确定性 hash 噪声（[-1, 1]）：同 (x, y, seed) 恒等，预览/烘焙/测试一致。
  static double _hashNoise(int x, int y, int seed) {
    var h = x * 374761393 + y * 668265263 + seed * 2147483647;
    h = (h ^ (h >> 13)) * 1274126177;
    h = h ^ (h >> 16);
    return ((h & 0xFFFF) / 0xFFFF) * 2 - 1;
  }

  /// 色相带边界平滑过渡宽度（度）。
  static const double kHslBandFeatherDegrees = 10.0;

  /// 滑杆满值（±100）对应的最大色相偏移（度）。
  static const double kHslMaxHueShiftDegrees = 30.0;

  /// 滑杆满值对应的最大饱和度乘性调整幅度。
  static const double kHslMaxSaturationScale = 0.6;

  /// 滑杆满值对应的最大明度调整幅度（按剩余余量比例施加，避免削顶）。
  static const double kHslMaxLuminanceShift = 0.3;

  /// HSL 分带逐像素应用（就地修改 RGBA 数组）。纯函数便于单测。
  static void applyHslBandsToRgbaPixels(
    Uint8List pixels,
    List<ImageEditorHslBandSpec> bands,
  ) {
    final active = bands
        .where(
          (band) =>
              band.hueShift.abs() > 0.001 ||
              band.saturation.abs() > 0.001 ||
              band.luminance.abs() > 0.001,
        )
        .toList(growable: false);
    if (active.isEmpty) {
      return;
    }
    for (var i = 0; i + 3 < pixels.length; i += 4) {
      final r = pixels[i] / 255.0;
      final g = pixels[i + 1] / 255.0;
      final b = pixels[i + 2] / 255.0;
      final maxC = math.max(r, math.max(g, b));
      final minC = math.min(r, math.min(g, b));
      final delta = maxC - minC;
      final lightness = (maxC + minC) / 2;
      if (delta < 1e-6) {
        // 无色相的灰阶像素不参与分带调节。
        continue;
      }
      final saturation = lightness >= 1 || lightness <= 0
          ? 0.0
          : delta / (1 - (2 * lightness - 1).abs());
      double hue;
      if (maxC == r) {
        hue = 60 * (((g - b) / delta) % 6);
      } else if (maxC == g) {
        hue = 60 * (((b - r) / delta) + 2);
      } else {
        hue = 60 * (((r - g) / delta) + 4);
      }
      if (hue < 0) hue += 360;

      // 灰度门控：低饱和像素没有可信色相，权重随饱和度平滑升起。
      final saturationGate = _smoothstep(0.04, 0.16, saturation);
      if (saturationGate <= 0) {
        continue;
      }
      var hueDelta = 0.0;
      var saturationScale = 1.0;
      var luminanceAmount = 0.0;
      var touched = false;
      for (final band in active) {
        final weight = band.weightForHue(hue) * saturationGate;
        if (weight <= 0) {
          continue;
        }
        touched = true;
        hueDelta += weight * band.hueShift / 100 * kHslMaxHueShiftDegrees;
        saturationScale *=
            1 + weight * band.saturation / 100 * kHslMaxSaturationScale;
        luminanceAmount += weight * band.luminance / 100 * kHslMaxLuminanceShift;
      }
      if (!touched) {
        continue;
      }
      var nextHue = (hue + hueDelta) % 360;
      if (nextHue < 0) nextHue += 360;
      final nextSaturation = (saturation * saturationScale).clamp(0.0, 1.0);
      // 明度按剩余余量施加：调亮以 (1-l) 为界、调暗以 l 为界，避免削顶。
      final nextLightness = luminanceAmount >= 0
          ? (lightness + luminanceAmount * (1 - lightness)).clamp(0.0, 1.0)
          : (lightness + luminanceAmount * lightness).clamp(0.0, 1.0);

      // HSL → RGB。
      final c = (1 - (2 * nextLightness - 1).abs()) * nextSaturation;
      final x = c * (1 - ((nextHue / 60) % 2 - 1).abs());
      final m = nextLightness - c / 2;
      double r1, g1, b1;
      if (nextHue < 60) {
        r1 = c;
        g1 = x;
        b1 = 0;
      } else if (nextHue < 120) {
        r1 = x;
        g1 = c;
        b1 = 0;
      } else if (nextHue < 180) {
        r1 = 0;
        g1 = c;
        b1 = x;
      } else if (nextHue < 240) {
        r1 = 0;
        g1 = x;
        b1 = c;
      } else if (nextHue < 300) {
        r1 = x;
        g1 = 0;
        b1 = c;
      } else {
        r1 = c;
        g1 = 0;
        b1 = x;
      }
      pixels[i] = ((r1 + m) * 255).round().clamp(0, 255);
      pixels[i + 1] = ((g1 + m) * 255).round().clamp(0, 255);
      pixels[i + 2] = ((b1 + m) * 255).round().clamp(0, 255);
    }
  }

  static double _smoothstep(double edge0, double edge1, double value) {
    final t = ((value - edge0) / (edge1 - edge0)).clamp(0.0, 1.0);
    return t * t * (3 - 2 * t);
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

/// 透视校正几何真相源：预览 Transform 与导出烘焙必须共用同一矩阵构造与
/// 填充缩放，禁止第二坐标链（对齐 RotateGeometry 纪律）。
class PerspectiveGeometry {
  PerspectiveGeometry({
    required this.width,
    required this.height,
    required this.horizontalDegrees,
    required this.verticalDegrees,
  });

  /// 透视轴滑杆上限（度）。
  static const double kMaxDegrees = 30.0;

  /// 透视深度系数（相对短边的观察距离倒数）。
  static const double kPerspectiveDepth = 0.0012;

  final double width;
  final double height;
  final double horizontalDegrees;
  final double verticalDegrees;

  bool get isIdentity =>
      horizontalDegrees.abs() <= 0.001 && verticalDegrees.abs() <= 0.001;

  /// 绕原点的透视旋转核（未含平移与填充缩放）。
  Matrix4 _centeredCore() {
    final shortSide = math.min(width, height);
    final hRad =
        horizontalDegrees.clamp(-kMaxDegrees, kMaxDegrees) * math.pi / 180;
    final vRad =
        verticalDegrees.clamp(-kMaxDegrees, kMaxDegrees) * math.pi / 180;
    final perspective = Matrix4.identity()
      ..setEntry(3, 2, -kPerspectiveDepth / shortSide * 1000);
    return perspective *
        (Matrix4.identity()..rotateY(hRad)) *
        (Matrix4.identity()..rotateX(vRad));
  }

  /// 绕中心的 3D 透视矩阵（未含填充缩放）。
  Matrix4 baseTransform() {
    return Matrix4.translationValues(width / 2, height / 2, 0) *
        _centeredCore() *
        Matrix4.translationValues(-width / 2, -height / 2, 0);
  }

  /// 变换后仍完整覆盖原范围框所需的填充缩放（二分内接测试）。
  double scaleToFill() {
    if (isIdentity) {
      return 1;
    }
    final transform = baseTransform();
    ui.Offset project(double x, double y) {
      final v = transform.transform3(Vector3(x, y, 0));
      final w =
          transform.storage[3] * x +
          transform.storage[7] * y +
          transform.storage[15];
      if (w.abs() < 1e-9) {
        return ui.Offset(v.x, v.y);
      }
      return ui.Offset(v.x / w, v.y / w);
    }

    final quad = <ui.Offset>[
      project(0, 0),
      project(width, 0),
      project(width, height),
      project(0, height),
    ];
    bool rectInsideQuad(double shrink) {
      final cx = width / 2;
      final cy = height / 2;
      final halfW = width / 2 * shrink;
      final halfH = height / 2 * shrink;
      final corners = <ui.Offset>[
        ui.Offset(cx - halfW, cy - halfH),
        ui.Offset(cx + halfW, cy - halfH),
        ui.Offset(cx + halfW, cy + halfH),
        ui.Offset(cx - halfW, cy + halfH),
      ];
      for (final point in corners) {
        // 凸四边形内含测试：点必须在每条边的同侧。
        for (var i = 0; i < 4; i++) {
          final a = quad[i];
          final b = quad[(i + 1) % 4];
          final cross =
              (b.dx - a.dx) * (point.dy - a.dy) -
              (b.dy - a.dy) * (point.dx - a.dx);
          if (cross < 0) {
            return false;
          }
        }
      }
      return true;
    }

    var low = 0.2;
    var high = 1.0;
    if (rectInsideQuad(1)) {
      return 1;
    }
    for (var iteration = 0; iteration < 24; iteration++) {
      final mid = (low + high) / 2;
      if (rectInsideQuad(mid)) {
        low = mid;
      } else {
        high = mid;
      }
    }
    return (1 / low).clamp(1.0, 3.0);
  }

  /// 绕原点的最终变换核（填充缩放 × 透视旋转），供 Flutter `Transform`
  /// 配合 `alignment: Alignment.center` 消费（与烘焙同一核）。
  Matrix4 centeredTransformWithFill() {
    final fill = scaleToFill();
    return Matrix4.diagonal3Values(fill, fill, 1) * _centeredCore();
  }

  /// 预览与烘焙共用的最终矩阵：绕中心缩放填充 × 透视。
  Matrix4 transformWithFill() {
    return Matrix4.translationValues(width / 2, height / 2, 0) *
        centeredTransformWithFill() *
        Matrix4.translationValues(-width / 2, -height / 2, 0);
  }

  /// 变换后角点（含透视除法与填充缩放），供测试断言位移方向。
  List<ui.Offset> projectedCorners() {
    final transform = transformWithFill();
    ui.Offset project(double x, double y) {
      final v = transform.transform3(Vector3(x, y, 0));
      final w =
          transform.storage[3] * x +
          transform.storage[7] * y +
          transform.storage[15];
      if (w.abs() < 1e-9) {
        return ui.Offset(v.x, v.y);
      }
      return ui.Offset(v.x / w, v.y / w);
    }

    return <ui.Offset>[
      project(0, 0),
      project(width, 0),
      project(width, height),
      project(0, height),
    ];
  }
}

/// 整体面板细节/分区/颗粒的纯渲染参数（值域 -100..100，grain/denoise 0..100）。
class ImageEditorDetailSpec {
  const ImageEditorDetailSpec({
    this.sharpen = 0,
    this.texture = 0,
    this.structure = 0,
    this.highlights = 0,
    this.shadows = 0,
    this.vibrance = 0,
    this.denoise = 0,
    this.ambiance = 0,
    this.vignette = 0,
    this.grain = 0,
    this.grainSeed = 1,
  });

  final double sharpen;
  final double texture;
  final double structure;
  final double highlights;
  final double shadows;

  /// 自然饱和度：低饱和像素增益大、已饱和像素受保护、肤色带衰减。
  final double vibrance;

  /// 降噪：亮度边缘引导的保边平滑（0..100）。
  final double denoise;

  /// 光感（ambiance）：暗部提亮 + 亮部微压 + 大半径局部对比；
  /// 替换旧「lightSense × 亮度/对比矩阵系数」近似。
  final double ambiance;

  /// 晕影：正值边角压暗（暗角）、负值边角提亮（亮角），径向平滑过渡。
  final double vignette;
  final double grain;
  final int grainSeed;

  bool get isIdentity =>
      sharpen.abs() <= 0.001 &&
      texture.abs() <= 0.001 &&
      structure.abs() <= 0.001 &&
      highlights.abs() <= 0.001 &&
      shadows.abs() <= 0.001 &&
      vibrance.abs() <= 0.001 &&
      denoise <= 0.001 &&
      ambiance.abs() <= 0.001 &&
      vignette.abs() <= 0.001 &&
      grain <= 0.001;
}

/// HSL 分带调节的纯渲染参数；页面边界把 8 通道 UI 值显式映射为该结构。
///
/// [hueMin]/[hueMax] 是色相带区间（度，支持跨 0 环绕）；三个调节值域 -100..100。
class ImageEditorHslBandSpec {
  const ImageEditorHslBandSpec({
    required this.hueMin,
    required this.hueMax,
    this.hueShift = 0,
    this.saturation = 0,
    this.luminance = 0,
  });

  final double hueMin;
  final double hueMax;
  final double hueShift;
  final double saturation;
  final double luminance;

  /// 像素色相在带内的权重：核心区 1，带边界 ±feather 平滑过渡到 0。
  double weightForHue(double hue) {
    const feather = ImageEditorExportEngine.kHslBandFeatherDegrees;
    final normalized = ((hue % 360) + 360) % 360;
    final start = ((hueMin % 360) + 360) % 360;
    final end = ((hueMax % 360) + 360) % 360;
    final width = end >= start ? end - start : 360 - start + end;
    // 相对带起点的环形偏移，统一映射到 [-(360-width), width) 后按
    // [-feather, width+feather] 判定带内（含过渡区）。
    var offset = normalized - start;
    if (offset < 0) offset += 360;
    if (offset > 360 - feather) offset -= 360;
    if (offset < -feather || offset > width + feather) {
      return 0;
    }
    final edgeIn = ((offset + feather) / (2 * feather)).clamp(0.0, 1.0);
    final edgeOut = (((width + feather) - offset) / (2 * feather)).clamp(
      0.0,
      1.0,
    );
    return math.min(edgeIn, edgeOut);
  }
}

/// 局部调整的纯渲染参数；业务锚点在页面边界显式映射为该结构。
class ImageEditorLocalRenderSpec {
  ImageEditorLocalRenderSpec({
    required this.center,
    required this.radiusOnShortSide,
    required this.colorMatrix,
    this.detail,
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

  /// 细节/分区/颗粒类参数（锐化/纹理/结构/高光/阴影/vibrance/降噪/颗粒）
  /// 走与整体面板同一逐像素管线；null 表示该锚点无细节类调节。
  final ImageEditorDetailSpec? detail;
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

Uint8List _encodeJpegInIsolate(_JpegEncodeRequest request) {
  final image = img.Image.fromBytes(
    width: request.width,
    height: request.height,
    bytes: request.rgba.buffer,
    numChannels: 4,
    order: img.ChannelOrder.rgba,
  );
  return Uint8List.fromList(img.encodeJpg(image, quality: request.quality));
}
