import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class PageflipBookIsolatedScene {
  const PageflipBookIsolatedScene({
    required this.legacyScene,
    required this.stageSize,
    required this.pageRect,
    required this.pageSize,
    required this.sheetBinding,
  });

  factory PageflipBookIsolatedScene.fromLegacyScene({
    required StPageFlipScene legacyScene,
    required Size stageSize,
  }) {
    final direction =
        legacyScene.renderFrame?.renderDirection ?? legacyScene.direction;
    final pageRect = resolveBookPageRect(
      legacyScene.layout,
      isRightPage: direction != StPageFlipDirection.back,
    );
    return PageflipBookIsolatedScene(
      legacyScene: legacyScene,
      stageSize: stageSize,
      pageRect: pageRect,
      pageSize: pageRect.size,
      sheetBinding: _resolveSheetBinding(legacyScene),
    );
  }

  final StPageFlipScene legacyScene;
  final Size stageSize;
  final Rect pageRect;
  final Size pageSize;
  final PageflipBookIsolatedSheetBinding? sheetBinding;

  StPageFlipDirection? get direction =>
      legacyScene.renderFrame?.renderDirection ?? legacyScene.direction;

  StPageFlipCorner? get corner =>
      legacyScene.renderFrame?.corner ?? legacyScene.corner;

  StPageFlipRenderFrame? get renderFrame => legacyScene.renderFrame;

  StPageFlipCalculation? get calculation => legacyScene.calculation;

  bool get isInteractive =>
      legacyScene.direction != null && sheetBinding != null && corner != null;

  Path buildBottomClipPath() {
    final direction = this.direction;
    if (direction == null) {
      return Path()..addRect(pageRect);
    }
    final renderFrame = legacyScene.renderFrame;
    final calculation = legacyScene.calculation;
    final area =
        renderFrame?.bottomClipArea ?? calculation?.getBottomClipArea();
    final anchor =
        renderFrame?.bottomAnchor ?? calculation?.getBottomPagePosition();
    final pageRectPath = Path()..addRect(pageRect);
    if (area == null || area.length < 3 || anchor == null) {
      return pageRectPath;
    }
    final polygon = area
        .map((point) => Offset(point.dx - anchor.dx, point.dy - anchor.dy))
        .toList(growable: false);
    final position = convertBookPointToViewport(
      anchor,
      legacyScene.layout.bounds,
      direction: direction,
    );
    final path = Path()
      ..moveTo(position.dx + polygon.first.dx, position.dy + polygon.first.dy);
    for (final point in polygon.skip(1)) {
      path.lineTo(position.dx + point.dx, position.dy + point.dy);
    }
    path.close();
    return Path.combine(PathOperation.intersect, pageRectPath, path);
  }
}

PageflipBookIsolatedSheetBinding? _resolveSheetBinding(StPageFlipScene scene) {
  final binding = resolveArticlePageTextureBinding(
    direction: scene.direction,
    flippingPageIndex: scene.flippingPageIndex,
    bottomPageIndex: scene.bottomPageIndex,
    currentPageIndex: scene.currentPageIndex,
  );
  if (binding == null) {
    return null;
  }
  return PageflipBookIsolatedSheetBinding(
    direction: binding.direction == StPageFlipDirection.forward
        ? PageflipBookIsolatedDirection.forward
        : PageflipBookIsolatedDirection.backward,
    rectoPageIndex: binding.rectoPageIndex,
    versoPageIndex: binding.versoPageIndex,
    bottomPageIndex: binding.bottomPageIndex,
  );
}
