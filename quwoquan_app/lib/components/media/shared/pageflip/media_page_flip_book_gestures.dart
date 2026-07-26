part of 'media_page_flip_book.dart';

extension _MediaPageFlipBookStateGestures on _MediaPageFlipBookState {
  Widget _buildGestureLayer(Rect pageRect) {
    return ImmersivePointerGestureLayer(
      key: const ValueKey('media-pageflip-gesture-layer'),
      behavior: HitTestBehavior.translucent,
      onStart: (event) => _startHorizontalDrag(event.localPosition),
      onUpdate: (event) =>
          _updateHorizontalDrag(event.localPosition, event.delta),
      onEnd: (event) => _endHorizontalDrag(event.velocityDx),
      onCancel: (_) => _cancelHorizontalDrag(),
      child: const SizedBox.expand(),
    );
  }

  void _startHorizontalDrag(Offset localPosition) {
    final controller = _controller;
    if (controller == null || _activePlan != null) {
      return;
    }
    final intentController = widget.gestureIntentController;
    if (intentController?.shouldIgnorePageFlipInput ?? false) {
      return;
    }
    _dragStartLocalPosition = localPosition;
    _latestDragLocalPosition = localPosition;
    _dragStartedAt = DateTime.now();
    _activeDragDirection = null;
    _activeDragCorner = null;
    _dragActive = false;
    _reducedMotionTurnCommitted = false;
    _resetOverflowTracking();
  }

  void _updateHorizontalDrag(Offset localPosition, Offset delta) {
    final controller = _controller;
    if (controller == null) {
      return;
    }
    _latestDragLocalPosition = localPosition;
    final start = _dragStartLocalPosition;
    final intentController = widget.gestureIntentController;
    final intent = _currentGestureIntent(intentController);
    if (intentController?.shouldIgnorePageFlipInput ?? false) {
      if (_dragActive) {
        controller.cancelInteraction();
        _dragActive = false;
        _activeDragDirection = null;
        _activeDragCorner = null;
        _setTextureTransactionActive(false);
        _rebuild();
      }
      return;
    }
    if (_dragActive) {
      _applyFullSurfaceSwipe(controller, localPosition);
      _rebuild();
      return;
    }
    if (start == null) {
      return;
    }
    final dragDx = localPosition.dx - start.dx;
    if (dragDx.abs() < _MediaPageFlipBookState._swipeIntentDistance) {
      return;
    }
    final direction = dragDx < 0
        ? StPageFlipDirection.forward
        : StPageFlipDirection.back;
    if (!_gestureIntentAllowsDirection(intentController, intent, direction)) {
      return;
    }
    if (!controller.canFlipDirection(direction)) {
      if (intentController != null &&
          intent != ImmersiveGestureIntent.boundaryRubberBand) {
        return;
      }
      _pendingOverflowDirection = direction;
      _trackEdgeOverflow(delta, direction);
      return;
    }
    if (_reduceMotionEnabled) {
      if (_reducedMotionTurnCommitted ||
          dragDx.abs() < _MediaPageFlipBookState._reducedMotionCommitDistance) {
        return;
      }
      _setTextureTransactionActive(true);
      _commitReducedMotionPageTurn(controller, direction);
      _setTextureTransactionActive(false);
      return;
    }
    _beginFullSurfaceSwipe(controller, direction, localPosition);
  }

  void _endHorizontalDrag(double velocityDx) {
    final controller = _controller;
    if (controller == null) {
      widget.gestureIntentController?.finish();
      return;
    }
    var committed = false;
    if (_reducedMotionTurnCommitted) {
      committed = true;
      final direction = _activeDragDirection;
      if (direction != null) {
        _emitMotionEvent(
          direction: direction,
          motionProfile: 'reduced_motion',
          settleDuration: Duration.zero,
          reducedMotion: true,
          committed: true,
        );
      }
    } else if (_dragActive) {
      _dragActive = false;
      var plan = controller.stopMove();
      final direction = _activeDragDirection;
      final corner = _activeDragCorner ?? StPageFlipCorner.bottom;
      final releaseDecision = direction == null
          ? null
          : resolvePageflipReleaseDecision(
              isForwardDirection: direction == StPageFlipDirection.forward,
              progress: _pageFlipProgress(controller),
              pageWidth: controller.layout.bounds.pageWidth,
              velocityDx: velocityDx,
              dragStart: _dragStartLocalPosition,
              dragLatest: _latestDragLocalPosition,
              dragStartedAt: _dragStartedAt,
            );
      if (direction != null &&
          plan != null &&
          !plan.isTurned &&
          (releaseDecision?.commitsTurn ?? false)) {
        plan = switch (direction) {
          StPageFlipDirection.forward => controller.flipNext(
            corner,
            allowOutOfBoundsTap: false,
          ),
          StPageFlipDirection.back => controller.flipPrev(
            corner,
            allowOutOfBoundsTap: false,
          ),
        };
      }
      if (plan != null && releaseDecision != null) {
        plan = plan.copyWith(duration: releaseDecision.settleDuration);
      }
      committed = plan?.isTurned ?? false;
      if (plan != null) {
        _startAnimation(plan);
      } else {
        controller.cancelInteraction();
        _setTextureTransactionActive(false);
        _rebuild();
      }
      if (direction != null && releaseDecision != null) {
        _emitMotionEvent(
          direction: direction,
          motionProfile: 'comfort_curl',
          settleDuration: releaseDecision.settleDuration,
          reducedMotion: false,
          committed: committed,
        );
      }
    } else {
      final direction = _pendingOverflowDirection;
      if (!_overflowTriggered &&
          direction != null &&
          velocityDx.abs() >= _MediaPageFlipBookState._overflowSwitchVelocity &&
          _isEdgeOverflowStart(direction)) {
        _triggerOverflow(direction);
      }
    }
    widget.gestureIntentController?.finish(committed: committed);
    _dragStartLocalPosition = null;
    _latestDragLocalPosition = null;
    _dragStartedAt = null;
    _activeDragDirection = null;
    _activeDragCorner = null;
    _reducedMotionTurnCommitted = false;
    _resetOverflowTracking();
    _applyDeferredDirectTextureRefreshIfIdle();
  }

  void _cancelHorizontalDrag() {
    final shouldEmitCancel = _dragActive || _reducedMotionTurnCommitted;
    final cancelDirection = _activeDragDirection;
    final cancelReducedMotion =
        _reducedMotionTurnCommitted || _reduceMotionEnabled;
    if (_dragActive) {
      _controller?.cancelInteraction();
    }
    if (shouldEmitCancel && cancelDirection != null) {
      _emitMotionEvent(
        direction: cancelDirection,
        motionProfile: cancelReducedMotion ? 'reduced_motion' : 'comfort_curl',
        settleDuration: Duration.zero,
        reducedMotion: cancelReducedMotion,
        committed: false,
      );
    }
    widget.gestureIntentController?.cancel();
    _dragActive = false;
    _dragStartLocalPosition = null;
    _latestDragLocalPosition = null;
    _dragStartedAt = null;
    _activeDragDirection = null;
    _activeDragCorner = null;
    _reducedMotionTurnCommitted = false;
    _setTextureTransactionActive(false);
    _resetOverflowTracking();
    _applyDeferredDirectTextureRefreshIfIdle();
    _rebuild();
  }

  void _emitMotionEvent({
    required StPageFlipDirection direction,
    required String motionProfile,
    required Duration settleDuration,
    required bool reducedMotion,
    required bool committed,
  }) {
    widget.onMotionEvent?.call(
      MediaPageFlipMotionEvent(
        direction: direction,
        motionProfile: motionProfile,
        settleDuration: settleDuration,
        reducedMotion: reducedMotion,
        committed: committed,
      ),
    );
  }

  void _setTextureTransactionActive(bool active) {
    if (_textureTransactionActive == active) {
      return;
    }
    _textureTransactionActive = active;
    widget.onTextureTransactionActiveChanged?.call(active);
  }

  void _beginFullSurfaceSwipe(
    StPageFlipController controller,
    StPageFlipDirection direction,
    Offset currentLocalPosition,
  ) {
    final start = _dragStartLocalPosition;
    if (start == null) {
      return;
    }
    final corner = controller.cornerForGlobalPoint(start);
    final startPoint = _syntheticStartPoint(
      controller.layout,
      direction: direction,
      corner: corner,
      touchY: start.dy,
    );
    if (!controller.start(startPoint)) {
      return;
    }
    _dragActive = true;
    _setTextureTransactionActive(true);
    _activeDragDirection = direction;
    _activeDragCorner = corner;
    _applyFullSurfaceSwipe(controller, currentLocalPosition);
    _queueSceneTextureWindow(
      controller.scene,
      _textureBindingForScene(controller.scene),
    );
    _scheduleCapture();
    _rebuild();
  }

  void _applyFullSurfaceSwipe(
    StPageFlipController controller,
    Offset currentLocalPosition,
  ) {
    final start = _dragStartLocalPosition;
    final direction = _activeDragDirection;
    if (start == null || direction == null) {
      return;
    }
    controller.fold(currentLocalPosition);
    _queueSceneTextureWindow(
      controller.scene,
      _textureBindingForScene(controller.scene),
    );
    _scheduleCapture();
  }

  Offset _syntheticStartPoint(
    StPageFlipLayout layout, {
    required StPageFlipDirection direction,
    required StPageFlipCorner corner,
    required double touchY,
  }) {
    final bounds = layout.bounds;
    final y = _viewportYForTouch(bounds, touchY, corner: corner);
    final x = switch (direction) {
      StPageFlipDirection.forward =>
        bounds.left + bounds.width - AppSpacing.hairline,
      StPageFlipDirection.back => bounds.left + AppSpacing.hairline,
    };
    return Offset(x, y);
  }

  double _viewportYForTouch(
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

  double _pageFlipProgress(StPageFlipController controller) {
    return controller.scene.renderFrame?.progress ??
        ((controller.scene.calculation?.getFlippingProgress() ?? 0) / 100)
            .clamp(0.0, 1.0)
            .toDouble();
  }

  ImmersiveGestureIntent _pageFlipIntentForDirection(
    StPageFlipDirection direction,
  ) {
    return direction == StPageFlipDirection.forward
        ? ImmersiveGestureIntent.pageFlipForward
        : ImmersiveGestureIntent.pageFlipBack;
  }

  bool _gestureIntentAllowsDirection(
    ImmersiveGestureIntentController? controller,
    ImmersiveGestureIntent? intent,
    StPageFlipDirection direction,
  ) {
    if (controller == null || !controller.isTracking) {
      return true;
    }
    final expected = _pageFlipIntentForDirection(direction);
    return intent == expected ||
        intent == ImmersiveGestureIntent.boundaryRubberBand ||
        intent == ImmersiveGestureIntent.undecided ||
        intent == null;
  }

  ImmersiveGestureIntent? _currentGestureIntent(
    ImmersiveGestureIntentController? controller,
  ) {
    if (controller == null || !controller.isTracking) {
      return null;
    }
    if (controller.lockedIntent != ImmersiveGestureIntent.undecided) {
      return controller.lockedIntent;
    }
    return controller.previewIntent;
  }

  bool get _reduceMotionEnabled {
    final mediaQuery = mounted ? MediaQuery.maybeOf(context) : null;
    return mediaQuery?.disableAnimations ??
        WidgetsBinding
            .instance
            .platformDispatcher
            .accessibilityFeatures
            .disableAnimations;
  }

  void _commitReducedMotionPageTurn(
    StPageFlipController controller,
    StPageFlipDirection direction,
  ) {
    final nextPage = switch (direction) {
      StPageFlipDirection.forward => _currentPage + 1,
      StPageFlipDirection.back => _currentPage - 1,
    };
    if (nextPage < 0 || nextPage >= widget.pageCount) {
      return;
    }
    _reducedMotionTurnCommitted = true;
    _dragActive = false;
    _activeDragDirection = direction;
    _activeDragCorner = null;
    _currentPage = nextPage;
    controller.setCurrentPage(_currentPage);
    widget.onPageChanged?.call(_currentPage);
    _queueStaticTextureSnapshots();
    _applyDeferredDirectTextureRefreshIfIdle();
    _rebuild();
  }

  bool _isEdgeOverflowStart(StPageFlipDirection direction) {
    final start = _dragStartLocalPosition;
    final stage = _lastStageSize;
    if (start == null || stage == null) {
      return false;
    }
    return switch (direction) {
      StPageFlipDirection.back =>
        widget.onOverflowPrevious != null &&
            start.dx <= _MediaPageFlipBookState._overflowEdgeStartInset,
      StPageFlipDirection.forward =>
        widget.onOverflowNext != null &&
            start.dx >=
                stage.width - _MediaPageFlipBookState._overflowEdgeStartInset,
    };
  }

  void _trackEdgeOverflow(Offset delta, StPageFlipDirection direction) {
    if (!_isEdgeOverflowStart(direction)) {
      _edgeOverflowDistance = 0;
      return;
    }
    if (_pendingOverflowDirection != direction) {
      _pendingOverflowDirection = direction;
      _edgeOverflowDistance = 0;
    }
    _edgeOverflowDistance += delta.dx.abs();
    if (_edgeOverflowDistance >=
        _MediaPageFlipBookState._overflowSwitchDistance) {
      _triggerOverflow(direction);
    }
  }

  void _triggerOverflow(StPageFlipDirection direction) {
    if (_overflowTriggered) {
      return;
    }
    final callback = switch (direction) {
      StPageFlipDirection.back => widget.onOverflowPrevious,
      StPageFlipDirection.forward => widget.onOverflowNext,
    };
    if (callback == null) {
      return;
    }
    _overflowTriggered = true;
    callback();
  }

  void _resetOverflowTracking() {
    _edgeOverflowDistance = 0;
    _pendingOverflowDirection = null;
    _overflowTriggered = false;
  }

  void _startAnimation(StPageFlipAnimationPlan plan) {
    if (plan.frames.isEmpty) {
      _completeAnimation(plan);
      return;
    }
    _activePlan = plan;
    _lastAnimationFrameIndex = -1;
    _animationController.duration = plan.duration;
    _animationController.forward(from: 0);
  }

  void _handleAnimationTick() {
    final plan = _activePlan;
    final controller = _controller;
    if (plan == null || controller == null || plan.frames.isEmpty) {
      return;
    }
    final maxIndex = plan.frames.length - 1;
    final nextIndex = maxIndex == 0
        ? 0
        : (_animationController.value * maxIndex).round().clamp(0, maxIndex);
    if (nextIndex == _lastAnimationFrameIndex) {
      return;
    }
    _lastAnimationFrameIndex = nextIndex;
    controller.applyAnimationFrame(
      plan.frames[nextIndex],
      reversePose: plan.reversePoses == null
          ? null
          : plan.reversePoses![nextIndex.clamp(
              0,
              plan.reversePoses!.length - 1,
            )],
    );
    _rebuild();
  }

  void _handleAnimationStatus(AnimationStatus status) {
    final plan = _activePlan;
    if (status != AnimationStatus.completed || plan == null) {
      return;
    }
    _completeAnimation(plan);
  }

  void _completeAnimation(StPageFlipAnimationPlan plan) {
    final controller = _controller;
    if (controller == null) {
      _activePlan = null;
      _setTextureTransactionActive(false);
      return;
    }
    final lastFrameIndex = plan.frames.length - 1;
    if (lastFrameIndex >= 0 && _lastAnimationFrameIndex != lastFrameIndex) {
      controller.applyAnimationFrame(
        plan.frames[lastFrameIndex],
        reversePose: plan.reversePoses == null
            ? null
            : plan.reversePoses![lastFrameIndex.clamp(
                0,
                plan.reversePoses!.length - 1,
              )],
      );
      _lastAnimationFrameIndex = lastFrameIndex;
    }
    controller.completeAnimation(plan);
    final nextPage = controller.currentPageIndex;
    final changed = nextPage != _currentPage;
    _currentPage = nextPage;
    _activePlan = null;
    _lastAnimationFrameIndex = -1;
    if (changed) {
      widget.onPageChanged?.call(_currentPage);
    }
    _setTextureTransactionActive(false);
    _queueStaticTextureSnapshots();
    _applyDeferredDirectTextureRefreshIfIdle();
    _rebuild();
  }
}
