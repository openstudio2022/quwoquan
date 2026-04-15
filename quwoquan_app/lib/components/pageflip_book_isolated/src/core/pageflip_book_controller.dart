import 'dart:ui';

import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/animation_plan_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/fold_axis_state_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/leaf_pose_solver_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/page_touch_state_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/scene/pageflip_book_scene.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/spread_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

class PageflipBookIsolatedController {
  PageflipBookIsolatedController({
    required this.pageCount,
    this.initialPage = 0,
  }) : _currentPageIndex = pageCount <= 0
           ? 0
           : initialPage.clamp(0, pageCount - 1).toInt();

  final int pageCount;
  final int initialPage;

  Size? _stageSize;
  StPageFlipLayout? _layout;
  StPageFlipSpreadModel? _spreadModel;
  _InteractionState? _interaction;
  int _currentPageIndex;

  int get currentPageIndex => _currentPageIndex;

  void updateViewport({required Size stageSize, required Size pageSize}) {
    _stageSize = stageSize;
    _layout = computeStPageFlipLayout(
      viewportSize: stageSize,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
      usePortrait: true,
      orientationOverride: StPageFlipOrientation.portrait,
    );
    _spreadModel = StPageFlipSpreadModel(pageCount: pageCount);
    if (pageCount <= 0) {
      _currentPageIndex = 0;
      _interaction = null;
      return;
    }
    _currentPageIndex = _currentPageIndex.clamp(0, pageCount - 1).toInt();
  }

  PageflipBookIsolatedScene? sceneForStage(Size stageSize) {
    final layout = _layout;
    final spreadModel = _spreadModel;
    if (layout == null || spreadModel == null || pageCount <= 0) {
      return null;
    }
    final pageRect = resolveBookPageRect(layout, isRightPage: true);
    final visibleSpread = spreadModel.visibleSpreadForIndex(
      _currentPageIndex,
      layout.orientation,
    );
    final interaction = _interaction;
    if (interaction == null) {
      return PageflipBookIsolatedScene(
        stageSize: stageSize,
        pageRect: pageRect,
        pageSize: pageRect.size,
        layout: layout,
        visibleSpread: visibleSpread,
        currentPageIndex: _currentPageIndex,
        sheetBinding: null,
      );
    }
    final roles = _resolveRoleIndices(interaction.direction);
    return PageflipBookIsolatedScene(
      stageSize: stageSize,
      pageRect: pageRect,
      pageSize: pageRect.size,
      layout: layout,
      visibleSpread: visibleSpread,
      currentPageIndex: _currentPageIndex,
      sheetBinding: PageflipBookIsolatedSheetBinding(
        direction: interaction.direction,
        rectoPageIndex: roles.rectoPageIndex,
        versoPageIndex: roles.versoPageIndex,
        bottomPageIndex: roles.bottomPageIndex,
      ),
      direction: interaction.direction,
      corner: interaction.corner,
      touchState: interaction.touchState,
      foldAxisState: interaction.foldAxisState,
      pose: resolveLeafPoseV2(
        foldAxisState: interaction.foldAxisState,
        pageSize: pageRect.size,
      ),
      coveredCurrentPageIndex: roles.coveredCurrentPageIndex,
      turningFrontPageIndex: roles.rectoPageIndex,
      turningBackPageIndex: roles.versoPageIndex,
      nextUnderPageIndex: roles.bottomPageIndex,
    );
  }

  bool canFlip(PageflipBookIsolatedDirection direction) {
    if (pageCount <= 0) {
      return false;
    }
    return direction.isForward
        ? _currentPageIndex < pageCount - 1
        : _currentPageIndex > 0;
  }

  PageflipBookIsolatedDirection directionForPoint(Offset localPosition) {
    final stageSize = _stageSize;
    if (stageSize == null) {
      return PageflipBookIsolatedDirection.forward;
    }
    return localPosition.dx < stageSize.width / 2
        ? PageflipBookIsolatedDirection.backward
        : PageflipBookIsolatedDirection.forward;
  }

  PageflipBookIsolatedCorner cornerForPoint(Offset localPosition) {
    final pageRect = _pageRect;
    if (pageRect == null) {
      return PageflipBookIsolatedCorner.bottom;
    }
    return localPosition.dy < pageRect.center.dy
        ? PageflipBookIsolatedCorner.top
        : PageflipBookIsolatedCorner.bottom;
  }

  bool start(Offset localPosition) {
    final bounds = _bounds;
    if (bounds == null) {
      return false;
    }
    final direction = directionForPoint(localPosition);
    if (!canFlip(direction)) {
      return false;
    }
    _interaction = _interactionForTouchState(
      PageTouchStateV2.fromStagePoint(
        stagePoint: localPosition,
        bounds: bounds,
        direction: direction,
        corner: cornerForPoint(localPosition),
      ),
    );
    return true;
  }

  void fold(Offset localPosition) {
    final interaction = _interaction;
    final bounds = _bounds;
    if (interaction == null || bounds == null) {
      return;
    }
    _interaction = _interactionForTouchState(
      PageTouchStateV2.fromStagePoint(
        stagePoint: localPosition,
        bounds: bounds,
        direction: interaction.direction,
        corner: interaction.corner,
      ),
    );
  }

  PageflipBookIsolatedAnimationPlan? stopMove() {
    final interaction = _interaction;
    final bounds = _bounds;
    if (interaction == null) {
      return null;
    }
    if (bounds == null) {
      return null;
    }
    final commitsTurn = interaction.foldAxisState.progress >= 0.5;
    if (!commitsTurn && interaction.foldAxisState.progress <= 0.001) {
      return null;
    }
    return buildPageflipBookIsolatedAnimationPlan(
      fromTouchState: interaction.touchState,
      toWorkingPagePoint: _targetWorkingPagePoint(
        bounds: bounds,
        corner: interaction.corner,
        commitsTurn: commitsTurn,
      ),
      bounds: bounds,
      commitsTurn: commitsTurn,
    );
  }

  PageflipBookIsolatedAnimationPlan? flip(
    PageflipBookIsolatedDirection direction,
  ) {
    final bounds = _bounds;
    if (bounds == null || !canFlip(direction)) {
      return null;
    }
    final corner = PageflipBookIsolatedCorner.bottom;
    final fromTouchState = _programmaticStartTouchState(
      bounds: bounds,
      direction: direction,
      corner: corner,
    );
    _interaction = _interactionForTouchState(fromTouchState);
    return buildPageflipBookIsolatedAnimationPlan(
      fromTouchState: fromTouchState,
      toWorkingPagePoint: _targetWorkingPagePoint(
        bounds: bounds,
        corner: corner,
        commitsTurn: true,
      ),
      bounds: bounds,
      commitsTurn: true,
    );
  }

  void applyAnimationFrame(PageflipBookIsolatedAnimationFrame frame) {
    if (_bounds == null) {
      return;
    }
    _interaction = _interactionForTouchState(frame.touchState);
  }

  void completeAnimation(PageflipBookIsolatedAnimationPlan plan) {
    if (plan.commitsTurn) {
      _currentPageIndex += plan.direction.isForward ? 1 : -1;
      if (pageCount > 0) {
        _currentPageIndex = _currentPageIndex.clamp(0, pageCount - 1).toInt();
      } else {
        _currentPageIndex = 0;
      }
    }
    _interaction = null;
  }

  void cancelInteraction() {
    _interaction = null;
  }

  Set<int> textureWindowForDirection(PageflipBookIsolatedDirection direction) {
    final current = currentPageIndex;
    final indices = <int>{current};
    if (direction.isForward) {
      if (current + 1 < pageCount) {
        indices.add(current + 1);
      }
    } else if (current - 1 >= 0) {
      indices.add(current - 1);
    }
    return indices;
  }

  Rect? get _pageRect {
    final layout = _layout;
    if (layout == null) {
      return null;
    }
    return resolveBookPageRect(layout, isRightPage: true);
  }

  StPageFlipBoundsRect? get _bounds => _layout?.bounds;

  _InteractionState _interactionForTouchState(PageTouchStateV2 touchState) {
    final bounds = _bounds;
    final pageSize = _pageRect?.size;
    if (bounds == null || pageSize == null) {
      return _InteractionState(
        touchState: touchState,
        foldAxisState: resolveFoldAxisStateV2(
          touchState: touchState,
          pageSize: const Size(1, 1),
        ),
      );
    }
    try {
      return _InteractionState(
        touchState: touchState,
        foldAxisState: resolveFoldAxisStateV2(
          touchState: touchState,
          pageSize: pageSize,
        ),
      );
    } catch (_) {
      final safeTouchState = PageTouchStateV2.fromWorkingPagePoint(
        workingPagePoint: Offset(
          bounds.pageWidth - 1,
          touchState.corner == PageflipBookIsolatedCorner.bottom
              ? pageSize.height - 1
              : 1,
        ),
        bounds: bounds,
        direction: touchState.direction,
        corner: touchState.corner,
      );
      return _InteractionState(
        touchState: safeTouchState,
        foldAxisState: resolveFoldAxisStateV2(
          touchState: safeTouchState,
          pageSize: pageSize,
        ),
      );
    }
  }

  PageTouchStateV2 _programmaticStartTouchState({
    required StPageFlipBoundsRect bounds,
    required PageflipBookIsolatedDirection direction,
    required PageflipBookIsolatedCorner corner,
  }) {
    final topMargin = bounds.height / 10;
    final startPoint = Offset(
      bounds.pageWidth - topMargin,
      corner == PageflipBookIsolatedCorner.bottom
          ? bounds.height - topMargin
          : topMargin,
    );
    return PageTouchStateV2.fromWorkingPagePoint(
      workingPagePoint: startPoint,
      bounds: bounds,
      direction: direction,
      corner: corner,
    );
  }

  Offset _targetWorkingPagePoint({
    required StPageFlipBoundsRect bounds,
    required PageflipBookIsolatedCorner corner,
    required bool commitsTurn,
  }) {
    return Offset(
      commitsTurn ? -bounds.pageWidth : bounds.pageWidth,
      corner == PageflipBookIsolatedCorner.bottom ? bounds.height : 0,
    );
  }

  _IsolatedRoleIndices _resolveRoleIndices(
    PageflipBookIsolatedDirection direction,
  ) {
    if (direction.isForward) {
      final nextPageIndex = (_currentPageIndex + 1).clamp(0, pageCount - 1);
      return _IsolatedRoleIndices(
        rectoPageIndex: _currentPageIndex,
        versoPageIndex: nextPageIndex,
        bottomPageIndex: nextPageIndex,
        coveredCurrentPageIndex: _currentPageIndex,
      );
    }
    final previousPageIndex = (_currentPageIndex - 1).clamp(0, pageCount - 1);
    return _IsolatedRoleIndices(
      rectoPageIndex: previousPageIndex,
      versoPageIndex: _currentPageIndex,
      bottomPageIndex: previousPageIndex,
      coveredCurrentPageIndex: _currentPageIndex,
    );
  }
}

class _InteractionState {
  const _InteractionState({
    required this.touchState,
    required this.foldAxisState,
  });

  final PageTouchStateV2 touchState;
  final FoldAxisStateV2 foldAxisState;

  PageflipBookIsolatedDirection get direction => touchState.direction;

  PageflipBookIsolatedCorner get corner => touchState.corner;
}

class _IsolatedRoleIndices {
  const _IsolatedRoleIndices({
    required this.rectoPageIndex,
    required this.versoPageIndex,
    required this.bottomPageIndex,
    required this.coveredCurrentPageIndex,
  });

  final int rectoPageIndex;
  final int versoPageIndex;
  final int bottomPageIndex;
  final int coveredCurrentPageIndex;
}
