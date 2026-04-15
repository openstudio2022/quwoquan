import 'dart:async';
import 'dart:collection';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/core/pageflip_book_controller.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/animation_plan_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/render/high_fidelity/pageflip_book_high_fidelity_facade.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/render/mesh/pageflip_book_mesh_builder.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/render/mesh/pageflip_book_mesh_renderer.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/scene/pageflip_book_scene.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/snapshot/pageflip_book_texture_session.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

class PageflipBookIsolated extends StatefulWidget {
  const PageflipBookIsolated({
    super.key,
    required this.pageCount,
    required this.pageBuilder,
    this.initialPage = 0,
    this.pageAspectRatio = 0.72,
    this.stagePadding = const EdgeInsets.all(AppSpacing.md),
    this.stageColor = AppColors.welcomeBackgroundDark,
    this.onPageChanged,
  }) : assert(pageCount >= 0),
       assert(pageAspectRatio > 0);

  final int pageCount;
  final PageflipBookIsolatedPageBuilder pageBuilder;
  final int initialPage;
  final double pageAspectRatio;
  final EdgeInsets stagePadding;
  final Color stageColor;
  final ValueChanged<int>? onPageChanged;

  @override
  State<PageflipBookIsolated> createState() => _PageflipBookIsolatedState();
}

class _PageflipBookIsolatedState extends State<PageflipBookIsolated>
    with SingleTickerProviderStateMixin {
  static final ArticlePageCurlLightConfig _defaultLightConfig =
      ArticlePageCurlLightConfig(
        shadowColor: AppColors.black.withValues(alpha: 0.82),
        highlightColor: AppColors.white.withValues(alpha: 0.22),
        paperTintColor: Color.alphaBlend(
          AppColors.white.withValues(alpha: 0.14),
          ArticlePaperPaletteColors.creamStageLight,
        ).withValues(alpha: 0.24),
        ambientOcclusionColor: AppColors.black.withValues(alpha: 0.22),
      );

  final PageflipBookIsolatedHighFidelityFacade _highFidelityFacade =
      const PageflipBookIsolatedHighFidelityFacade();
  final PageflipBookIsolatedMeshBuilder _meshBuilder =
      const PageflipBookIsolatedMeshBuilder();
  final Map<int, GlobalKey> _captureBoundaryKeys = <int, GlobalKey>{};
  final Map<int, ArticlePageTextureSnapshot> _pageSnapshots =
      <int, ArticlePageTextureSnapshot>{};
  final List<ArticlePageTextureSnapshot> _retiredSnapshots =
      <ArticlePageTextureSnapshot>[];
  final ListQueue<int> _pendingCaptureIndices = ListQueue<int>();

  late PageflipBookIsolatedController _controller;
  late AnimationController _animationController;

  PageflipBookIsolatedTextureSession? _activeTextureSession;
  PageflipBookIsolatedAnimationPlan? _activeAnimationPlan;
  ui.FragmentProgram? _lightingProgram;
  ui.FragmentProgram? _backfaceProgram;

  Size? _lastStageSize;
  Size? _lastPageSize;
  Size? _snapshotPageSize;
  int _lastAnimationFrameIndex = -1;
  bool _captureScheduled = false;
  bool _dragActive = false;

  @override
  void initState() {
    super.initState();
    _controller = PageflipBookIsolatedController(
      pageCount: widget.pageCount,
      initialPage: widget.initialPage,
    );
    _animationController = AnimationController(vsync: this)
      ..addListener(_handleAnimationTick)
      ..addStatusListener(_handleAnimationStatus);
    unawaited(_loadShaders());
  }

  @override
  void didUpdateWidget(covariant PageflipBookIsolated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.pageCount != widget.pageCount ||
        oldWidget.initialPage != widget.initialPage) {
      _controller = PageflipBookIsolatedController(
        pageCount: widget.pageCount,
        initialPage: widget.initialPage,
      );
      _activeTextureSession = null;
      _activeAnimationPlan = null;
      _animationController.stop();
      _lastAnimationFrameIndex = -1;
      _dragActive = false;
      _clearAllSnapshots();
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
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final stageSize = Size(
          constraints.maxWidth.isFinite ? constraints.maxWidth : 0,
          constraints.maxHeight.isFinite ? constraints.maxHeight : 0,
        );
        if (widget.pageCount <= 0 ||
            stageSize.width <= 0 ||
            stageSize.height <= 0) {
          return const SizedBox.expand();
        }
        final pageSize = _resolvePageSize(stageSize);
        _updateViewport(stageSize: stageSize, pageSize: pageSize);
        _reconcileSnapshotSize(pageSize);
        _queueCurrentTextureWindow();

        final scene = _controller.sceneForStage(stageSize);
        if (scene == null) {
          return ColoredBox(color: widget.stageColor);
        }
        final highFidelityState = scene.isInteractive
            ? _resolveHighFidelityState(scene)
            : null;
        final meshScene = scene.isInteractive
            ? _buildMeshScene(scene, highFidelityState)
            : null;
        if (_pendingCaptureIndices.isNotEmpty) {
          _scheduleCapture();
        }

        return ColoredBox(
          color: widget.stageColor,
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              if (meshScene != null)
                Positioned.fromRect(
                  rect: scene.pageRect,
                  child: const ColoredBox(
                    color: ArticlePaperPaletteColors.creamStageLight,
                  ),
                )
              else
                _buildStaticPage(scene.pageRect, scene.currentPageIndex),
              if (meshScene != null)
                Positioned.fill(
                  child: IgnorePointer(
                    child: PageflipBookIsolatedMeshRenderer(
                      key: PageflipBookIsolatedTestKeys.meshRenderer,
                      scene: meshScene,
                      lightingProgram: _lightingProgram,
                      backfaceProgram: _backfaceProgram,
                    ),
                  ),
                ),
              Positioned.fill(child: _buildGestureLayer(scene)),
              if (_pendingCaptureIndices.isNotEmpty)
                Positioned.fill(
                  child: IgnorePointer(
                    child: _buildCaptureLayer(pageSize, stageSize),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildGestureLayer(PageflipBookIsolatedScene scene) {
    final halfWidth = scene.stageSize.width / 2;
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onTapUp: (details) => _handleTap(details.localPosition),
      onPanStart: (details) => _handlePanStart(details.localPosition),
      onPanUpdate: (details) => _handlePanUpdate(details.localPosition),
      onPanEnd: (_) => _handlePanEnd(),
      onPanCancel: _handlePanCancel,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          const SizedBox.expand(key: PageflipBookIsolatedTestKeys.stage),
          Positioned(
            left: 0,
            top: 0,
            bottom: 0,
            width: halfWidth,
            child: const IgnorePointer(
              child: SizedBox.expand(
                key: PageflipBookIsolatedTestKeys.hotzoneLeft,
              ),
            ),
          ),
          Positioned(
            right: 0,
            top: 0,
            bottom: 0,
            width: halfWidth,
            child: const IgnorePointer(
              child: SizedBox.expand(
                key: PageflipBookIsolatedTestKeys.hotzoneRight,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStaticPage(Rect pageRect, int pageIndex) {
    final pageSize = pageRect.size;
    return Align(
      alignment: Alignment.topLeft,
      child: Padding(
        padding: EdgeInsets.only(left: pageRect.left, top: pageRect.top),
        child: SizedBox.fromSize(
          size: pageSize,
          child: KeyedSubtree(
            key: PageflipBookIsolatedTestKeys.staticPage,
            child: _buildPageSurface(pageIndex, pageSize),
          ),
        ),
      ),
    );
  }

  Widget _buildCaptureLayer(Size pageSize, Size stageSize) {
    final pendingPages = _pendingCaptureIndices.take(3).toList(growable: false);
    if (pendingPages.isEmpty) {
      return const SizedBox.shrink();
    }
    return Transform.translate(
      offset: Offset(stageSize.width + pageSize.width + 48, 0),
      child: _StableTextureCaptureLayer(
        capturePages: pendingPages,
        pageSize: pageSize,
        boundaryKeys: _captureBoundaryKeys,
        buildPage: (pageIndex) => _buildPageSurface(pageIndex, pageSize),
      ),
    );
  }

  Widget _buildPageSurface(int pageIndex, Size pageSize) {
    return SizedBox(
      width: pageSize.width,
      height: pageSize.height,
      child: widget.pageBuilder(context, pageIndex, pageSize),
    );
  }

  PageflipBookIsolatedMeshRenderScene? _buildMeshScene(
    PageflipBookIsolatedScene scene,
    PageflipBookIsolatedHighFidelityState? highFidelityState,
  ) {
    if (highFidelityState == null || !highFidelityState.usesMesh) {
      return null;
    }
    return _meshBuilder.build(
      scene: scene,
      textures: highFidelityState.bundle!,
      lightConfig: _defaultLightConfig,
    );
  }

  PageflipBookIsolatedHighFidelityState _resolveHighFidelityState(
    PageflipBookIsolatedScene scene,
  ) {
    final state = _computeHighFidelityState(scene);
    _applyResolvedHighFidelityState(state);
    return state;
  }

  PageflipBookIsolatedHighFidelityState _computeHighFidelityState(
    PageflipBookIsolatedScene scene,
  ) {
    return _highFidelityFacade.resolve(
      scene: scene,
      snapshots: _pageSnapshots,
      existingSession: _activeTextureSession,
      supportsAdvancedPageCurl: _supportsAdvancedPageCurl,
      freezeBinding: _shouldFreezeTextureSession(scene),
    );
  }

  void _applyResolvedHighFidelityState(
    PageflipBookIsolatedHighFidelityState state,
  ) {
    _activeTextureSession = state.textureSession;
    _queueTextureIndices(state.prioritizedPageIndices, prioritize: true);
  }

  void _syncActiveTextureSession(PageflipBookIsolatedScene scene) {
    _applyResolvedHighFidelityState(_computeHighFidelityState(scene));
  }

  void _syncActiveTextureSessionForCurrentScene() {
    final stageSize = _lastStageSize;
    if (stageSize == null) {
      return;
    }
    final scene = _controller.sceneForStage(stageSize);
    if (scene == null) {
      return;
    }
    _syncActiveTextureSession(scene);
  }

  void _clearActiveTextureSession() {
    _activeTextureSession = null;
  }

  bool get _supportsAdvancedPageCurl =>
      _lightingProgram != null && _backfaceProgram != null;

  bool _shouldFreezeTextureSession(PageflipBookIsolatedScene scene) {
    return _dragActive ||
        _animationController.isAnimating ||
        scene.isInteractive;
  }

  void _queueTextureIndices(
    Iterable<int> pageIndices, {
    bool prioritize = false,
  }) {
    var added = false;
    final orderedIndices = pageIndices.toList(growable: false);
    final iteration = prioritize ? orderedIndices.reversed : orderedIndices;
    for (final pageIndex in iteration) {
      if (pageIndex < 0 || pageIndex >= widget.pageCount) {
        continue;
      }
      if (_pageSnapshots.containsKey(pageIndex)) {
        continue;
      }
      final alreadyPending = _pendingCaptureIndices.contains(pageIndex);
      if (alreadyPending && !prioritize) {
        continue;
      }
      _pendingCaptureIndices.remove(pageIndex);
      if (prioritize) {
        _pendingCaptureIndices.addFirst(pageIndex);
      } else {
        _pendingCaptureIndices.addLast(pageIndex);
      }
      added = added || !alreadyPending;
      _captureBoundaryKeys.putIfAbsent(
        pageIndex,
        () => GlobalKey(debugLabel: 'pageflip_isolated_capture_$pageIndex'),
      );
    }
    if (added) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        setState(() {});
      });
      _scheduleCapture();
    }
  }

  void _updateViewport({required Size stageSize, required Size pageSize}) {
    if (_sizeEquals(_lastStageSize, stageSize) &&
        _sizeEquals(_lastPageSize, pageSize)) {
      return;
    }
    _lastStageSize = stageSize;
    _lastPageSize = pageSize;
    _controller.updateViewport(stageSize: stageSize, pageSize: pageSize);
  }

  Size _resolvePageSize(Size stageSize) {
    final paddedWidth = (stageSize.width - widget.stagePadding.horizontal)
        .clamp(1.0, double.infinity);
    final paddedHeight = (stageSize.height - widget.stagePadding.vertical)
        .clamp(1.0, double.infinity);
    var width = paddedWidth;
    var height = width / widget.pageAspectRatio;
    if (height > paddedHeight) {
      height = paddedHeight;
      width = height * widget.pageAspectRatio;
    }
    return Size(width, height);
  }

  void _reconcileSnapshotSize(Size pageSize) {
    if (_sizeEquals(_snapshotPageSize, pageSize)) {
      return;
    }
    _clearAllSnapshots();
    _snapshotPageSize = pageSize;
    _activeTextureSession = null;
  }

  void _queueCurrentTextureWindow() {
    final current = _controller.currentPageIndex;
    _queueTextureIndices(<int>[current - 1, current, current + 1]);
  }

  void _handleTap(Offset localPosition) {
    if (_dragActive || _animationController.isAnimating) {
      return;
    }
    final direction = localPosition.dx < ((_lastStageSize?.width ?? 0) / 2)
        ? PageflipBookIsolatedDirection.backward
        : PageflipBookIsolatedDirection.forward;
    _startProgrammaticFlip(direction);
  }

  void _handlePanStart(Offset localPosition) {
    if (_animationController.isAnimating) {
      return;
    }
    if (!_controller.start(localPosition)) {
      return;
    }
    final stageSize = _lastStageSize;
    if (stageSize == null) {
      _controller.cancelInteraction();
      return;
    }
    _dragActive = true;
    _controller.fold(localPosition);
    _syncActiveTextureSessionForCurrentScene();
    setState(() {});
  }

  void _handlePanUpdate(Offset localPosition) {
    if (!_dragActive) {
      return;
    }
    final stageSize = _lastStageSize;
    if (stageSize == null) {
      _handlePanCancel();
      return;
    }
    _controller.fold(localPosition);
    _syncActiveTextureSessionForCurrentScene();
    setState(() {});
  }

  void _handlePanEnd() {
    if (!_dragActive) {
      return;
    }
    _dragActive = false;
    final plan = _controller.stopMove();
    if (plan == null) {
      _controller.cancelInteraction();
      _clearActiveTextureSession();
      setState(() {});
      return;
    }
    _startAnimation(plan);
  }

  void _handlePanCancel() {
    _dragActive = false;
    _controller.cancelInteraction();
    _clearActiveTextureSession();
    if (mounted) {
      setState(() {});
    }
  }

  void _startProgrammaticFlip(PageflipBookIsolatedDirection direction) {
    if (!_controller.canFlip(direction) || !_isDirectionReady(direction)) {
      return;
    }
    final plan = _controller.flip(direction);
    if (plan == null) {
      return;
    }
    _startAnimation(plan);
  }

  void _startAnimation(PageflipBookIsolatedAnimationPlan plan) {
    _syncActiveTextureSessionForCurrentScene();
    _activeAnimationPlan = plan;
    _lastAnimationFrameIndex = -1;
    _animationController.duration = plan.duration;
    _animationController.forward(from: 0);
    setState(() {});
  }

  void _handleAnimationTick() {
    final plan = _activeAnimationPlan;
    final stageSize = _lastStageSize;
    if (plan == null || stageSize == null || plan.frames.isEmpty) {
      return;
    }
    final nextIndex = (_animationController.value * (plan.frames.length - 1))
        .round()
        .clamp(0, plan.frames.length - 1);
    if (nextIndex == _lastAnimationFrameIndex) {
      return;
    }
    _controller.applyAnimationFrame(plan.frames[nextIndex]);
    _syncActiveTextureSessionForCurrentScene();
    _lastAnimationFrameIndex = nextIndex;
    if (mounted) {
      setState(() {});
    }
  }

  void _handleAnimationStatus(AnimationStatus status) {
    if (status != AnimationStatus.completed) {
      return;
    }
    final plan = _activeAnimationPlan;
    if (plan != null) {
      final previousPage = _controller.currentPageIndex;
      _controller.completeAnimation(plan);
      final nextPage = _controller.currentPageIndex;
      if (nextPage != previousPage) {
        widget.onPageChanged?.call(nextPage);
      }
    }
    _activeAnimationPlan = null;
    _clearActiveTextureSession();
    _lastAnimationFrameIndex = -1;
    _queueCurrentTextureWindow();
    if (mounted) {
      setState(() {});
    }
  }

  bool _isDirectionReady(PageflipBookIsolatedDirection direction) {
    final missing = <int>[];
    for (final pageIndex in _controller.textureWindowForDirection(direction)) {
      if (!_pageSnapshots.containsKey(pageIndex)) {
        missing.add(pageIndex);
      }
    }
    if (missing.isNotEmpty) {
      _queueTextureIndices(missing, prioritize: true);
      return false;
    }
    return true;
  }

  Future<void> _loadShaders() async {
    try {
      final lighting = await ui.FragmentProgram.fromAsset(
        'shaders/article_page_curl_lighting.frag',
      );
      final backface = await ui.FragmentProgram.fromAsset(
        'shaders/article_page_curl_backface.frag',
      );
      if (!mounted) {
        return;
      }
      _lightingProgram = lighting;
      _backfaceProgram = backface;
      _queueCurrentTextureWindow();
      setState(() {});
    } catch (_) {
      // shader 是可选增强效果；V2 mesh 不依赖它才能运行。
    }
  }

  void _scheduleCapture() {
    if (_captureScheduled || _pendingCaptureIndices.isEmpty || !mounted) {
      return;
    }
    _captureScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _captureScheduled = false;
      unawaited(_capturePendingTextures());
    });
  }

  double _capturePixelRatio(BuildContext context) {
    final view = View.maybeOf(context);
    final pixelRatio =
        view?.devicePixelRatio ??
        MediaQuery.maybeOf(context)?.devicePixelRatio ??
        1.0;
    return pixelRatio.clamp(1.0, 2.0).toDouble();
  }

  Future<void> _capturePendingTextures() async {
    if (!mounted || _pendingCaptureIndices.isEmpty) {
      return;
    }
    final pendingNow = _pendingCaptureIndices.take(3).toList(growable: false);
    var capturedAny = false;
    for (final pageIndex in pendingNow) {
      final boundaryKey = _captureBoundaryKeys[pageIndex];
      final boundaryContext = boundaryKey?.currentContext;
      if (boundaryContext == null || !boundaryContext.mounted) {
        continue;
      }
      RenderRepaintBoundary? boundary;
      try {
        final renderObject = boundaryContext.findRenderObject();
        if (renderObject is RenderRepaintBoundary) {
          boundary = renderObject;
        }
      } catch (_) {
        continue;
      }
      if (boundary == null ||
          !boundary.attached ||
          !boundary.hasSize ||
          boundary.size.isEmpty ||
          boundary.debugNeedsPaint) {
        continue;
      }
      final logicalSize = boundary.size;
      final pixelRatio = _capturePixelRatio(boundaryContext);
      try {
        final image = await boundary.toImage(pixelRatio: pixelRatio);
        if (!mounted) {
          image.dispose();
          return;
        }
        final retired = _pageSnapshots.remove(pageIndex);
        if (retired != null) {
          _retiredSnapshots.add(retired);
        }
        _pageSnapshots[pageIndex] = ArticlePageTextureSnapshot(
          image: image,
          logicalSize: logicalSize,
          pixelRatio: pixelRatio,
        );
        _pendingCaptureIndices.remove(pageIndex);
        capturedAny = true;
      } catch (_) {
        // Capture can temporarily fail while the hidden layer is rebuilding.
      }
    }
    if (capturedAny && mounted) {
      _syncActiveTextureSessionForCurrentScene();
      setState(() {});
    }
    if (_pendingCaptureIndices.isNotEmpty) {
      _scheduleCapture();
    }
  }

  void _clearAllSnapshots() {
    _retiredSnapshots.addAll(_pageSnapshots.values);
    _pageSnapshots.clear();
    _pendingCaptureIndices.clear();
    _captureBoundaryKeys.clear();
    _snapshotPageSize = null;
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

class _StableTextureCaptureLayer extends StatefulWidget {
  const _StableTextureCaptureLayer({
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
  State<_StableTextureCaptureLayer> createState() =>
      _StableTextureCaptureLayerState();
}

class _StableTextureCaptureLayerState
    extends State<_StableTextureCaptureLayer> {
  late List<int> _capturePages;
  late Map<int, Widget> _cachedWidgets;

  @override
  void initState() {
    super.initState();
    _capturePages = List<int>.of(widget.capturePages);
    _rebuildCache();
  }

  @override
  void didUpdateWidget(covariant _StableTextureCaptureLayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!listEquals(widget.capturePages, _capturePages) ||
        widget.pageSize != oldWidget.pageSize) {
      _capturePages = List<int>.of(widget.capturePages);
      _rebuildCache();
    }
  }

  void _rebuildCache() {
    _cachedWidgets = {
      for (final index in _capturePages) index: widget.buildPage(index),
    };
  }

  @override
  Widget build(BuildContext context) {
    final column = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: _capturePages
          .map((index) {
            return RepaintBoundary(
              key: widget.boundaryKeys.putIfAbsent(
                index,
                () => GlobalKey(debugLabel: 'pageflip_isolated_capture_$index'),
              ),
              child: SizedBox(
                width: widget.pageSize.width,
                height: widget.pageSize.height,
                child: _cachedWidgets[index] ?? const SizedBox.shrink(),
              ),
            );
          })
          .toList(growable: false),
    );
    return IgnorePointer(
      child: ExcludeSemantics(
        child: Align(
          alignment: Alignment.topLeft,
          child: OverflowBox(
            alignment: Alignment.topLeft,
            minWidth: widget.pageSize.width,
            maxWidth: widget.pageSize.width,
            minHeight: widget.pageSize.height,
            maxHeight: widget.pageSize.height * _capturePages.length,
            child: column,
          ),
        ),
      ),
    );
  }
}
