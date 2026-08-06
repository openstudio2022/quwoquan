part of 'article_read_only_book_deck.dart';

extension _ArticleReadOnlyBookDeckGestures on _ArticleReadOnlyBookDeckState {
  void _emitPageCurlAbortForPlan(StPageFlipAnimationPlan plan) {
    final calculation = _pageFlipScene?.calculation;
    final progress = ((calculation?.getFlippingProgress() ?? 0) / 100)
        .clamp(0.0, 1.0)
        .toDouble();
    _clearPageTransition();
    if (progress <= 0) {
      return;
    }
    _deck.onPageCurlAborted?.call(
      ArticleReaderPageCurlAbort(
        corner: _cornerNameFromPageFlip(plan.corner, plan.direction),
        progress: progress,
        direction: plan.direction == StPageFlipDirection.forward
            ? 'forward'
            : 'backward',
      ),
    );
  }

  void _handlePageFlipAnimationTick() {
    if (!_isMounted) {
      return;
    }
    final controller = _pageFlipController;
    final plan = _activePageFlipAnimation;
    if (controller == null || plan == null || plan.frames.isEmpty) {
      return;
    }
    final maxIndex = plan.frames.length - 1;
    final nextIndex = maxIndex == 0
        ? 0
        : (_pageFlipAnimationController.value * maxIndex).round().clamp(
            0,
            maxIndex,
          );
    if (nextIndex == _lastAnimationFrameIndex) {
      return;
    }
    controller.applyAnimationFrame(plan.frames[nextIndex]);
    _lastAnimationFrameIndex = nextIndex;
    _setDeckState(() {});
  }

  void _handlePageFlipAnimationStatus(AnimationStatus status) {
    if (status != AnimationStatus.completed) {
      return;
    }
    final controller = _pageFlipController;
    final plan = _activePageFlipAnimation;
    if (controller == null || plan == null) {
      return;
    }
    final previousPage = controller.currentPageIndex;
    final lastFrameIndex = plan.frames.length - 1;
    if (lastFrameIndex >= 0 && _lastAnimationFrameIndex != lastFrameIndex) {
      controller.applyAnimationFrame(plan.frames[lastFrameIndex]);
      _lastAnimationFrameIndex = lastFrameIndex;
    }
    controller.completeAnimation(plan);
    _activePageFlipAnimation = null;
    _lastAnimationFrameIndex = -1;
    final nextPage = controller.currentPageIndex;
    if (!_isMounted) {
      return;
    }
    _setDeckState(() {
      _currentPage = nextPage;
    });
    _clearPageFlipTextureSession();
    if (plan.isTurned) {
      _emitPageFlipCommit(fromPage: previousPage, toPage: _currentPage);
      _deck.onPageChanged?.call(_currentPage);
    }
  }

  void _runPageFlipAnimation(
    StPageFlipAnimationPlan plan, {
    bool reportAbort = false,
  }) {
    if (reportAbort) {
      _emitPageCurlAbortForPlan(plan);
    }
    if (plan.isTurned && _pageTransitionStartedAt == null) {
      _startPageTransition('page_curl');
    }
    _startPageFlipTextureSession(plan.direction);
    _activePageFlipAnimation = plan;
    _lastAnimationFrameIndex = -1;
    _pageFlipAnimationController.duration = plan.duration;
    _pageFlipAnimationController.forward(from: 0);
  }

  void _triggerOverflow(StPageFlipDirection direction) {
    if (_overflowTriggered) {
      return;
    }
    _overflowTriggered = true;
    if (direction == StPageFlipDirection.forward) {
      _deck.onOverflowNext?.call();
    } else {
      _deck.onOverflowPrevious?.call();
    }
  }

  void _resetOverflowTracking() {
    _edgeOverflowDistance = 0;
    _pendingOverflowDirection = null;
    _overflowTriggered = false;
  }

  VoidCallback? _overflowCallbackForDirection(StPageFlipDirection direction) {
    return direction == StPageFlipDirection.forward
        ? _deck.onOverflowNext
        : _deck.onOverflowPrevious;
  }

  bool _canStartEdgeOverflow(
    Offset localPosition,
    StPageFlipDirection direction,
  ) {
    final callback = _overflowCallbackForDirection(direction);
    final controller = _pageFlipController;
    final stageSize = _lastInteractiveStageSize;
    if (callback == null || controller == null || stageSize == null) {
      return false;
    }
    if (controller.canFlipDirection(direction)) {
      return false;
    }
    if (direction == StPageFlipDirection.back) {
      return localPosition.dx <=
          _ArticleReadOnlyBookDeckState._overflowEdgeStartInset;
    }
    return localPosition.dx >=
        stageSize.width - _ArticleReadOnlyBookDeckState._overflowEdgeStartInset;
  }

  bool _matchesOverflowDragDirection(
    Offset delta,
    StPageFlipDirection direction,
  ) {
    return direction == StPageFlipDirection.back ? delta.dx > 0 : delta.dx < 0;
  }

  bool _matchesOverflowVelocity(
    StPageFlipDirection direction,
    double velocityX,
  ) {
    return direction == StPageFlipDirection.back
        ? velocityX > 0
        : velocityX < 0;
  }

  void _trackEdgeOverflow(Offset delta, StPageFlipDirection direction) {
    if (!_matchesOverflowDragDirection(delta, direction)) {
      _edgeOverflowDistance = 0;
      return;
    }
    if (_pendingOverflowDirection != direction) {
      _pendingOverflowDirection = direction;
      _edgeOverflowDistance = 0;
    }
    _edgeOverflowDistance += delta.dx.abs();
    if (_edgeOverflowDistance >=
        _ArticleReadOnlyBookDeckState._overflowSwitchDistance) {
      _triggerOverflow(direction);
    }
  }

  double _springDampedOffset(double raw, double maxPull) {
    if (raw <= 0 || maxPull <= 0) {
      return 0;
    }
    final damping = maxPull / 1.2;
    return (maxPull * (1 - math.exp(-raw / damping))).clamp(0.0, maxPull);
  }

  bool _canStartBoundaryOverflow(
    Offset localPosition,
    StPageFlipDirection direction,
    Size stageSize,
  ) {
    final callback = _overflowCallbackForDirection(direction);
    if (callback == null) {
      return false;
    }
    if (direction == StPageFlipDirection.back) {
      return localPosition.dx <=
          _ArticleReadOnlyBookDeckState._overflowEdgeStartInset;
    }
    return localPosition.dx >=
        stageSize.width - _ArticleReadOnlyBookDeckState._overflowEdgeStartInset;
  }

  void _setBoundaryRubberBandOffset(
    double visualOffset, {
    required bool animate,
    double? rawOffset,
  }) {
    final safeVisualOffset = visualOffset.abs() < 0.1 ? 0.0 : visualOffset;
    final safeRawOffset =
        rawOffset ??
        (safeVisualOffset == 0.0 ? 0.0 : _boundaryRubberBandRawOffset);
    if ((_boundaryRubberBandOffset - safeVisualOffset).abs() < 0.1 &&
        (_boundaryRubberBandRawOffset - safeRawOffset).abs() < 0.1 &&
        _shouldAnimateBoundaryRubberBandReset == animate) {
      return;
    }
    _setDeckState(() {
      _boundaryRubberBandOffset = safeVisualOffset;
      _boundaryRubberBandRawOffset = safeRawOffset;
      _shouldAnimateBoundaryRubberBandReset = animate;
    });
  }

  void _applyBoundaryRubberBand(Offset delta, StPageFlipDirection direction) {
    final nextRaw = direction == StPageFlipDirection.back
        ? (_boundaryRubberBandRawOffset + delta.dx).clamp(0.0, double.infinity)
        : (_boundaryRubberBandRawOffset + delta.dx).clamp(
            double.negativeInfinity,
            0.0,
          );
    final magnitude = _springDampedOffset(
      nextRaw.abs(),
      _ArticleReadOnlyBookDeckState._boundaryRubberBandMaxOffset,
    );
    final visualOffset = direction == StPageFlipDirection.back
        ? magnitude
        : -magnitude;
    _setBoundaryRubberBandOffset(
      visualOffset,
      animate: false,
      rawOffset: nextRaw.toDouble(),
    );
  }

  void _resetBoundaryRubberBand({required bool animate}) {
    _setBoundaryRubberBandOffset(0, animate: animate, rawOffset: 0);
  }

  void _resetBoundaryTracking({required bool animate}) {
    _boundaryDragStartLocalPosition = null;
    _boundaryDragDirection = null;
    _resetOverflowTracking();
    _resetBoundaryRubberBand(animate: animate);
  }

  void _handleBoundaryPanStart(
    Offset localPosition, {
    StPageFlipDirection? direction,
  }) {
    _boundaryDragStartLocalPosition = localPosition;
    _boundaryDragDirection = direction;
    _resetOverflowTracking();
    _resetBoundaryRubberBand(animate: false);
  }

  void _handleBoundaryDragDelta(
    Offset delta,
    StPageFlipDirection direction,
    Size stageSize,
  ) {
    _boundaryDragDirection = direction;
    _applyBoundaryRubberBand(delta, direction);
    final dragStart = _boundaryDragStartLocalPosition;
    if (dragStart == null ||
        !_canStartBoundaryOverflow(dragStart, direction, stageSize)) {
      _edgeOverflowDistance = 0;
      _pendingOverflowDirection = null;
      return;
    }
    _trackEdgeOverflow(delta, direction);
  }

  void _handleBoundaryPanUpdate(Offset delta, Size stageSize) {
    if (delta.dx == 0) {
      return;
    }
    final direction = delta.dx > 0
        ? StPageFlipDirection.back
        : StPageFlipDirection.forward;
    _handleBoundaryDragDelta(delta, direction, stageSize);
  }

  void _finishBoundaryPan(Velocity velocity, Size stageSize) {
    final dragStart = _boundaryDragStartLocalPosition;
    final overflowDirection = _pendingOverflowDirection;
    if (dragStart != null && overflowDirection != null) {
      final velocityX = velocity.pixelsPerSecond.dx;
      if (!_overflowTriggered &&
          velocityX.abs() >=
              _ArticleReadOnlyBookDeckState._overflowSwitchVelocity &&
          _canStartBoundaryOverflow(dragStart, overflowDirection, stageSize) &&
          _matchesOverflowVelocity(overflowDirection, velocityX)) {
        _triggerOverflow(overflowDirection);
      }
    }
    _resetBoundaryTracking(animate: true);
  }

  void _handleStageTapUp(TapUpDetails details) {
    if (!_showsPageCurl || _hasActivePageCurlAnimation) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    final direction = controller.directionForGlobalPoint(details.localPosition);
    if (_canStartEdgeOverflow(details.localPosition, direction)) {
      return;
    }
    if (!_ensureBackTextureReadyForDirection(direction)) {
      return;
    }
    final plan = controller.flip(details.localPosition);
    if (plan == null) {
      return;
    }
    _startPageTransition('page_curl');
    _setDeckState(() {});
    _runPageFlipAnimation(plan);
  }

  bool _isPageFlipIntentForDirection(
    ImmersiveGestureIntent? intent,
    StPageFlipDirection direction,
  ) {
    return switch (direction) {
      StPageFlipDirection.forward =>
        intent == ImmersiveGestureIntent.pageFlipForward,
      StPageFlipDirection.back => intent == ImmersiveGestureIntent.pageFlipBack,
    };
  }

  StPageFlipDirection? _directionFromGestureIntent(
    ImmersiveGestureIntent? intent,
  ) {
    return switch (intent) {
      ImmersiveGestureIntent.pageFlipForward => StPageFlipDirection.forward,
      ImmersiveGestureIntent.pageFlipBack => StPageFlipDirection.back,
      _ => null,
    };
  }

  ImmersiveGestureIntent? _currentGestureIntent(
    ImmersiveGestureIntentController controller,
  ) {
    if (!controller.isTracking) {
      return null;
    }
    if (controller.lockedIntent != ImmersiveGestureIntent.undecided) {
      return controller.lockedIntent;
    }
    return controller.previewIntent;
  }

  StPageFlipDirection? _directionFromDragDelta(Offset delta) {
    if (delta.dx < 0) {
      return StPageFlipDirection.forward;
    }
    if (delta.dx > 0) {
      return StPageFlipDirection.back;
    }
    return null;
  }

  Offset _syntheticStagePageCurlStartPoint(
    StPageFlipLayout layout, {
    required StPageFlipDirection direction,
    required StPageFlipCorner corner,
    required double touchY,
  }) {
    final bounds = layout.bounds;
    final y = _viewportYForStageTouch(bounds, touchY, corner: corner);
    final x = switch (direction) {
      StPageFlipDirection.forward =>
        bounds.left + bounds.width - AppSpacing.hairline,
      StPageFlipDirection.back => bounds.left + AppSpacing.hairline,
    };
    return Offset(x, y);
  }

  double _viewportYForStageTouch(
    StPageFlipBoundsRect bounds,
    double touchY, {
    required StPageFlipCorner corner,
  }) {
    final clamped = touchY.clamp(
      bounds.top + AppSpacing.hairline,
      bounds.top + bounds.height - AppSpacing.hairline,
    );
    if (clamped.isFinite) {
      return clamped.toDouble();
    }
    return bounds.top +
        (corner == StPageFlipCorner.bottom
            ? bounds.height - AppSpacing.hairline
            : AppSpacing.hairline);
  }

  bool _beginStagePageCurl(
    StPageFlipController controller,
    StPageFlipDirection direction,
    Offset startPosition,
    Offset localPosition,
  ) {
    if (!controller.canFlipDirection(direction)) {
      return false;
    }
    if (!_ensureBackTextureReadyForDirection(
      direction,
      blockCurrentGesture: true,
    )) {
      return false;
    }
    final corner = controller.cornerForGlobalPoint(startPosition);
    final startPoint = _syntheticStagePageCurlStartPoint(
      controller.layout,
      direction: direction,
      corner: corner,
      touchY: startPosition.dy,
    );
    if (!controller.start(startPoint)) {
      return false;
    }
    _activeDragDirection = direction;
    _resetBoundaryRubberBand(animate: false);
    _startPageTransition('page_curl');
    _startPageFlipTextureSession(direction);
    if ((localPosition - startPosition).distance > 0) {
      controller.fold(localPosition);
    } else {
      controller.fold(startPoint);
    }
    _setDeckState(() {});
    return true;
  }

  void _handleStagePanStart(Offset localPosition) {
    if (!_showsPageCurl || _hasActivePageCurlAnimation) {
      return;
    }
    final startPosition = _pointerDownLocalPosition ?? localPosition;
    _dragStartGlobalPosition = startPosition;
    _latestDragGlobalPosition = localPosition;
    _dragStartedAt = DateTime.now();
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    final intentController = _deck.gestureIntentController;
    if (intentController != null) {
      if (intentController.shouldIgnorePageFlipInput) {
        return;
      }
      return;
    }
    final direction = controller.directionForGlobalPoint(startPosition);
    if (!controller.canFlipDirection(direction)) {
      _activeDragDirection = null;
      _handleBoundaryPanStart(startPosition, direction: direction);
      _pendingOverflowDirection = direction;
      return;
    }
    if (!_ensureBackTextureReadyForDirection(
      direction,
      blockCurrentGesture: true,
    )) {
      _dragStartGlobalPosition = null;
      _latestDragGlobalPosition = null;
      _dragStartedAt = null;
      _activeDragDirection = null;
      return;
    }
    _activeDragDirection = direction;
    _resetBoundaryRubberBand(animate: false);
    _startPageTransition('page_curl');
    _startPageFlipTextureSession(direction);
    controller.fold(startPosition);
    if ((localPosition - startPosition).distance > 0) {
      controller.fold(localPosition);
    }
    _setDeckState(() {});
  }

  void _handleStagePanUpdate(Offset localPosition, Offset delta) {
    if (!_showsPageCurl || _hasActivePageCurlAnimation) {
      return;
    }
    if (_textureWarmupBlockedGesture) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    _latestDragGlobalPosition = localPosition;
    final intentController = _deck.gestureIntentController;
    if (intentController != null) {
      final intent = _currentGestureIntent(intentController);
      if (intentController.shouldIgnorePageFlipInput) {
        return;
      }
      final start = _dragStartGlobalPosition ?? localPosition;
      final direction =
          _directionFromGestureIntent(intent) ??
          _directionFromDragDelta(localPosition - start) ??
          _activeDragDirection ??
          controller.scene.direction ??
          controller.directionForGlobalPoint(start);
      if (intent == ImmersiveGestureIntent.boundaryRubberBand) {
        final stageSize = _lastInteractiveStageSize;
        if (stageSize != null && _boundaryDragStartLocalPosition == null) {
          _handleBoundaryPanStart(start, direction: direction);
          _pendingOverflowDirection = direction;
        }
      } else if ((intent == ImmersiveGestureIntent.pageFlipForward ||
              intent == ImmersiveGestureIntent.pageFlipBack) &&
          !_isPageFlipIntentForDirection(intent, direction)) {
        return;
      }
      if (intentController.isPageFlipLocked &&
          controller.scene.direction == null &&
          !_beginStagePageCurl(controller, direction, start, localPosition)) {
        return;
      }
      if (!intentController.isPageFlipLocked &&
          controller.scene.direction == null &&
          _boundaryDragStartLocalPosition == null) {
        return;
      }
    }
    final stageSize = _lastInteractiveStageSize;
    if (_boundaryDragStartLocalPosition != null && stageSize != null) {
      final boundaryDirection =
          _boundaryDragDirection ?? _pendingOverflowDirection;
      if (boundaryDirection != null) {
        _handleBoundaryDragDelta(delta, boundaryDirection, stageSize);
      }
      return;
    }
    final direction =
        _activeDragDirection ??
        controller.scene.direction ??
        controller.directionForGlobalPoint(
          _dragStartGlobalPosition ?? localPosition,
        );
    if (!controller.canFlipDirection(direction)) {
      return;
    }
    if (!_ensureBackTextureReadyForDirection(
      direction,
      blockCurrentGesture: true,
    )) {
      return;
    }
    controller.fold(localPosition);
    _setDeckState(() {});
  }

  void _handleStagePanCancel() {
    _pointerDownLocalPosition = null;
    _dragStartGlobalPosition = null;
    _latestDragGlobalPosition = null;
    _dragStartedAt = null;
    _activeDragDirection = null;
    _textureWarmupBlockedGesture = false;
    _resetBoundaryTracking(animate: true);
    _deck.gestureIntentController?.cancel();
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    controller.cancelInteraction();
    _clearPageTransition();
    _clearPageFlipTextureSession();
    _setDeckState(() {});
  }

  void _handleStagePanEnd(Velocity velocity) {
    var committed = false;
    final controller = _pageFlipController;
    final dragStart = _dragStartGlobalPosition;
    final dragLatest = _latestDragGlobalPosition;
    final dragStartedAt = _dragStartedAt;
    final dragDirection = _activeDragDirection;
    _pointerDownLocalPosition = null;
    _dragStartGlobalPosition = null;
    _latestDragGlobalPosition = null;
    _dragStartedAt = null;
    _activeDragDirection = null;
    final textureWarmupBlockedGesture = _textureWarmupBlockedGesture;
    _textureWarmupBlockedGesture = false;
    final stageSize = _lastInteractiveStageSize;
    if (controller == null) {
      _resetBoundaryTracking(animate: true);
      _deck.gestureIntentController?.finish();
      return;
    }
    if (_boundaryDragStartLocalPosition != null && stageSize != null) {
      _finishBoundaryPan(velocity, stageSize);
      _deck.gestureIntentController?.finish();
      return;
    }
    if (textureWarmupBlockedGesture) {
      _resetBoundaryTracking(animate: true);
      _deck.gestureIntentController?.finish();
      return;
    }
    if (dragStart != null) {
      final direction =
          dragDirection ??
          (dragLatest != null
              ? _directionFromDragDelta(dragLatest - dragStart)
              : null) ??
          controller.directionForGlobalPoint(dragStart);
      if (!controller.canFlipDirection(direction)) {
        _resetBoundaryTracking(animate: true);
        controller.cancelInteraction();
        _clearPageFlipTextureSession();
        _setDeckState(() {});
        _deck.gestureIntentController?.finish();
        return;
      }
    }

    var plan = controller.stopMove();
    _resetBoundaryTracking(animate: true);
    if (plan == null) {
      controller.cancelInteraction();
      _clearPageFlipTextureSession();
      _setDeckState(() {});
      _deck.gestureIntentController?.finish();
      return;
    }
    final direction =
        controller.scene.direction ??
        dragDirection ??
        (dragStart != null && dragLatest != null
            ? _directionFromDragDelta(dragLatest - dragStart)
            : null) ??
        (dragStart != null
            ? controller.directionForGlobalPoint(dragStart)
            : StPageFlipDirection.forward);
    final corner =
        controller.scene.corner ??
        (dragStart != null
            ? controller.cornerForGlobalPoint(dragStart)
            : StPageFlipCorner.bottom);
    final progress =
        controller.scene.renderFrame?.progress ??
        ((controller.scene.calculation?.getFlippingProgress() ?? 0) / 100)
            .clamp(0.0, 1.0)
            .toDouble();
    final releaseDecision = resolvePageflipReleaseDecision(
      isForwardDirection: direction == StPageFlipDirection.forward,
      progress: progress,
      pageWidth: controller.layout.bounds.pageWidth,
      velocityDx: velocity.pixelsPerSecond.dx,
      dragStart: dragStart,
      dragLatest: dragLatest,
      dragStartedAt: dragStartedAt,
    );
    if (!plan.isTurned && releaseDecision.commitsTurn) {
      if (controller.canFlipDirection(direction)) {
        plan = direction == StPageFlipDirection.forward
            ? controller.flipNext(corner)
            : controller.flipPrev(corner);
      }
    }
    if (plan == null) {
      controller.cancelInteraction();
      _setDeckState(() {});
      _deck.gestureIntentController?.finish();
      return;
    }
    plan = plan.copyWith(duration: releaseDecision.settleDuration);
    committed = plan.isTurned;
    if (!plan.isTurned) {
      _runPageFlipAnimation(plan, reportAbort: true);
    } else {
      _runPageFlipAnimation(plan);
    }
    _deck.gestureIntentController?.finish(committed: committed);
  }

  void _handleStageMouseHover(PointerHoverEvent event) {
    if (!_showsPageCurl || _hasActivePageCurlAnimation) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    final direction = controller.directionForGlobalPoint(event.localPosition);
    if (!_ensureBackTextureReadyForDirection(direction)) {
      return;
    }
    final plan = controller.showCorner(event.localPosition);
    if (plan != null) {
      _runPageFlipAnimation(plan);
      return;
    }
    _setDeckState(() {});
  }

  void _handleStageMouseExit(PointerExitEvent event) {
    if (!_showsPageCurl || _hasActivePageCurlAnimation) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    final plan = controller.showCorner(const Offset(-1, -1));
    if (plan != null) {
      _runPageFlipAnimation(plan);
      return;
    }
    controller.cancelInteraction();
    _clearPageFlipTextureSession();
    _setDeckState(() {});
  }

  void _handleStagePointerDownPosition(Offset localPosition) {
    if (!_showsPageCurl) {
      return;
    }
    _pointerDownLocalPosition = localPosition;
    _pointerBridge.handleTouchStart(localPosition, () {});
  }

  void _handleStagePointerMovePosition(Offset localPosition) {
    if (!_showsPageCurl || _dragStartGlobalPosition != null) {
      return;
    }
    _pointerBridge.handleTouchMove(localPosition, () {});
  }

  void _handleStagePointerUpPosition(Offset localPosition) {
    final pointerDownPosition = _pointerDownLocalPosition;
    _pointerDownLocalPosition = null;
    if (!_showsPageCurl || _dragStartGlobalPosition != null) {
      _pointerBridge.cancel();
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      _pointerBridge.cancel();
      return;
    }
    final swipe = _pointerBridge.handleTouchEnd(
      localPosition,
      pageHeight: controller.layout.bounds.height,
    );
    if (swipe == null) {
      return;
    }
    if (!controller.canFlipDirection(swipe.direction)) {
      if (pointerDownPosition != null &&
          _canStartEdgeOverflow(pointerDownPosition, swipe.direction)) {
        _triggerOverflow(swipe.direction);
      }
      return;
    }
    if (!_ensureBackTextureReadyForDirection(swipe.direction)) {
      return;
    }
    final plan = swipe.direction == StPageFlipDirection.forward
        ? controller.flipNext(swipe.corner)
        : controller.flipPrev(swipe.corner);
    if (plan == null) {
      return;
    }
    _startPageTransition('page_curl');
    _runPageFlipAnimation(plan);
  }

  void _handleStagePointerCancelPosition() {
    _pointerDownLocalPosition = null;
    _textureWarmupBlockedGesture = false;
    _pointerBridge.cancel();
  }

  void _startPageTransition(String mechanism) {
    _pageTransitionStartedAt = DateTime.now();
    _pageTransitionMechanism = mechanism;
  }

  void _clearPageTransition() {
    _pageTransitionStartedAt = null;
    _pageTransitionMechanism = null;
  }

  void _emitPageFlipCommit({required int fromPage, required int toPage}) {
    final startedAt = _pageTransitionStartedAt;
    final mechanism = _pageTransitionMechanism;
    _clearPageTransition();
    if (startedAt == null || mechanism == null || fromPage == toPage) {
      return;
    }
    _deck.onPageFlipCommitted?.call(
      ArticleReaderPageFlipCommit(
        fromPage: fromPage,
        toPage: toPage,
        durationMs: DateTime.now().difference(startedAt).inMilliseconds,
        mechanism: mechanism,
      ),
    );
  }

  bool _handleScrollNotification(
    ScrollNotification notification,
    Size stageSize,
  ) {
    if (notification is ScrollStartNotification &&
        notification.dragDetails != null &&
        _pageTransitionStartedAt == null) {
      _startPageTransition(_useDegradedPager ? 'book_style_pager' : 'pager');
    } else if (notification is OverscrollNotification) {
      if (notification.overscroll < 0) {
        _handleBoundaryDragDelta(
          Offset(-notification.overscroll, 0),
          StPageFlipDirection.back,
          stageSize,
        );
      } else if (notification.overscroll > 0) {
        _handleBoundaryDragDelta(
          Offset(-notification.overscroll, 0),
          StPageFlipDirection.forward,
          stageSize,
        );
      }
    } else if (notification is ScrollEndNotification) {
      _finishBoundaryPan(Velocity.zero, stageSize);
      if (_pageFlipScene?.calculation == null) {
        _clearPageTransition();
      }
    }
    return false;
  }

  Key _hotzoneKey(ArticlePageCurlCorner corner) {
    return switch (corner) {
      ArticlePageCurlCorner.topLeft => TestKeys.articlePageCurlHotzoneTopLeft,
      ArticlePageCurlCorner.topRight => TestKeys.articlePageCurlHotzoneTopRight,
      ArticlePageCurlCorner.bottomLeft =>
        TestKeys.articlePageCurlHotzoneBottomLeft,
      ArticlePageCurlCorner.bottomRight =>
        TestKeys.articlePageCurlHotzoneBottomRight,
    };
  }
}
