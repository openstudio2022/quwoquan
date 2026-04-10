import 'dart:ui';

import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/scene/pageflip_book_scene.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/reverse_curl_calculation.dart';
import 'package:quwoquan_app/ui/content/pageflip/spread_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

class PageflipBookIsolatedController {
  PageflipBookIsolatedController({
    required this.pageCount,
    this.initialPage = 0,
  });

  final int pageCount;
  final int initialPage;

  StPageFlipController? _delegate;

  StPageFlipController? get delegate => _delegate;

  int get currentPageIndex => _delegate?.currentPageIndex ?? initialPage;

  void updateViewport({required Size stageSize, required Size pageSize}) {
    final layout = computeStPageFlipLayout(
      viewportSize: stageSize,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
      usePortrait: true,
      orientationOverride: StPageFlipOrientation.portrait,
    );
    final spreadModel = StPageFlipSpreadModel(pageCount: pageCount);
    if (_delegate == null) {
      _delegate = StPageFlipController(
        spreadModel: spreadModel,
        layout: layout,
        initialPage: initialPage,
        useForwardMirroredBackwardPath: true,
      );
      return;
    }
    _delegate!.updateConfiguration(
      spreadModel: spreadModel,
      layout: layout,
      currentPage: currentPageIndex,
    );
  }

  PageflipBookIsolatedScene? sceneForStage(Size stageSize) {
    final delegate = _delegate;
    if (delegate == null) {
      return null;
    }
    return PageflipBookIsolatedScene.fromLegacyScene(
      legacyScene: delegate.scene,
      stageSize: stageSize,
    );
  }

  bool canFlip(PageflipBookIsolatedDirection direction) {
    final delegate = _delegate;
    if (delegate == null) {
      return false;
    }
    return delegate.canFlipDirection(_legacyDirection(direction));
  }

  PageflipBookIsolatedDirection directionForPoint(Offset localPosition) {
    final delegate = _delegate;
    if (delegate == null) {
      return PageflipBookIsolatedDirection.forward;
    }
    final direction = delegate.directionForGlobalPoint(localPosition);
    return direction == StPageFlipDirection.forward
        ? PageflipBookIsolatedDirection.forward
        : PageflipBookIsolatedDirection.backward;
  }

  StPageFlipCorner cornerForPoint(Offset localPosition) {
    final delegate = _delegate;
    if (delegate == null) {
      return StPageFlipCorner.bottom;
    }
    return delegate.cornerForGlobalPoint(localPosition);
  }

  bool start(Offset localPosition) {
    return _delegate?.start(localPosition) ?? false;
  }

  void fold(Offset localPosition) {
    _delegate?.fold(localPosition);
  }

  StPageFlipAnimationPlan? stopMove() {
    return _delegate?.stopMove();
  }

  StPageFlipAnimationPlan? flip(PageflipBookIsolatedDirection direction) {
    final delegate = _delegate;
    if (delegate == null) {
      return null;
    }
    return direction == PageflipBookIsolatedDirection.forward
        ? delegate.flipNext(StPageFlipCorner.bottom)
        : delegate.flipPrev(StPageFlipCorner.bottom);
  }

  void applyAnimationFrame(
    Offset localPagePoint, {
    ReverseFlipPose? reversePose,
  }) {
    _delegate?.applyAnimationFrame(localPagePoint, reversePose: reversePose);
  }

  void completeAnimation(StPageFlipAnimationPlan plan) {
    _delegate?.completeAnimation(plan);
  }

  void cancelInteraction() {
    _delegate?.cancelInteraction();
  }

  Set<int> textureWindowForDirection(PageflipBookIsolatedDirection direction) {
    final current = currentPageIndex;
    final indices = <int>{current};
    if (direction == PageflipBookIsolatedDirection.forward) {
      if (current + 1 < pageCount) {
        indices.add(current + 1);
      }
    } else if (current - 1 >= 0) {
      indices.add(current - 1);
    }
    return indices;
  }

  static StPageFlipDirection _legacyDirection(
    PageflipBookIsolatedDirection direction,
  ) {
    return direction == PageflipBookIsolatedDirection.forward
        ? StPageFlipDirection.forward
        : StPageFlipDirection.back;
  }
}
