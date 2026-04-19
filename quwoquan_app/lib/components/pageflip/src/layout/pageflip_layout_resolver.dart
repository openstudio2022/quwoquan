import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_mode.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart' as canonical_layout;
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class PageflipLayout {
  const PageflipLayout({
    required this.mode,
    required this.orientation,
    required this.bounds,
  });

  final PageflipMode mode;
  final StPageFlipOrientation orientation;
  final StPageFlipBoundsRect bounds;

  Rect resolvePageRect({required bool isRightPage}) {
    return canonical_layout.resolveBookPageRect(
      StPageFlipLayout(orientation: orientation, bounds: bounds),
      isRightPage: isRightPage,
    );
  }

  Offset convertViewportPointToPage(
    Offset point, {
    required StPageFlipDirection direction,
  }) {
    return canonical_layout.convertViewportPointToPage(
      point,
      bounds,
      direction: direction,
    );
  }
}

@immutable
class PageflipLayoutResolver {
  const PageflipLayoutResolver({
    this.usePortrait = true,
    this.orientationOverride,
  });

  final bool usePortrait;
  final StPageFlipOrientation? orientationOverride;

  PageflipLayout resolve({
    required Size viewportSize,
    required double pageWidth,
    required double pageHeight,
    required PageflipMode mode,
  }) {
    final layout = canonical_layout.computeStPageFlipLayout(
      viewportSize: viewportSize,
      pageWidth: pageWidth,
      pageHeight: pageHeight,
      usePortrait: usePortrait,
      orientationOverride: orientationOverride,
    );
    final resolvedMode = mode;
    return PageflipLayout(
      mode: resolvedMode,
      orientation: layout.orientation,
      bounds: layout.bounds,
    );
  }
}
