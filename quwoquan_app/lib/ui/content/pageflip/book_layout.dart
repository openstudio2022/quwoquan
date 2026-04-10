import 'dart:math' as math;
import 'dart:ui';

import 'package:quwoquan_app/ui/content/pageflip/types.dart';

StPageFlipLayout computeStPageFlipLayout({
  required Size viewportSize,
  required double pageWidth,
  required double pageHeight,
  bool usePortrait = true,
  StPageFlipOrientation? orientationOverride,
}) {
  final safeViewportWidth = math.max(1.0, viewportSize.width).toDouble();
  final safeViewportHeight = math.max(1.0, viewportSize.height).toDouble();
  final middlePoint = Offset(
    safeViewportWidth / 2,
    safeViewportHeight / 2,
  );

  final orientation =
      orientationOverride ??
      (safeViewportWidth < pageWidth * 2 && usePortrait
          ? StPageFlipOrientation.portrait
          : StPageFlipOrientation.landscape);
  final left = orientation == StPageFlipOrientation.portrait
      ? middlePoint.dx - (pageWidth / 2) - pageWidth
      : middlePoint.dx - pageWidth;

  return StPageFlipLayout(
    orientation: orientation,
    bounds: StPageFlipBoundsRect(
      left: left,
      top: middlePoint.dy - (pageHeight / 2),
      width: pageWidth * 2,
      height: pageHeight,
      pageWidth: pageWidth,
    ),
  );
}

Offset convertBookPointToViewport(
  Offset point,
  StPageFlipBoundsRect bounds, {
  StPageFlipDirection? direction,
}) {
  final activeDirection = direction ?? StPageFlipDirection.forward;
  final x = activeDirection == StPageFlipDirection.forward
      ? point.dx + bounds.left + (bounds.width / 2)
      : bounds.width - point.dx + bounds.left;
  return Offset(x, point.dy + bounds.top);
}

Offset convertViewportPointToBook(
  Offset point,
  StPageFlipBoundsRect bounds,
) {
  return Offset(
    point.dx - bounds.left,
    point.dy - bounds.top,
  );
}

Offset convertViewportPointToPage(
  Offset point,
  StPageFlipBoundsRect bounds, {
  required StPageFlipDirection direction,
}) {
  final x = direction == StPageFlipDirection.forward
      ? point.dx - bounds.left - (bounds.width / 2)
      : bounds.width - point.dx + bounds.left;
  return Offset(x, point.dy - bounds.top);
}

StPageFlipRectPoints convertRectPointsToViewport(
  StPageFlipRectPoints rect,
  StPageFlipBoundsRect bounds, {
  required StPageFlipDirection direction,
}) {
  return StPageFlipRectPoints(
    topLeft: convertBookPointToViewport(
      rect.topLeft,
      bounds,
      direction: direction,
    ),
    topRight: convertBookPointToViewport(
      rect.topRight,
      bounds,
      direction: direction,
    ),
    bottomLeft: convertBookPointToViewport(
      rect.bottomLeft,
      bounds,
      direction: direction,
    ),
    bottomRight: convertBookPointToViewport(
      rect.bottomRight,
      bounds,
      direction: direction,
    ),
  );
}

Rect resolveBookPageRect(
  StPageFlipLayout layout, {
  required bool isRightPage,
}) {
  final bounds = layout.bounds;
  final x = isRightPage ? bounds.left + bounds.pageWidth : bounds.left;
  return Rect.fromLTWH(x, bounds.top, bounds.pageWidth, bounds.height);
}
