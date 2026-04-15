export 'pageflip_book.dart';
export 'src/legacy/pageflip_book_legacy_exports.dart';

import 'dart:ui';

import 'package:quwoquan_app/components/pageflip_book/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book/src/render/soft/pageflip_book_single_backward_soft_frame.dart';
import 'package:quwoquan_app/components/pageflip_book/src/scene/pageflip_book_scene_contract.dart';
import 'package:quwoquan_app/components/pageflip_book/src/snapshot/pageflip_book_snapshot_contract.dart';
import 'package:quwoquan_app/components/pageflip_book/src/legacy/pageflip_book_legacy_exports.dart';

class PageflipBookLegacyAdapter {
  const PageflipBookLegacyAdapter._();

  static StPageFlipLayout computeLayout({
    required Size viewportSize,
    required double pageWidth,
    required double pageHeight,
    bool usePortrait = true,
    PageflipBookDisplayMode? displayMode,
  }) {
    return computeStPageFlipLayout(
      viewportSize: viewportSize,
      pageWidth: pageWidth,
      pageHeight: pageHeight,
      usePortrait: usePortrait,
      orientationOverride: displayMode == null
          ? null
          : _legacyOrientationForDisplayMode(displayMode),
    );
  }

  static StPageFlipSpreadModel createSpreadModel({
    required int pageCount,
    required bool showCover,
  }) {
    return StPageFlipSpreadModel(
      pageCount: pageCount,
      showCover: showCover,
    );
  }

  static StPageFlipController createController({
    required int pageCount,
    required bool showCover,
    required Size viewportSize,
    required double pageWidth,
    required double pageHeight,
    required int initialPage,
    bool usePortrait = true,
    PageflipBookDisplayMode? displayMode,
    int flippingTimeMs = 1000,
    double maxShadowOpacity = 1.0,
  }) {
    return StPageFlipController(
      spreadModel: createSpreadModel(
        pageCount: pageCount,
        showCover: showCover,
      ),
      layout: computeLayout(
        viewportSize: viewportSize,
        pageWidth: pageWidth,
        pageHeight: pageHeight,
        usePortrait: usePortrait,
        displayMode: displayMode,
      ),
      initialPage: initialPage,
      flippingTimeMs: flippingTimeMs,
      maxShadowOpacity: maxShadowOpacity,
    );
  }

  static void updateController({
    required StPageFlipController controller,
    required int pageCount,
    required bool showCover,
    required Size viewportSize,
    required double pageWidth,
    required double pageHeight,
    required int currentPage,
    bool usePortrait = true,
    PageflipBookDisplayMode? displayMode,
  }) {
    controller.updateConfiguration(
      spreadModel: createSpreadModel(
        pageCount: pageCount,
        showCover: showCover,
      ),
      layout: computeLayout(
        viewportSize: viewportSize,
        pageWidth: pageWidth,
        pageHeight: pageHeight,
        usePortrait: usePortrait,
        displayMode: displayMode,
      ),
      currentPage: currentPage,
    );
  }

  static StPageFlipOrientation _legacyOrientationForDisplayMode(
    PageflipBookDisplayMode displayMode,
  ) {
    return displayMode == PageflipBookDisplayMode.spread
        ? StPageFlipOrientation.landscape
        : StPageFlipOrientation.portrait;
  }

  static ArticleBackwardPageSurfaceBinding? resolveBackwardSurfaceBindingForScene(
    StPageFlipScene scene,
  ) {
    return resolveArticleBackwardPageSurfaceBinding(
      direction: scene.direction,
      flippingPageIndex: scene.flippingPageIndex,
      currentPageIndex: scene.currentPageIndex,
    );
  }

  static PageflipBookSheetBinding? resolveSheetBindingForScene(
    StPageFlipScene scene,
  ) {
    final textureBinding = resolveTextureBindingForScene(scene);
    final direction = scene.direction;
    if (textureBinding == null || direction == null) {
      return null;
    }
    return PageflipBookSheetBinding(
      direction: direction == StPageFlipDirection.forward
          ? PageflipBookDirection.forward
          : PageflipBookDirection.backward,
      rectoPageIndex: textureBinding.rectoPageIndex,
      versoPageIndex: textureBinding.versoPageIndex,
      bottomPageIndex: textureBinding.bottomPageIndex,
    );
  }

  static PageflipBookSurfaceRoleBinding? resolveSurfaceRoleBindingForScene(
    StPageFlipScene scene,
  ) {
    final roles = <PageflipBookSurfaceRole, int>{};
    final leftPageIndex = scene.visibleSpread.leftPageIndex;
    final rightPageIndex = scene.visibleSpread.rightPageIndex;
    if (leftPageIndex != null) {
      roles[PageflipBookSurfaceRole.staticLeft] = leftPageIndex;
    }
    if (rightPageIndex != null) {
      roles[PageflipBookSurfaceRole.staticRight] = rightPageIndex;
    }
    final direction = scene.direction;
    final flippingPageIndex = scene.flippingPageIndex;
    if (direction != null && flippingPageIndex != null) {
      if (direction == StPageFlipDirection.forward) {
        final coveredCurrentPageIndex =
            scene.visibleSpread.rightPageIndex ?? scene.currentPageIndex;
        final underPageIndex = scene.bottomPageIndex ?? flippingPageIndex;
        roles[PageflipBookSurfaceRole.coveredCurrent] =
            coveredCurrentPageIndex;
        roles[PageflipBookSurfaceRole.turningFront] = flippingPageIndex;
        roles[PageflipBookSurfaceRole.turningBack] = underPageIndex;
        roles[PageflipBookSurfaceRole.nextUnder] = underPageIndex;
      } else {
        final coveredCurrentPageIndex =
            scene.bottomPageIndex ??
            scene.visibleSpread.rightPageIndex ??
            scene.currentPageIndex;
        roles[PageflipBookSurfaceRole.coveredCurrent] =
            coveredCurrentPageIndex;
        roles[PageflipBookSurfaceRole.turningFront] = flippingPageIndex;
        roles[PageflipBookSurfaceRole.turningBack] = coveredCurrentPageIndex;
        roles[PageflipBookSurfaceRole.nextUnder] = coveredCurrentPageIndex;
      }
    }
    return roles.isEmpty ? null : PageflipBookSurfaceRoleBinding(roles: roles);
  }

  static PageflipBookSingleBackwardSoftFrame?
  resolveSingleBackwardSoftFrameForScene(
    StPageFlipScene scene,
  ) {
    if (scene.direction != StPageFlipDirection.back ||
        scene.layout.orientation != StPageFlipOrientation.portrait) {
      return null;
    }
    final progress = scene.renderFrame?.progress ??
        ((scene.calculation?.getFlippingProgress() ?? 0) / 100)
            .clamp(0.0, 1.0)
            .toDouble();
    final frame =
        scene.renderFrame?.backwardLeafFrame ??
        resolveArticlePageBackwardLeafFrame(
          direction: scene.direction!,
          progress: progress,
          reversePose: scene.reversePose,
        );
    if (frame == null) {
      return null;
    }
    return PageflipBookSingleBackwardSoftFrame(
      phase: switch (frame.phase) {
        ArticlePageBackwardLeafPhase.emerge =>
          PageflipBookSingleBackwardSoftPhase.emerge,
        ArticlePageBackwardLeafPhase.unroll =>
          PageflipBookSingleBackwardSoftPhase.unroll,
        ArticlePageBackwardLeafPhase.settle =>
          PageflipBookSingleBackwardSoftPhase.settle,
      },
      emergenceProgress: frame.emergenceProgress,
      unrollProgress: frame.unrollProgress,
      settleProgress: frame.settleProgress,
      coveredWidthNormalized: frame.coveredWidthNormalized,
      laidDownWidthNormalized: frame.laidDownWidthNormalized,
      curlWidthNormalized: frame.curlWidthNormalized,
      rectoRevealWidthNormalized: frame.rectoRevealWidthNormalized,
      curlPivotNormalized: frame.curlPivotNormalized,
      edgeLift: frame.edgeLift,
      liftDirection: scene.corner == StPageFlipCorner.top ? -1.0 : 1.0,
      shadowAxisNormalized: frame.curlPivotNormalized,
      commitProgress: frame.coveredWidthNormalized,
    );
  }

  static ArticlePageTextureBinding? resolveTextureBindingForScene(
    StPageFlipScene scene,
  ) {
    return resolveArticlePageTextureBinding(
      direction: scene.direction,
      flippingPageIndex: scene.flippingPageIndex,
      bottomPageIndex: scene.bottomPageIndex,
      currentPageIndex: scene.currentPageIndex,
    );
  }

  static ArticlePageTextureSession? resolveTextureSession({
    required ArticlePageTextureSession? existing,
    required ArticlePageTextureBinding? binding,
    required ArticlePageTextureBundle? resolvedBundle,
    required bool supportsHighFidelity,
    required bool freezeBinding,
  }) {
    return resolveArticlePageTextureSession(
      existing: existing,
      binding: binding,
      resolvedBundle: resolvedBundle,
      supportsHighFidelity: supportsHighFidelity,
      freezeBinding: freezeBinding,
    );
  }

  static PageflipBookTextureSessionContract? resolveTextureSessionContract({
    required PageflipBookSurfaceRoleBinding? binding,
    PageflipBookSheetBinding? sheetBinding,
    required bool preferHighFidelity,
    required bool hasResolvedBundle,
    bool hasMatchingBinding = true,
  }) {
    if (binding == null) {
      return null;
    }
    return PageflipBookTextureSessionContract(
      binding: binding,
      sheetBinding: sheetBinding,
      preferHighFidelity: preferHighFidelity,
      hasResolvedBundle: hasResolvedBundle,
      hasMatchingBinding: hasMatchingBinding,
    );
  }
}
