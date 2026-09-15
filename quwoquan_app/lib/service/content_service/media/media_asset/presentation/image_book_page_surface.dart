import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_viewer_layout.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_page_flip_book.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

/// 将图片书的任意输入统一 rasterize 成固定书页尺寸。
///
/// 翻页几何只消费固定尺寸的 page surface，不消费图片自然尺寸；
/// pending/failed 统一 rasterize 为无状态图标的中性纸面。
class ImageBookPageSurfaceFactory {
  const ImageBookPageSurfaceFactory();

  Future<MediaPageFlipTexturePair> rasterizeImageTexture({
    required ui.Image image,
    required Size pageSize,
    required double pixelRatio,
    double? canonicalAspectRatio,
    double mediaTopInset = 0,
    double mediaBottomInset = 0,
    double landscapeEntryExtent = 0,
    bool usePortraitBands = false,
  }) async {
    final geometry = geometryForImage(
      image,
      _safePageSize(pageSize),
      canonicalAspectRatio: canonicalAspectRatio,
      mediaTopInset: mediaTopInset,
      mediaBottomInset: mediaBottomInset,
      landscapeEntryExtent: landscapeEntryExtent,
      usePortraitBands: usePortraitBands,
    );
    final front = await _rasterize(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
      semanticSurfaceKind: 'image_book.success.front',
      paint: (canvas, logicalRect) {
        paintImage(canvas, image, geometry);
      },
    );
    final back = await _rasterize(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
      semanticSurfaceKind: 'image_book.success.back',
      paint: (canvas, logicalRect) {
        _paintMirroredBackImage(canvas, logicalRect, image, geometry: geometry);
      },
    );
    return MediaPageFlipTexturePair(front: front, back: back);
  }

  Future<MediaPageFlipTexturePair> buildNeutralTexture({
    required Size pageSize,
    required double pixelRatio,
  }) async {
    final front = await _rasterize(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
      semanticSurfaceKind: 'image_book.neutral.front',
      paint: (canvas, logicalRect) {
        _paintNeutralPaper(canvas, logicalRect, isBackFace: false);
      },
    );
    final back = await _rasterize(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
      semanticSurfaceKind: 'image_book.neutral.back',
      paint: (canvas, logicalRect) {
        _paintNeutralPaper(canvas, logicalRect, isBackFace: true);
      },
    );
    return MediaPageFlipTexturePair(front: front, back: back);
  }

  Rect containDestinationRect(
    ui.Image image,
    Size pageSize, {
    double? canonicalAspectRatio,
  }) => geometryForImage(
    image,
    pageSize,
    canonicalAspectRatio: canonicalAspectRatio,
  ).contentRect;

  ImmersiveMediaGeometry geometryForImage(
    ui.Image image,
    Size pageSize, {
    double? canonicalAspectRatio,
    double mediaTopInset = 0,
    double mediaBottomInset = 0,
    double landscapeEntryExtent = 0,
    bool usePortraitBands = false,
  }) {
    final ratio =
        canonicalAspectRatio != null &&
            canonicalAspectRatio.isFinite &&
            canonicalAspectRatio > 0
        ? canonicalAspectRatio
        : image.width / image.height;
    return ImmersiveMediaGeometry(
      size: pageSize,
      aspectRatio: ratio,
      topInset: mediaTopInset,
      bottomInset: mediaBottomInset,
      entryExtent: landscapeEntryExtent,
      fullscreen: !usePortraitBands,
    );
  }

  /// 静态页与 front texture 共用同一绘制入口；back 仅增加镜像和材质滤镜。
  void paintImage(
    ui.Canvas canvas,
    ui.Image image,
    ImmersiveMediaGeometry geometry, {
    ui.ColorFilter? colorFilter,
  }) {
    canvas.save();
    canvas.clipRect(geometry.viewportRect);
    canvas.drawImageRect(
      image,
      Rect.fromLTWH(0, 0, image.width.toDouble(), image.height.toDouble()),
      geometry.contentRect,
      ui.Paint()
        ..isAntiAlias = false
        ..filterQuality = FilterQuality.medium
        ..colorFilter = colorFilter,
    );
    canvas.restore();
  }

  Future<MediaPageFlipTextureSnapshot> _rasterize({
    required Size pageSize,
    required double pixelRatio,
    required String semanticSurfaceKind,
    required void Function(ui.Canvas canvas, Rect logicalRect) paint,
  }) async {
    final safeSize = _safePageSize(pageSize);
    final safePixelRatio = _safePixelRatio(pixelRatio);
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    final logicalRect = Offset.zero & safeSize;
    canvas.scale(safePixelRatio, safePixelRatio);
    canvas.drawRect(logicalRect, ui.Paint()..color = AppColors.black);
    paint(canvas, logicalRect);
    final picture = recorder.endRecording();
    final raster = await picture.toImage(
      math.max(1, (safeSize.width * safePixelRatio).round()),
      math.max(1, (safeSize.height * safePixelRatio).round()),
    );
    picture.dispose();
    return createMediaPageFlipTextureSnapshot(
      image: raster,
      logicalSize: safeSize,
      pixelRatio: safePixelRatio,
      semanticSurfaceKind: semanticSurfaceKind,
    );
  }

  void _paintNeutralPaper(
    ui.Canvas canvas,
    Rect logicalRect, {
    required bool isBackFace,
  }) {
    canvas.drawRect(
      logicalRect,
      ui.Paint()
        ..color = isBackFace
            ? AppColors.imageBookBackFaceWash
            : AppColors.imageBookPlaceholderBackdrop,
    );
    canvas.drawRect(
      logicalRect,
      ui.Paint()
        ..shader = ui.Gradient.linear(
          logicalRect.topLeft,
          logicalRect.bottomRight,
          <Color>[
            AppColors.white.withValues(alpha: isBackFace ? 0.025 : 0.04),
            AppColors.transparent,
            AppColors.black.withValues(alpha: isBackFace ? 0.07 : 0.035),
          ],
          const <double>[0.0, 0.55, 1.0],
        ),
    );
  }

  void _paintMirroredBackImage(
    ui.Canvas canvas,
    Rect logicalRect,
    ui.Image image, {
    required ImmersiveMediaGeometry geometry,
  }) {
    canvas.save();
    // 洗色和纸张渐变只覆盖媒体本身，不染亮 contain/裁剪窗口外的黑边。
    canvas.clipRect(geometry.viewportRect.intersect(geometry.contentRect));
    canvas.translate(logicalRect.width, 0);
    canvas.scale(-1, 1);
    paintImage(
      canvas,
      image,
      geometry,
      colorFilter: const ui.ColorFilter.matrix(<double>[
        0.46,
        0.24,
        0.24,
        0,
        0,
        0.24,
        0.46,
        0.24,
        0,
        0,
        0.24,
        0.24,
        0.46,
        0,
        0,
        0,
        0,
        0,
        0.88,
        0,
      ]),
    );
    _paintBackFaceWash(canvas, logicalRect);
    canvas.restore();
  }

  void _paintBackFaceWash(ui.Canvas canvas, Rect logicalRect) {
    canvas.drawRect(
      logicalRect,
      ui.Paint()
        ..color = AppColors.imageBookBackFaceWash.withValues(alpha: 0.28),
    );
    canvas.drawRect(
      logicalRect,
      ui.Paint()
        ..shader = ui.Gradient.linear(
          logicalRect.centerLeft,
          logicalRect.centerRight,
          <Color>[
            AppColors.black.withValues(alpha: 0.055),
            AppColors.white.withValues(alpha: 0.032),
            AppColors.black.withValues(alpha: 0.05),
          ],
          const <double>[0.0, 0.52, 1.0],
        ),
    );
  }

  Size _safePageSize(Size pageSize) {
    final width = pageSize.width.isFinite && pageSize.width > 0
        ? pageSize.width
        : AppSpacing.one;
    final height = pageSize.height.isFinite && pageSize.height > 0
        ? pageSize.height
        : AppSpacing.one;
    return Size(width, height);
  }

  double _safePixelRatio(double pixelRatio) {
    return pixelRatio.isFinite && pixelRatio > 0 ? pixelRatio : 1.0;
  }
}
