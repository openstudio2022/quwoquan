import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/components/media/shared/pageflip/media_page_flip_book.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

enum ImageBookPageSurfaceStatus { loading, success, failure }

/// 将图片书的任意输入统一 rasterize 成固定书页尺寸。
///
/// 翻页几何只消费 page surface，不消费图片自然尺寸；加载失败也必须提供
/// 同尺寸失败页，避免 curl renderer 采样到空纹理或黑底。
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

  Future<MediaPageFlipTexturePair> buildLoadingTexture({
    required Size pageSize,
    required double pixelRatio,
  }) async {
    final front = await _rasterize(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
      semanticSurfaceKind: 'image_book.loading.front',
      paint: (canvas, logicalRect) {
        _paintPlaceholder(
          canvas,
          logicalRect,
          status: ImageBookPageSurfaceStatus.loading,
        );
      },
    );
    final back = await _rasterize(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
      semanticSurfaceKind: 'image_book.loading.back',
      paint: (canvas, logicalRect) {
        _paintPlaceholder(
          canvas,
          logicalRect,
          status: ImageBookPageSurfaceStatus.loading,
          isBackFace: true,
        );
      },
    );
    return MediaPageFlipTexturePair(front: front, back: back);
  }

  Future<MediaPageFlipTexturePair> buildFailureTexture({
    required Size pageSize,
    required double pixelRatio,
  }) async {
    final front = await _rasterize(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
      semanticSurfaceKind: 'image_book.failure.front',
      paint: (canvas, logicalRect) {
        _paintPlaceholder(
          canvas,
          logicalRect,
          status: ImageBookPageSurfaceStatus.failure,
        );
      },
    );
    final back = await _rasterize(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
      semanticSurfaceKind: 'image_book.failure.back',
      paint: (canvas, logicalRect) {
        _paintPlaceholder(
          canvas,
          logicalRect,
          status: ImageBookPageSurfaceStatus.failure,
          isBackFace: true,
        );
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
    _paintChrome(canvas, logicalRect);
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

  void _paintPlaceholder(
    ui.Canvas canvas,
    Rect logicalRect, {
    required ImageBookPageSurfaceStatus status,
    bool isBackFace = false,
  }) {
    final base = status == ImageBookPageSurfaceStatus.failure
        ? const Color(0xFF18202C)
        : const Color(0xFF141B25);
    canvas.drawRect(logicalRect, ui.Paint()..color = base);
    canvas.drawRect(
      logicalRect,
      ui.Paint()
        ..shader = ui.Gradient.linear(
          logicalRect.topLeft,
          logicalRect.bottomRight,
          <Color>[
            AppColors.white.withValues(alpha: 0.09),
            AppColors.transparent,
            AppColors.black.withValues(alpha: 0.18),
          ],
          const <double>[0.0, 0.48, 1.0],
        ),
    );
    if (isBackFace) {
      _paintBackFaceWash(canvas, logicalRect);
    }

    final iconSize = math.min(logicalRect.width, logicalRect.height) * 0.18;
    if (iconSize <= 0) {
      return;
    }
    final center = logicalRect.center;
    final iconRect = Rect.fromCenter(
      center: center,
      width: iconSize,
      height: iconSize * 0.72,
    );
    final strokePaint = ui.Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = math.max(AppSpacing.one, iconSize * 0.035)
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..color = AppColors.white.withValues(
        alpha: status == ImageBookPageSurfaceStatus.failure ? 0.34 : 0.22,
      );
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        iconRect,
        const Radius.circular(AppSpacing.radiusTen),
      ),
      strokePaint,
    );
    canvas.drawCircle(
      Offset(
        iconRect.left + iconRect.width * 0.26,
        iconRect.top + iconRect.height * 0.3,
      ),
      iconSize * 0.055,
      ui.Paint()..color = strokePaint.color,
    );
    final mountainPath = Path()
      ..moveTo(
        iconRect.left + iconRect.width * 0.16,
        iconRect.bottom - iconRect.height * 0.18,
      )
      ..lineTo(
        iconRect.left + iconRect.width * 0.42,
        iconRect.top + iconRect.height * 0.56,
      )
      ..lineTo(
        iconRect.left + iconRect.width * 0.58,
        iconRect.top + iconRect.height * 0.72,
      )
      ..lineTo(
        iconRect.left + iconRect.width * 0.76,
        iconRect.top + iconRect.height * 0.44,
      )
      ..lineTo(
        iconRect.right - iconRect.width * 0.12,
        iconRect.bottom - iconRect.height * 0.18,
      );
    canvas.drawPath(mountainPath, strokePaint);
    if (status == ImageBookPageSurfaceStatus.failure) {
      canvas.drawLine(
        iconRect.topRight +
            Offset(iconRect.width * 0.1, -iconRect.height * 0.12),
        iconRect.bottomLeft -
            Offset(iconRect.width * 0.1, -iconRect.height * 0.12),
        strokePaint,
      );
    }
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
          0.84,
          0,
          0,
          0,
          0,
          0,
          0.84,
          0,
          0,
          0,
          0,
          0,
          0.84,
          0,
          0,
          0,
          0,
          0,
          1,
          0,
        ]),
    );
    canvas.restore();
    _paintBackFaceWash(canvas, logicalRect);
  }

  void _paintBackFaceWash(ui.Canvas canvas, Rect logicalRect) {
    canvas.drawRect(
      logicalRect,
      ui.Paint()..color = const Color(0xFF111821).withValues(alpha: 0.10),
    );
    canvas.drawRect(
      logicalRect,
      ui.Paint()
        ..shader = ui.Gradient.linear(
          logicalRect.centerLeft,
          logicalRect.centerRight,
          <Color>[
            AppColors.black.withValues(alpha: 0.08),
            AppColors.white.withValues(alpha: 0.035),
            AppColors.black.withValues(alpha: 0.06),
          ],
          const <double>[0.0, 0.52, 1.0],
        ),
    );
  }

  void _paintChrome(ui.Canvas canvas, Rect logicalRect) {
    canvas.drawRect(
      logicalRect,
      ui.Paint()
        ..shader = ui.Gradient.linear(
          logicalRect.topCenter,
          logicalRect.bottomCenter,
          <Color>[
            AppColors.black.withValues(alpha: 0.06),
            AppColors.black.withValues(alpha: 0.58),
          ],
        ),
    );
    canvas.drawRect(
      Rect.fromLTWH(
        AppSpacing.zero,
        math.max(AppSpacing.zero, logicalRect.height - AppSpacing.hairline),
        logicalRect.width,
        AppSpacing.hairline,
      ),
      ui.Paint()..color = AppColors.black.withValues(alpha: 0.18),
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
