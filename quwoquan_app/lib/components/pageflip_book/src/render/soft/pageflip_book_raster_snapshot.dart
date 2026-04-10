import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

@immutable
class PageflipBookRasterSnapshot {
  const PageflipBookRasterSnapshot({
    required this.image,
    required this.logicalSize,
  });

  final ui.Image image;
  final Size logicalSize;

  Rect sourceRectForLogicalSlice({
    required double left,
    required double width,
  }) {
    final safeWidth = logicalSize.width <= 0 ? 1.0 : logicalSize.width;
    final safeHeight = logicalSize.height <= 0 ? 1.0 : logicalSize.height;
    final clampedLeft = left.clamp(0.0, safeWidth).toDouble();
    final clampedWidth = width
        .clamp(0.0, (safeWidth - clampedLeft).clamp(0.0, safeWidth))
        .toDouble();
    final pixelWidthPerLogical = image.width / safeWidth;
    final pixelHeightPerLogical = image.height / safeHeight;
    return Rect.fromLTWH(
      clampedLeft * pixelWidthPerLogical,
      0,
      clampedWidth * pixelWidthPerLogical,
      image.height * pixelHeightPerLogical / pixelHeightPerLogical,
    );
  }
}

@immutable
class PageflipBookSingleBackwardRasterBundle {
  const PageflipBookSingleBackwardRasterBundle({
    required this.coveredCurrent,
    required this.turningFront,
    required this.turningBack,
  });

  final PageflipBookRasterSnapshot coveredCurrent;
  final PageflipBookRasterSnapshot turningFront;
  final PageflipBookRasterSnapshot turningBack;
}
