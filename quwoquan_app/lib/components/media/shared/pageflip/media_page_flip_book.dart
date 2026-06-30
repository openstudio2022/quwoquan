import 'dart:async';
import 'dart:collection';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:quwoquan_app/components/pageflip/book_layout.dart';
import 'package:quwoquan_app/components/pageflip/controller.dart';
import 'package:quwoquan_app/components/pageflip/geometry.dart';
import 'package:quwoquan_app/components/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/components/pageflip/spread_model.dart';
import 'package:quwoquan_app/components/pageflip/types.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

typedef MediaPageFlipPageBuilder =
    Widget Function(BuildContext context, int pageIndex);
typedef MediaPageFlipTextureReadyPredicate = bool Function(int pageIndex);
typedef MediaPageFlipTextureSnapshot = ArticlePageTextureSnapshot;
typedef MediaPageFlipTextureSnapshotBuilder =
    Future<MediaPageFlipTexturePair?> Function(
      BuildContext context,
      int pageIndex,
      Size pageSize,
      double pixelRatio,
    );

enum MediaPageFlipSurfaceFace { front, back }

@immutable
class MediaPageFlipTexturePair {
  const MediaPageFlipTexturePair({required this.front, required this.back});

  final MediaPageFlipTextureSnapshot front;
  final MediaPageFlipTextureSnapshot back;

  bool matchesLogicalSize(Size expected) {
    return front.matchesLogicalSize(expected) &&
        back.matchesLogicalSize(expected);
  }

  void dispose() {
    front.dispose();
    back.dispose();
  }
}

MediaPageFlipTextureSnapshot createMediaPageFlipTextureSnapshot({
  required ui.Image image,
  required Size logicalSize,
  required double pixelRatio,
  String? semanticSurfaceKind,
}) {
  return ArticlePageTextureSnapshot(
    image: image,
    logicalSize: logicalSize,
    pixelRatio: pixelRatio,
    semanticSurfaceKind: semanticSurfaceKind,
  );
}

@immutable
class _MediaPageTextureKey {
  const _MediaPageTextureKey(this.pageIndex, this.face);

  final int pageIndex;
  final MediaPageFlipSurfaceFace face;

  @override
  bool operator ==(Object other) {
    return other is _MediaPageTextureKey &&
        other.pageIndex == pageIndex &&
        other.face == face;
  }

  @override
  int get hashCode => Object.hash(pageIndex, face);
}

@immutable
class _MediaPageTextureRef {
  const _MediaPageTextureRef({required this.pageIndex, required this.face});

  final int pageIndex;
  final MediaPageFlipSurfaceFace face;
}

@immutable
class _MediaPageTextureBinding {
  const _MediaPageTextureBinding({
    required this.direction,
    required this.recto,
    required this.verso,
    required this.bottom,
  });

  final StPageFlipDirection direction;
  final _MediaPageTextureRef recto;
  final _MediaPageTextureRef verso;
  final _MediaPageTextureRef bottom;

  List<int> get prioritizedPageIndices {
    final indices = <int>[];
    void addUnique(int index) {
      if (!indices.contains(index)) {
        indices.add(index);
      }
    }

    addUnique(recto.pageIndex);
    addUnique(verso.pageIndex);
    addUnique(bottom.pageIndex);
    return indices;
  }

  Set<int> get requiredPageIndices => <int>{
    recto.pageIndex,
    verso.pageIndex,
    bottom.pageIndex,
  };
}

/// 媒体通用翻书宿主。
///
/// 仅负责 pageflip 几何、纹理捕获与页切换事件，不承载 discovery/content
/// 业务模型、provider、导航或埋点。
class MediaPageFlipBook extends StatefulWidget {
  const MediaPageFlipBook({
    super.key,
    required this.pageCount,
    required this.pageBuilder,
    this.initialPage = 0,
    this.stageColor = AppColors.worksBackground,
    this.pageAspectRatio,
    this.pagePadding = EdgeInsets.zero,
    this.contentSignature,
    this.textureReadinessSignature,
    this.isPageTextureReady,
    this.textureSnapshotBuilder,
    this.onPageChanged,
    this.onOverflowPrevious,
    this.onOverflowNext,
  });

  final int pageCount;
  final int initialPage;
  final MediaPageFlipPageBuilder pageBuilder;
  final Color stageColor;
  final double? pageAspectRatio;
  final EdgeInsets pagePadding;
  final Object? contentSignature;
  final Object? textureReadinessSignature;
  final MediaPageFlipTextureReadyPredicate? isPageTextureReady;
  final MediaPageFlipTextureSnapshotBuilder? textureSnapshotBuilder;
  final ValueChanged<int>? onPageChanged;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  State<MediaPageFlipBook> createState() => _MediaPageFlipBookState();
}

class _MediaPageFlipBookState extends State<MediaPageFlipBook>
    with SingleTickerProviderStateMixin {
  static const double _overflowSwitchVelocity = 320;
  static const double _overflowSwitchDistance = AppSpacing.buttonHeight;
  static const double _overflowEdgeStartInset =
      AppSpacing.minInteractiveSize / 2;
  static const double _swipeIntentDistance = AppSpacing.sm;
  static const double _swipeCommitDistance = AppSpacing.buttonHeight;
  static const double _swipeToPageTravelFactor = 2.4;

  final Map<int, GlobalKey> _captureBoundaryKeys = <int, GlobalKey>{};
  final Map<_MediaPageTextureKey, ArticlePageTextureSnapshot> _pageSnapshots =
      <_MediaPageTextureKey, ArticlePageTextureSnapshot>{};
  final List<ArticlePageTextureSnapshot> _retiredSnapshots =
      <ArticlePageTextureSnapshot>[];
  final ListQueue<int> _pendingCaptureIndices = ListQueue<int>();

  late final AnimationController _animationController;

  StPageFlipController? _controller;
  StPageFlipAnimationPlan? _activePlan;
  Size? _lastStageSize;
  Size? _lastPageSize;
  Offset? _dragStartLocalPosition;
  StPageFlipDirection? _activeDragDirection;
  StPageFlipCorner? _activeDragCorner;
  StPageFlipDirection? _pendingOverflowDirection;
  double _edgeOverflowDistance = 0;
  double _activeDragTravel = 0;
  bool _dragActive = false;
  bool _overflowTriggered = false;
  bool _captureScheduled = false;
  bool _captureInFlight = false;
  int _viewportCaptureGeneration = 0;
  int _lastAnimationFrameIndex = -1;
  late int _currentPage;

  int get _safeInitialPage {
    if (widget.pageCount <= 0) {
      return 0;
    }
    return widget.initialPage.clamp(0, widget.pageCount - 1).toInt();
  }

  @override
  void initState() {
    super.initState();
    _currentPage = _safeInitialPage;
    _animationController =
        AnimationController(
            vsync: this,
            duration: const Duration(milliseconds: 260),
          )
          ..addListener(_handleAnimationTick)
          ..addStatusListener(_handleAnimationStatus);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        widget.onPageChanged?.call(_currentPage);
      }
    });
  }

  @override
  void didUpdateWidget(covariant MediaPageFlipBook oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.pageCount != oldWidget.pageCount ||
        widget.contentSignature != oldWidget.contentSignature ||
        widget.pageAspectRatio != oldWidget.pageAspectRatio ||
        widget.pagePadding != oldWidget.pagePadding ||
        widget.stageColor != oldWidget.stageColor) {
      _clearAllSnapshots();
      _controller = null;
      _lastStageSize = null;
      _lastPageSize = null;
      _viewportCaptureGeneration += 1;
    }
    final nextInitialPage = _safeInitialPage;
    if (widget.initialPage != oldWidget.initialPage &&
        nextInitialPage != _currentPage) {
      _currentPage = nextInitialPage;
      _controller?.setCurrentPage(_currentPage);
    } else if (_currentPage >= widget.pageCount && widget.pageCount > 0) {
      _currentPage = widget.pageCount - 1;
      _controller?.setCurrentPage(_currentPage);
    }
    if (widget.textureReadinessSignature !=
        oldWidget.textureReadinessSignature) {
      if (widget.textureSnapshotBuilder != null) {
        _clearAllSnapshots();
        _queueStaticTextureSnapshots();
      } else if (_pendingCaptureIndices.isNotEmpty) {
        _scheduleCapture();
      }
    }
  }

  @override
  void dispose() {
    _animationController.dispose();
    _clearAllSnapshots();
    _disposeRetiredSnapshots();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.pageCount <= 0) {
      return ColoredBox(color: widget.stageColor);
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final stageSize = Size(
          constraints.maxWidth.isFinite && constraints.maxWidth > 0
              ? constraints.maxWidth
              : MediaQuery.sizeOf(context).width,
          constraints.maxHeight.isFinite && constraints.maxHeight > 0
              ? constraints.maxHeight
              : MediaQuery.sizeOf(context).height,
        );
        if (stageSize.width <= 0 || stageSize.height <= 0) {
          return ColoredBox(color: widget.stageColor);
        }
        final pageSize = _resolvePageSize(stageSize);
        _configureController(stageSize: stageSize, pageSize: pageSize);
        final controller = _controller;
        if (controller == null) {
          return ColoredBox(color: widget.stageColor);
        }
        if (_pageSnapshots.isEmpty && _pendingCaptureIndices.isEmpty) {
          _queueStaticTextureSnapshots();
        }
        final scene = controller.scene;
        final pageRect = resolveBookPageRect(scene.layout, isRightPage: true);
        final shouldCaptureTextures = _shouldCaptureTexturesForScene(scene);
        final textureBinding = shouldCaptureTextures
            ? _textureBindingForScene(scene)
            : null;
        if (shouldCaptureTextures) {
          _queueSceneTextureWindow(scene, textureBinding);
        }
        final dynamicLayers = _buildDynamicLayers(
          context,
          scene,
          pageRect: pageRect,
        );
        if (shouldCaptureTextures && _pendingCaptureIndices.isNotEmpty) {
          _scheduleCapture();
        }
        return ColoredBox(
          color: widget.stageColor,
          child: Stack(
            fit: StackFit.expand,
            children: [
              _buildStaticPage(context, pageRect, scene.currentPageIndex),
              ...dynamicLayers,
              Positioned.fill(child: _buildGestureLayer(pageRect)),
              if (_pendingCaptureIndices.isNotEmpty)
                if (widget.textureSnapshotBuilder == null)
                  Positioned.fill(
                    child: IgnorePointer(
                      child: _buildCaptureLayer(context, pageSize, stageSize),
                    ),
                  ),
            ],
          ),
        );
      },
    );
  }

  Size _resolvePageSize(Size stageSize) {
    final availableWidth = math.max(
      1.0,
      stageSize.width - widget.pagePadding.horizontal,
    );
    final availableHeight = math.max(
      1.0,
      stageSize.height - widget.pagePadding.vertical,
    );
    final ratio = widget.pageAspectRatio;
    if (ratio == null || ratio <= 0) {
      return Size(availableWidth, availableHeight);
    }
    var width = availableWidth;
    var height = width / ratio;
    if (height > availableHeight) {
      height = availableHeight;
      width = height * ratio;
    }
    return Size(width, height);
  }

  void _configureController({required Size stageSize, required Size pageSize}) {
    if (_sizeEquals(_lastStageSize, stageSize) &&
        _sizeEquals(_lastPageSize, pageSize) &&
        _controller != null) {
      return;
    }
    final hadViewport = _lastStageSize != null && _lastPageSize != null;
    _lastStageSize = stageSize;
    _lastPageSize = pageSize;
    if (hadViewport) {
      _viewportCaptureGeneration += 1;
      _clearAllSnapshots();
    }
    final layout = computeStPageFlipLayout(
      viewportSize: stageSize,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
      usePortrait: true,
    );
    final spreadModel = StPageFlipSpreadModel(
      pageCount: widget.pageCount,
      showCover: false,
      hardPagePolicy: StPageFlipHardPagePolicy.none,
    );
    if (_controller == null) {
      _controller = StPageFlipController(
        spreadModel: spreadModel,
        layout: layout,
        initialPage: _currentPage,
      );
      return;
    }
    _controller!.updateConfiguration(
      spreadModel: spreadModel,
      layout: layout,
      currentPage: _currentPage,
    );
  }

  Widget _buildGestureLayer(Rect pageRect) {
    return GestureDetector(
      key: const ValueKey('media-pageflip-gesture-layer'),
      behavior: HitTestBehavior.translucent,
      onHorizontalDragStart: _handleHorizontalDragStart,
      onHorizontalDragUpdate: _handleHorizontalDragUpdate,
      onHorizontalDragEnd: _handleHorizontalDragEnd,
      onHorizontalDragCancel: _handleHorizontalDragCancel,
      child: const SizedBox.expand(),
    );
  }

  Widget _buildStaticPage(BuildContext context, Rect pageRect, int pageIndex) {
    return Positioned.fromRect(
      rect: pageRect,
      child: KeyedSubtree(
        key: ValueKey<String>('media-pageflip-static-page-$pageIndex'),
        child: widget.pageBuilder(context, pageIndex),
      ),
    );
  }

  Widget _buildCaptureLayer(
    BuildContext context,
    Size pageSize,
    Size stageSize,
  ) {
    final pages = _pendingCaptureIndices.take(3).toList(growable: false);
    if (pages.isEmpty) {
      return const SizedBox.shrink();
    }
    return Transform.translate(
      offset: Offset(
        stageSize.width + pageSize.width + AppSpacing.buttonHeight,
        0,
      ),
      child: _StableMediaPageCaptureLayer(
        capturePages: pages,
        pageSize: pageSize,
        boundaryKeys: _captureBoundaryKeys,
        buildPage: (index) => widget.pageBuilder(context, index),
      ),
    );
  }

  void _handleHorizontalDragStart(DragStartDetails details) {
    final controller = _controller;
    if (controller == null || _activePlan != null) {
      return;
    }
    _dragStartLocalPosition = details.localPosition;
    _activeDragDirection = null;
    _activeDragCorner = null;
    _activeDragTravel = 0;
    _dragActive = false;
    _resetOverflowTracking();
  }

  void _handleHorizontalDragUpdate(DragUpdateDetails details) {
    final controller = _controller;
    if (controller == null) {
      return;
    }
    if (_dragActive) {
      _applyFullSurfaceSwipe(controller, details.localPosition);
      setState(() {});
      return;
    }
    final start = _dragStartLocalPosition;
    if (start == null) {
      return;
    }
    final dragDx = details.localPosition.dx - start.dx;
    if (dragDx.abs() < _swipeIntentDistance) {
      return;
    }
    final direction = dragDx < 0
        ? StPageFlipDirection.forward
        : StPageFlipDirection.back;
    if (!controller.canFlipDirection(direction)) {
      _pendingOverflowDirection = direction;
      _trackEdgeOverflow(details, direction);
      return;
    }
    _beginFullSurfaceSwipe(controller, direction, details.localPosition);
  }

  void _handleHorizontalDragEnd(DragEndDetails details) {
    final controller = _controller;
    if (controller == null) {
      return;
    }
    if (_dragActive) {
      _dragActive = false;
      var plan = controller.stopMove();
      final direction = _activeDragDirection;
      final corner = _activeDragCorner ?? StPageFlipCorner.bottom;
      if (direction != null &&
          plan != null &&
          !plan.isTurned &&
          _shouldCommitSwipe(direction, details.primaryVelocity ?? 0)) {
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
      if (plan != null) {
        _startAnimation(plan);
      } else {
        controller.cancelInteraction();
        setState(() {});
      }
    } else {
      final velocity = details.primaryVelocity ?? 0;
      final direction = _pendingOverflowDirection;
      if (!_overflowTriggered &&
          direction != null &&
          velocity.abs() >= _overflowSwitchVelocity &&
          _isEdgeOverflowStart(direction)) {
        _triggerOverflow(direction);
      }
    }
    _dragStartLocalPosition = null;
    _activeDragDirection = null;
    _activeDragCorner = null;
    _activeDragTravel = 0;
    _resetOverflowTracking();
  }

  void _handleHorizontalDragCancel() {
    if (_dragActive) {
      _controller?.cancelInteraction();
    }
    _dragActive = false;
    _dragStartLocalPosition = null;
    _activeDragDirection = null;
    _activeDragCorner = null;
    _activeDragTravel = 0;
    _resetOverflowTracking();
    if (mounted) {
      setState(() {});
    }
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
    _activeDragDirection = direction;
    _activeDragCorner = corner;
    _applyFullSurfaceSwipe(controller, currentLocalPosition);
    _queueSceneTextureWindow(
      controller.scene,
      _textureBindingForScene(controller.scene),
    );
    _scheduleCapture();
    setState(() {});
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
    final dragDx = currentLocalPosition.dx - start.dx;
    _activeDragTravel = switch (direction) {
      StPageFlipDirection.forward => math.max(0, -dragDx),
      StPageFlipDirection.back => math.max(0, dragDx),
    };
    final foldPoint = _syntheticFoldPoint(
      controller.layout,
      direction: direction,
      touchY: currentLocalPosition.dy,
      travel: _activeDragTravel,
    );
    controller.fold(foldPoint);
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

  Offset _syntheticFoldPoint(
    StPageFlipLayout layout, {
    required StPageFlipDirection direction,
    required double touchY,
    required double travel,
  }) {
    final bounds = layout.bounds;
    final pageWidth = bounds.pageWidth;
    final pageTravel = (travel * _swipeToPageTravelFactor).clamp(
      0.0,
      pageWidth * 2,
    );
    final localX = switch (direction) {
      StPageFlipDirection.forward =>
        (pageWidth - pageTravel).clamp(-pageWidth, pageWidth).toDouble(),
      StPageFlipDirection.back =>
        (-pageTravel).clamp(-pageWidth, 0.0).toDouble(),
    };
    final localY = (touchY - bounds.top)
        .clamp(AppSpacing.hairline, bounds.height - AppSpacing.hairline)
        .toDouble();
    return convertBookPointToViewport(
      Offset(localX, localY),
      bounds,
      direction: direction,
    );
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

  bool _shouldCommitSwipe(StPageFlipDirection direction, double velocity) {
    final velocityCommits = switch (direction) {
      StPageFlipDirection.forward => velocity <= -_overflowSwitchVelocity,
      StPageFlipDirection.back => velocity >= _overflowSwitchVelocity,
    };
    return _activeDragTravel >= _swipeCommitDistance || velocityCommits;
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
            start.dx <= _overflowEdgeStartInset,
      StPageFlipDirection.forward =>
        widget.onOverflowNext != null &&
            start.dx >= stage.width - _overflowEdgeStartInset,
    };
  }

  void _trackEdgeOverflow(
    DragUpdateDetails details,
    StPageFlipDirection direction,
  ) {
    if (!_isEdgeOverflowStart(direction)) {
      _edgeOverflowDistance = 0;
      return;
    }
    if (_pendingOverflowDirection != direction) {
      _pendingOverflowDirection = direction;
      _edgeOverflowDistance = 0;
    }
    _edgeOverflowDistance += details.delta.dx.abs();
    if (_edgeOverflowDistance >= _overflowSwitchDistance) {
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
    final frameIndex = (_animationController.value * (plan.frames.length - 1))
        .round()
        .clamp(0, plan.frames.length - 1)
        .toInt();
    if (frameIndex == _lastAnimationFrameIndex) {
      return;
    }
    _lastAnimationFrameIndex = frameIndex;
    controller.applyAnimationFrame(
      plan.frames[frameIndex],
      reversePose: plan.reversePoses == null
          ? null
          : plan.reversePoses![frameIndex.clamp(
              0,
              plan.reversePoses!.length - 1,
            )],
    );
    if (mounted) {
      setState(() {});
    }
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
      return;
    }
    controller.completeAnimation(plan);
    final nextPage = controller.currentPageIndex;
    final changed = nextPage != _currentPage;
    _currentPage = nextPage;
    _activePlan = null;
    if (changed) {
      widget.onPageChanged?.call(_currentPage);
    }
    _queueStaticTextureSnapshots();
    if (mounted) {
      setState(() {});
    }
  }

  _MediaPageTextureBinding? _textureBindingForScene(StPageFlipScene scene) {
    final direction = scene.effectiveRenderDirection ?? scene.direction;
    if (direction == null || scene.flippingPageIndex == null) {
      return null;
    }
    if (direction == StPageFlipDirection.forward) {
      final targetPageIndex = scene.bottomPageIndex;
      if (targetPageIndex == null) {
        return null;
      }
      return _MediaPageTextureBinding(
        direction: direction,
        recto: _MediaPageTextureRef(
          pageIndex: scene.currentPageIndex,
          face: MediaPageFlipSurfaceFace.front,
        ),
        verso: _MediaPageTextureRef(
          pageIndex: targetPageIndex,
          face: MediaPageFlipSurfaceFace.back,
        ),
        bottom: _MediaPageTextureRef(
          pageIndex: targetPageIndex,
          face: MediaPageFlipSurfaceFace.front,
        ),
      );
    }
    return _MediaPageTextureBinding(
      direction: direction,
      recto: _MediaPageTextureRef(
        pageIndex: scene.flippingPageIndex!,
        face: MediaPageFlipSurfaceFace.front,
      ),
      verso: _MediaPageTextureRef(
        pageIndex: scene.flippingPageIndex!,
        face: MediaPageFlipSurfaceFace.back,
      ),
      bottom: _MediaPageTextureRef(
        pageIndex: scene.currentPageIndex,
        face: MediaPageFlipSurfaceFace.front,
      ),
    );
  }

  bool _shouldCaptureTexturesForScene(StPageFlipScene scene) {
    return scene.renderFrame != null || _activePlan != null || _dragActive;
  }

  List<Widget> _buildDynamicLayers(
    BuildContext context,
    StPageFlipScene scene, {
    required Rect pageRect,
  }) {
    final renderFrame = scene.renderFrame;
    if (renderFrame == null) {
      return const <Widget>[];
    }
    final binding = _textureBindingForScene(scene);
    final bundle = _textureBundleForScene(scene, binding);
    if (binding == null || bundle == null) {
      return const <Widget>[];
    }
    final pageSize = Size(
      scene.layout.bounds.pageWidth,
      scene.layout.bounds.height,
    );
    final direction = renderFrame.renderDirection;
    if (direction == StPageFlipDirection.forward) {
      return <Widget>[
        if (renderFrame.bottomClipArea.length >= 3)
          _buildDynamicPageLayer(
            key: const ValueKey<String>('media-pageflip-bottom-layer'),
            transformKey: const ValueKey<String>(
              'media-pageflip-bottom-transform',
            ),
            textureRef: binding.bottom,
            pageSize: pageSize,
            area: renderFrame.bottomClipArea,
            anchor: renderFrame.bottomAnchor,
            angle: 0,
            direction: StPageFlipDirection.forward,
            visualGeometryDirection: renderFrame.visualGeometryDirection,
            bounds: scene.layout.bounds,
            isFlippingPage: false,
            progress: renderFrame.progress,
          ),
        if (renderFrame.flippingClipArea.length >= 3)
          _buildDynamicPageLayer(
            key: const ValueKey<String>('media-pageflip-flipping-layer'),
            transformKey: const ValueKey<String>(
              'media-pageflip-flipping-transform',
            ),
            textureRef: binding.verso,
            pageSize: pageSize,
            area: renderFrame.flippingClipArea,
            anchor: renderFrame.flippingAnchor,
            angle: renderFrame.angle,
            direction: StPageFlipDirection.forward,
            visualGeometryDirection: renderFrame.visualGeometryDirection,
            bounds: scene.layout.bounds,
            isFlippingPage: true,
            progress: renderFrame.progress,
          ),
      ];
    }

    return <Widget>[
      Positioned.fromRect(
        key: const ValueKey<String>('media-pageflip-backward-front-layer'),
        rect: pageRect,
        child: _buildTextureSurface(binding.recto),
      ),
      if (renderFrame.bottomClipArea.length >= 3)
        _buildDynamicPageLayer(
          key: const ValueKey<String>('media-pageflip-bottom-layer'),
          transformKey: const ValueKey<String>(
            'media-pageflip-bottom-transform',
          ),
          textureRef: binding.bottom,
          pageSize: pageSize,
          area: renderFrame.bottomClipArea,
          anchor: renderFrame.bottomAnchor,
          angle: 0,
          direction: StPageFlipDirection.back,
          visualGeometryDirection: renderFrame.visualGeometryDirection,
          bounds: scene.layout.bounds,
          isFlippingPage: false,
          progress: renderFrame.progress,
        ),
      if (renderFrame.flippingClipArea.length >= 3)
        _buildDynamicPageLayer(
          key: const ValueKey<String>('media-pageflip-flipping-layer'),
          transformKey: const ValueKey<String>(
            'media-pageflip-flipping-transform',
          ),
          textureRef: binding.verso,
          pageSize: pageSize,
          area: renderFrame.flippingClipArea,
          anchor: renderFrame.flippingAnchor,
          angle: renderFrame.angle,
          direction: StPageFlipDirection.back,
          visualGeometryDirection: renderFrame.visualGeometryDirection,
          bounds: scene.layout.bounds,
          isFlippingPage: true,
          progress: renderFrame.progress,
        ),
    ];
  }

  Widget _buildDynamicPageLayer({
    required Key key,
    required Key transformKey,
    required _MediaPageTextureRef textureRef,
    required Size pageSize,
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
    required StPageFlipDirection visualGeometryDirection,
    required StPageFlipBoundsRect bounds,
    required bool isFlippingPage,
    required double progress,
  }) {
    final geometryDirection = visualGeometryDirection;
    final layerOrigin = anchor;
    final localPolygon = _localPolygonFromArea(
      area: area,
      anchor: layerOrigin,
      angle: angle,
      direction: geometryDirection,
    );
    if (localPolygon.length < 3) {
      return const SizedBox.shrink();
    }
    final position = convertBookPointToViewport(
      layerOrigin,
      bounds,
      direction: geometryDirection,
    );
    final paintBounds = isFlippingPage
        ? _softLayerPaintBounds(pageSize: pageSize, polygon: localPolygon)
        : Offset.zero & pageSize;
    final paintOrigin = paintBounds.topLeft;
    final positionedOffset =
        position + _rotatePointForCanvasTransform(paintOrigin, angle);
    final shiftedPolygon = paintOrigin == Offset.zero
        ? localPolygon
        : localPolygon
              .map((point) => point - paintOrigin)
              .toList(growable: false);
    return Positioned(
      key: key,
      left: positionedOffset.dx,
      top: positionedOffset.dy,
      width: paintBounds.width,
      height: paintBounds.height,
      child: Transform.rotate(
        key: transformKey,
        angle: angle,
        alignment: Alignment.topLeft,
        child: ClipPath(
          clipper: _MediaPagePolygonClipper(shiftedPolygon),
          child: Transform.translate(
            offset: -paintOrigin,
            child: SizedBox(
              width: pageSize.width,
              height: pageSize.height,
              child: Stack(
                fit: StackFit.expand,
                children: <Widget>[
                  _buildTextureSurface(textureRef),
                  _buildDynamicSurfaceOverlay(
                    direction: direction,
                    isBackFace:
                        textureRef.face == MediaPageFlipSurfaceFace.back,
                    isFlippingPage: isFlippingPage,
                    progress: progress,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTextureSurface(_MediaPageTextureRef ref) {
    final key = _MediaPageTextureKey(ref.pageIndex, ref.face);
    var snapshot = _pageSnapshots[key];
    if (snapshot == null &&
        widget.textureSnapshotBuilder == null &&
        ref.face == MediaPageFlipSurfaceFace.back) {
      snapshot =
          _pageSnapshots[_MediaPageTextureKey(
            ref.pageIndex,
            MediaPageFlipSurfaceFace.front,
          )];
    }
    if (snapshot == null) {
      return ColoredBox(color: widget.stageColor);
    }
    return KeyedSubtree(
      key: ValueKey<String>(
        'media-pageflip-surface-${ref.pageIndex}-${ref.face.name}',
      ),
      child: RawImage(
        image: snapshot.image,
        fit: BoxFit.fill,
        filterQuality: FilterQuality.medium,
      ),
    );
  }

  Widget _buildDynamicSurfaceOverlay({
    required StPageFlipDirection direction,
    required bool isBackFace,
    required bool isFlippingPage,
    required double progress,
  }) {
    final settledProgress = progress.clamp(0.0, 1.0).toDouble();
    final lift = Curves.easeOutCubic.transform(settledProgress);
    final edgeAlignment = direction == StPageFlipDirection.forward
        ? Alignment.centerRight
        : Alignment.centerLeft;
    final oppositeEdge = direction == StPageFlipDirection.forward
        ? Alignment.centerLeft
        : Alignment.centerRight;
    final edgeShadow = AppColors.black.withValues(
      alpha: (isBackFace ? 0.11 : 0.10) + lift * 0.05,
    );
    final paperHighlight = AppColors.white.withValues(
      alpha: (isBackFace ? 0.055 : 0.10) + lift * 0.025,
    );
    return IgnorePointer(
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          if (isBackFace)
            ColoredBox(color: AppColors.black.withValues(alpha: 0.025)),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: edgeAlignment,
                end: oppositeEdge,
                colors: <Color>[
                  edgeShadow,
                  AppColors.black.withValues(
                    alpha: isFlippingPage ? 0.05 : 0.03,
                  ),
                  AppColors.transparent,
                ],
                stops: const <double>[0.0, 0.32, 1.0],
              ),
            ),
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  paperHighlight,
                  AppColors.transparent,
                  AppColors.black.withValues(
                    alpha: (isBackFace ? 0.06 : 0.12) + lift * 0.035,
                  ),
                ],
                stops: const <double>[0.0, 0.5, 1.0],
              ),
            ),
          ),
          Align(
            alignment: edgeAlignment,
            child: FractionallySizedBox(
              widthFactor: (isBackFace ? 0.16 : 0.08) + lift * 0.04,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: edgeAlignment,
                    end: oppositeEdge,
                    colors: <Color>[
                      AppColors.white.withValues(
                        alpha: isBackFace ? 0.055 : 0.12,
                      ),
                      AppColors.transparent,
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  List<Offset> _localPolygonFromArea({
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
  }) {
    return area
        .map((point) {
          final translated = direction == StPageFlipDirection.back
              ? Offset(anchor.dx - point.dx, point.dy - anchor.dy)
              : Offset(point.dx - anchor.dx, point.dy - anchor.dy);
          return rotatePoint(translated, Offset.zero, angle);
        })
        .toList(growable: false);
  }

  Rect _softLayerPaintBounds({
    required Size pageSize,
    required List<Offset> polygon,
  }) {
    final bounds = _polygonBounds(polygon);
    if (bounds == null) {
      return Offset.zero & pageSize;
    }
    return Rect.fromLTRB(
      math.min(0.0, bounds.left),
      math.min(0.0, bounds.top),
      math.max(pageSize.width, bounds.right),
      math.max(pageSize.height, bounds.bottom),
    );
  }

  Rect? _polygonBounds(List<Offset> polygon) {
    if (polygon.isEmpty) {
      return null;
    }
    var left = polygon.first.dx;
    var top = polygon.first.dy;
    var right = left;
    var bottom = top;
    for (final point in polygon.skip(1)) {
      left = math.min(left, point.dx);
      top = math.min(top, point.dy);
      right = math.max(right, point.dx);
      bottom = math.max(bottom, point.dy);
    }
    return Rect.fromLTRB(left, top, right, bottom);
  }

  Offset _rotatePointForCanvasTransform(Offset point, double angle) {
    final sinAngle = math.sin(angle);
    final cosAngle = math.cos(angle);
    return Offset(
      point.dx * cosAngle - point.dy * sinAngle,
      point.dx * sinAngle + point.dy * cosAngle,
    );
  }

  ArticlePageTextureBundle? _textureBundleForScene(
    StPageFlipScene scene,
    _MediaPageTextureBinding? binding,
  ) {
    if (binding == null) {
      return null;
    }
    final pageSize = Size(
      scene.layout.bounds.pageWidth,
      scene.layout.bounds.height,
    );
    final recto = _validSnapshotForRef(binding.recto, expectedSize: pageSize);
    final verso = _validSnapshotForRef(binding.verso, expectedSize: pageSize);
    final bottom = _validSnapshotForRef(binding.bottom, expectedSize: pageSize);
    if (recto == null || verso == null || bottom == null) {
      return null;
    }
    return ArticlePageTextureBundle(recto: recto, verso: verso, bottom: bottom);
  }

  ArticlePageTextureSnapshot? _validSnapshotForRef(
    _MediaPageTextureRef ref, {
    required Size expectedSize,
  }) {
    final key = _MediaPageTextureKey(ref.pageIndex, ref.face);
    var snapshot = _pageSnapshots[key];
    if (widget.textureSnapshotBuilder == null &&
        ref.face == MediaPageFlipSurfaceFace.back) {
      snapshot ??=
          _pageSnapshots[_MediaPageTextureKey(
            ref.pageIndex,
            MediaPageFlipSurfaceFace.front,
          )];
    }
    if (widget.textureSnapshotBuilder == null &&
        !_isPageTextureReady(ref.pageIndex)) {
      _queueTextureIndices(<int>[ref.pageIndex], prioritize: true);
      return null;
    }
    if (snapshot == null) {
      _queueTextureIndices(<int>[ref.pageIndex], prioritize: true);
      return null;
    }
    if (snapshot.matchesLogicalSize(expectedSize)) {
      return snapshot;
    }
    _retireSnapshotForKey(key);
    _queueTextureIndices(<int>[ref.pageIndex], prioritize: true);
    return null;
  }

  bool _isPageTextureReady(int index) {
    final predicate = widget.isPageTextureReady;
    return predicate == null || predicate(index);
  }

  void _queueSceneTextureWindow(
    StPageFlipScene scene,
    _MediaPageTextureBinding? binding,
  ) {
    _queueTextureIndices(
      binding?.prioritizedPageIndices ??
          <int>[
            scene.currentPageIndex,
            scene.currentPageIndex + 1,
            scene.currentPageIndex - 1,
          ],
    );
  }

  void _queueStaticTextureSnapshots() {
    _queueTextureIndices(<int>[
      _currentPage,
      _currentPage - 1,
      _currentPage + 1,
    ]);
  }

  void _queueTextureIndices(Iterable<int> indices, {bool prioritize = false}) {
    var added = false;
    final ordered = indices.toList(growable: false);
    final iterable = prioritize ? ordered.reversed : ordered;
    for (final index in iterable) {
      if (index < 0 || index >= widget.pageCount) {
        continue;
      }
      if (_hasSnapshotForIndex(index)) {
        continue;
      }
      final alreadyPending = _pendingCaptureIndices.contains(index);
      if (alreadyPending && !prioritize) {
        continue;
      }
      _pendingCaptureIndices.remove(index);
      if (prioritize) {
        _pendingCaptureIndices.addFirst(index);
      } else {
        _pendingCaptureIndices.addLast(index);
      }
      if (widget.textureSnapshotBuilder == null) {
        _captureBoundaryKeys.putIfAbsent(
          index,
          () => GlobalKey(debugLabel: 'media_pageflip_capture_$index'),
        );
      }
      added = true;
    }
    if (added) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() {});
        }
      });
      _scheduleCapture();
    }
  }

  bool _hasSnapshotForIndex(int index) {
    final front = _pageSnapshots.containsKey(
      _MediaPageTextureKey(index, MediaPageFlipSurfaceFace.front),
    );
    if (widget.textureSnapshotBuilder == null) {
      return front;
    }
    return front &&
        _pageSnapshots.containsKey(
          _MediaPageTextureKey(index, MediaPageFlipSurfaceFace.back),
        );
  }

  void _retireSnapshotForKey(_MediaPageTextureKey key) {
    final retired = _pageSnapshots.remove(key);
    if (retired != null) {
      _retiredSnapshots.add(retired);
    }
  }

  void _storeTexturePair(int index, MediaPageFlipTexturePair pair) {
    final frontKey = _MediaPageTextureKey(
      index,
      MediaPageFlipSurfaceFace.front,
    );
    final backKey = _MediaPageTextureKey(index, MediaPageFlipSurfaceFace.back);
    _retireSnapshotForKey(frontKey);
    _retireSnapshotForKey(backKey);
    _pageSnapshots[frontKey] = pair.front;
    _pageSnapshots[backKey] = pair.back;
  }

  void _scheduleCapture() {
    if (_captureScheduled ||
        _captureInFlight ||
        _pendingCaptureIndices.isEmpty ||
        !mounted ||
        _lastPageSize == null) {
      return;
    }
    _captureScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _captureScheduled = false;
      _captureInFlight = true;
      unawaited(_capturePendingTextures());
    });
  }

  double _capturePixelRatio(BuildContext context) {
    final view = View.maybeOf(context);
    final ratio =
        view?.devicePixelRatio ??
        MediaQuery.maybeOf(context)?.devicePixelRatio ??
        1.0;
    return ratio.clamp(1.0, double.infinity).toDouble();
  }

  Future<void> _capturePendingTextures() async {
    if (!mounted || _pendingCaptureIndices.isEmpty) {
      _captureInFlight = false;
      return;
    }
    final pendingNow = _pendingCaptureIndices.take(3).toList(growable: false);
    var capturedAny = false;
    final directTextureBuilder = widget.textureSnapshotBuilder;
    if (directTextureBuilder != null) {
      final expectedGeneration = _viewportCaptureGeneration;
      final expectedPageSize = _lastPageSize;
      if (expectedPageSize == null) {
        _captureInFlight = false;
        return;
      }
      final pixelRatio = _capturePixelRatio(context);
      try {
        for (final index in pendingNow) {
          final pair = await directTextureBuilder(
            context,
            index,
            expectedPageSize,
            pixelRatio,
          );
          if (!mounted || pair == null) {
            pair?.dispose();
            _pendingCaptureIndices.remove(index);
            if (!mounted) {
              return;
            }
            continue;
          }
          final stale =
              expectedGeneration != _viewportCaptureGeneration ||
              !pair.matchesLogicalSize(expectedPageSize);
          if (stale) {
            pair.dispose();
            _pendingCaptureIndices.remove(index);
          } else {
            _storeTexturePair(index, pair);
            _pendingCaptureIndices.remove(index);
            capturedAny = true;
          }
        }
      } catch (_) {
        // Direct media texture construction may fail while the image is still
        // warming; release it so the next ready/gesture signal can requeue
        // without spinning a frame-by-frame retry loop.
        for (final index in pendingNow) {
          _pendingCaptureIndices.remove(index);
        }
      } finally {
        _captureInFlight = false;
      }
      if (capturedAny && mounted) {
        setState(() {});
      }
      if (mounted && _pendingCaptureIndices.isNotEmpty) {
        _scheduleCapture();
      }
      return;
    }
    try {
      for (final index in pendingNow) {
        if (!mounted) {
          break;
        }
        if (!_isPageTextureReady(index)) {
          continue;
        }
        final boundaryKey = _captureBoundaryKeys[index];
        final boundaryContext = boundaryKey?.currentContext;
        if (boundaryContext == null || !boundaryContext.mounted) {
          continue;
        }
        final renderObject = boundaryContext.findRenderObject();
        if (renderObject is! RenderRepaintBoundary ||
            !renderObject.attached ||
            !renderObject.hasSize ||
            renderObject.size.isEmpty ||
            renderObject.debugNeedsPaint) {
          continue;
        }
        final expectedGeneration = _viewportCaptureGeneration;
        final expectedPageSize = _lastPageSize;
        final logicalSize = renderObject.size;
        final pixelRatio = _capturePixelRatio(boundaryContext);
        try {
          final image = await renderObject.toImage(pixelRatio: pixelRatio);
          if (!mounted) {
            image.dispose();
            return;
          }
          final stale =
              expectedPageSize == null ||
              expectedGeneration != _viewportCaptureGeneration ||
              !_sizeEquals(expectedPageSize, logicalSize) ||
              !_sizeEquals(renderObject.size, logicalSize) ||
              !identical(_captureBoundaryKeys[index], boundaryKey);
          if (stale) {
            image.dispose();
            continue;
          }
          final frontKey = _MediaPageTextureKey(
            index,
            MediaPageFlipSurfaceFace.front,
          );
          _retireSnapshotForKey(frontKey);
          _pageSnapshots[frontKey] = ArticlePageTextureSnapshot(
            image: image,
            logicalSize: logicalSize,
            pixelRatio: pixelRatio,
          );
          _pendingCaptureIndices.remove(index);
          capturedAny = true;
        } catch (_) {
          // Capture may transiently fail while the hidden surface is repainting.
        }
      }
    } finally {
      _captureInFlight = false;
    }
    if (capturedAny && mounted) {
      setState(() {});
    }
    if (mounted &&
        _pendingCaptureIndices.isNotEmpty &&
        _pendingCaptureIndices.any(_isPageTextureReady)) {
      _scheduleCapture();
    }
  }

  void _clearAllSnapshots() {
    _retiredSnapshots.addAll(_pageSnapshots.values);
    _pageSnapshots.clear();
    _pendingCaptureIndices.clear();
    _captureBoundaryKeys.clear();
  }

  void _disposeRetiredSnapshots() {
    for (final snapshot in _retiredSnapshots) {
      snapshot.dispose();
    }
    _retiredSnapshots.clear();
  }

  bool _sizeEquals(Size? a, Size b) {
    if (a == null) {
      return false;
    }
    return (a.width - b.width).abs() < 0.01 &&
        (a.height - b.height).abs() < 0.01;
  }
}

class _MediaPagePolygonClipper extends CustomClipper<Path> {
  const _MediaPagePolygonClipper(this.points);

  final List<Offset> points;

  @override
  Path getClip(Size size) {
    final path = Path();
    if (points.isEmpty) {
      return path;
    }
    path.moveTo(points.first.dx, points.first.dy);
    for (final point in points.skip(1)) {
      path.lineTo(point.dx, point.dy);
    }
    path.close();
    return path;
  }

  @override
  bool shouldReclip(covariant _MediaPagePolygonClipper oldClipper) {
    if (identical(points, oldClipper.points)) {
      return false;
    }
    if (points.length != oldClipper.points.length) {
      return true;
    }
    for (var index = 0; index < points.length; index += 1) {
      if (points[index] != oldClipper.points[index]) {
        return true;
      }
    }
    return false;
  }
}

class _StableMediaPageCaptureLayer extends StatefulWidget {
  const _StableMediaPageCaptureLayer({
    required this.capturePages,
    required this.pageSize,
    required this.boundaryKeys,
    required this.buildPage,
  });

  final List<int> capturePages;
  final Size pageSize;
  final Map<int, GlobalKey> boundaryKeys;
  final Widget Function(int index) buildPage;

  @override
  State<_StableMediaPageCaptureLayer> createState() =>
      _StableMediaPageCaptureLayerState();
}

class _StableMediaPageCaptureLayerState
    extends State<_StableMediaPageCaptureLayer> {
  late List<int> _capturePages;
  late Map<int, Widget> _cachedWidgets;

  @override
  void initState() {
    super.initState();
    _capturePages = List<int>.of(widget.capturePages);
    _rebuildCache();
  }

  @override
  void didUpdateWidget(covariant _StableMediaPageCaptureLayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!listEquals(widget.capturePages, _capturePages) ||
        widget.pageSize != oldWidget.pageSize) {
      _capturePages = List<int>.of(widget.capturePages);
      _rebuildCache();
    }
  }

  void _rebuildCache() {
    _cachedWidgets = <int, Widget>{
      for (final index in _capturePages) index: widget.buildPage(index),
    };
  }

  @override
  Widget build(BuildContext context) {
    final column = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: _capturePages
          .map(
            (index) => RepaintBoundary(
              key: widget.boundaryKeys[index],
              child: SizedBox(
                width: widget.pageSize.width,
                height: widget.pageSize.height,
                child: _cachedWidgets[index] ?? const SizedBox.shrink(),
              ),
            ),
          )
          .toList(growable: false),
    );
    return Align(
      alignment: Alignment.topLeft,
      child: OverflowBox(
        alignment: Alignment.topLeft,
        minWidth: widget.pageSize.width,
        maxWidth: widget.pageSize.width,
        minHeight: widget.pageSize.height,
        maxHeight: widget.pageSize.height * _capturePages.length,
        child: column,
      ),
    );
  }
}
