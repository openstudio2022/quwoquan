import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/components/media/shared/pageflip/media_page_flip_book.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

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
  }) async {
    final front = await _rasterize(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
      semanticSurfaceKind: 'image_book.success.front',
      paint: (canvas, logicalRect) {
        canvas.drawImageRect(
          image,
          coverSourceRect(image, logicalRect.size),
          logicalRect,
          ui.Paint()
            ..isAntiAlias = false
            ..filterQuality = FilterQuality.medium,
        );
      },
    );
    final back = await _rasterize(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
      semanticSurfaceKind: 'image_book.success.back',
      paint: (canvas, logicalRect) {
        _paintMirroredBackImage(canvas, logicalRect, image);
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

  Rect coverSourceRect(ui.Image image, Size pageSize) {
    final sourceWidth = image.width.toDouble();
    final sourceHeight = image.height.toDouble();
    if (sourceWidth <= 0 || sourceHeight <= 0 || pageSize.isEmpty) {
      return Rect.fromLTWH(0, 0, sourceWidth, sourceHeight);
    }
    final sourceAspect = sourceWidth / sourceHeight;
    final targetAspect = pageSize.width / pageSize.height;
    if (sourceAspect > targetAspect) {
      final cropWidth = sourceHeight * targetAspect;
      final left = (sourceWidth - cropWidth) / 2;
      return Rect.fromLTWH(left, 0, cropWidth, sourceHeight);
    }
    final cropHeight = sourceWidth / targetAspect;
    final top = (sourceHeight - cropHeight) / 2;
    return Rect.fromLTWH(0, top, sourceWidth, cropHeight);
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
    canvas.drawRect(logicalRect, ui.Paint()..color = AppColors.worksBackground);
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
    ui.Image image,
  ) {
    canvas.save();
    canvas.translate(logicalRect.width, 0);
    canvas.scale(-1, 1);
    canvas.drawImageRect(
      image,
      coverSourceRect(image, logicalRect.size),
      logicalRect,
      ui.Paint()
        ..isAntiAlias = false
        ..filterQuality = FilterQuality.medium
        ..colorFilter = const ui.ColorFilter.matrix(<double>[
          0.44,
          0.14,
          0.14,
          0,
          0,
          0.14,
          0.44,
          0.14,
          0,
          0,
          0.14,
          0.14,
          0.44,
          0,
          0,
          0,
          0,
          0,
          0.88,
          0,
        ]),
    );
    canvas.restore();
    _paintBackFaceWash(canvas, logicalRect);
  }

  void _paintBackFaceWash(ui.Canvas canvas, Rect logicalRect) {
    canvas.drawRect(
      logicalRect,
      ui.Paint()
        ..color = AppColors.imageBookBackFaceWash.withValues(alpha: 0.08),
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
