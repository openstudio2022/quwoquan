import 'dart:async';
import 'dart:collection';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/core/pageflip_book_controller.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/render/mesh/pageflip_book_mesh_builder.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/render/mesh/pageflip_book_mesh_renderer.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/scene/pageflip_book_scene.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/snapshot/pageflip_book_texture_session.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
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
    shadowColor: AppColors.black.withValues(alpha: 0x5C / 255.0),
    highlightColor: AppColors.white.withValues(alpha: 0x45 / 255.0),
    paperTintColor: AppColors.iosProfileSurfaceLight,
    ambientOcclusionColor: AppColors.black.withValues(alpha: 0x26 / 255.0),
  );

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
  StPageFlipAnimationPlan? _activeAnimationPlan;
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
        final meshScene = scene.isInteractive ? _buildMeshScene(scene) : null;
        final interactionBinding = _activeTextureSession?.binding;
        if (_pendingCaptureIndices.isNotEmpty) {
          _scheduleCapture();
        }

        return ColoredBox(
          color: widget.stageColor,
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              if (meshScene == null || interactionBinding == null)
                _buildStaticPage(
                  scene.pageRect,
                  scene.legacyScene.currentPageIndex,
                )
              else
                ..._buildInteractionStaticLayers(scene, interactionBinding),
              if (meshScene != null)
                Positioned.fill(
                  child: IgnorePointer(
                    child: PageflipBookIsolatedMeshRenderer(
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
    return Positioned.fromRect(
      rect: pageRect,
      child: KeyedSubtree(
        key: PageflipBookIsolatedTestKeys.staticPage,
        child: _buildPageSurface(pageIndex, pageSize),
      ),
    );
  }

  List<Widget> _buildInteractionStaticLayers(
    PageflipBookIsolatedScene scene,
    PageflipBookIsolatedSheetBinding binding,
  ) {
    final pageRect = scene.pageRect;
    final pageRectPath = Path()..addRect(pageRect);
    final bottomPath = scene.buildBottomClipPath();
    final topPath = Path.combine(
      PathOperation.difference,
      pageRectPath,
      bottomPath,
    );
    switch (binding.direction) {
      case PageflipBookIsolatedDirection.forward:
        return <Widget>[
          _buildClippedStaticPage(
            rect: pageRect,
            pageIndex: binding.bottomPageIndex,
            clipPath: bottomPath,
          ),
          _buildClippedStaticPage(
            rect: pageRect,
            pageIndex: scene.legacyScene.currentPageIndex,
            clipPath: topPath,
          ),
        ];
      case PageflipBookIsolatedDirection.backward:
        return <Widget>[
          _buildClippedStaticPage(
            rect: pageRect,
            pageIndex: scene.legacyScene.currentPageIndex,
            clipPath: bottomPath,
          ),
          _buildClippedStaticPage(
            rect: pageRect,
            pageIndex: binding.rectoPageIndex,
            clipPath: topPath,
          ),
        ];
    }
  }

  Widget _buildClippedStaticPage({
    required Rect rect,
    required int pageIndex,
    required Path clipPath,
  }) {
    return Positioned.fromRect(
      rect: rect,
      child: ClipPath(
        clipper: _RelativePathClipper(
          clipPath.shift(Offset(-rect.left, -rect.top)),
        ),
        child: _buildPageSurface(pageIndex, rect.size),
      ),
    );
  }

  Widget _buildCaptureLayer(Size pageSize, Size stageSize) {
    final pendingPages = _pendingCaptureIndices.toSet().toList(growable: false);
    return Transform.translate(
      offset: Offset(stageSize.width + pageSize.width + 48, 0),
      child: Align(
        alignment: Alignment.topLeft,
        child: SizedBox(
          width: pageSize.width,
          height: pageSize.height,
          child: Stack(
            children: pendingPages
                .map(
                  (pageIndex) => RepaintBoundary(
                    key: _captureBoundaryKeys.putIfAbsent(
                      pageIndex,
                      () => GlobalKey(
                        debugLabel: 'pageflip_isolated_capture_$pageIndex',
                      ),
                    ),
                    child: SizedBox(
                      width: pageSize.width,
                      height: pageSize.height,
                      child: _buildPageSurface(pageIndex, pageSize),
                    ),
                  ),
                )
                .toList(growable: false),
          ),
        ),
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
  ) {
    final textureSession = _activeTextureSession;
    if (textureSession == null || !textureSession.isReadyForMesh) {
      return null;
    }
    return _meshBuilder.build(
      scene: scene,
      textures: textureSession.bundle!,
      lightConfig: _defaultLightConfig,
    );
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
    for (final candidate in <int>[current - 1, current, current + 1]) {
      if (candidate < 0 || candidate >= widget.pageCount) {
        continue;
      }
      if (_pageSnapshots.containsKey(candidate) ||
          _pendingCaptureIndices.contains(candidate)) {
        continue;
      }
      _pendingCaptureIndices.add(candidate);
    }
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
    final scene = _controller.sceneForStage(stageSize);
    if (scene == null || !_prepareTextureSession(scene, freezeBinding: false)) {
      _controller.cancelInteraction();
      _activeTextureSession = null;
      return;
    }
    _dragActive = true;
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
    final scene = _controller.sceneForStage(stageSize);
    if (scene == null || !_prepareTextureSession(scene, freezeBinding: true)) {
      _handlePanCancel();
      return;
    }
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
      _activeTextureSession = null;
      setState(() {});
      return;
    }
    _startAnimation(plan);
  }

  void _handlePanCancel() {
    _dragActive = false;
    _controller.cancelInteraction();
    _activeTextureSession = null;
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
    final stageSize = _lastStageSize;
    if (stageSize == null) {
      _controller.cancelInteraction();
      return;
    }
    final scene = _controller.sceneForStage(stageSize);
    if (scene == null || !_prepareTextureSession(scene, freezeBinding: false)) {
      _controller.cancelInteraction();
      _activeTextureSession = null;
      return;
    }
    _startAnimation(plan);
  }

  void _startAnimation(StPageFlipAnimationPlan plan) {
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
    _controller.applyAnimationFrame(
      plan.frames[nextIndex],
      reversePose:
          plan.reversePoses != null && nextIndex < plan.reversePoses!.length
          ? plan.reversePoses![nextIndex]
          : null,
    );
    final scene = _controller.sceneForStage(stageSize);
    if (scene == null || !_prepareTextureSession(scene, freezeBinding: true)) {
      _animationController.stop();
      _handlePanCancel();
      return;
    }
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
    _activeTextureSession = null;
    _lastAnimationFrameIndex = -1;
    _queueCurrentTextureWindow();
    if (mounted) {
      setState(() {});
    }
  }

  bool _prepareTextureSession(
    PageflipBookIsolatedScene scene, {
    required bool freezeBinding,
  }) {
    final binding = scene.sheetBinding;
    if (binding == null || !_shadersReady) {
      return false;
    }
    final bundle = _resolveTextureBundle(binding);
    _activeTextureSession = resolvePageflipBookIsolatedTextureSession(
      existing: _activeTextureSession,
      binding: binding,
      resolvedBundle: bundle,
      freezeBinding: freezeBinding,
    );
    return _activeTextureSession?.isReadyForMesh ?? false;
  }

  ArticlePageTextureBundle? _resolveTextureBundle(
    PageflipBookIsolatedSheetBinding binding,
  ) {
    final recto = _pageSnapshots[binding.rectoPageIndex];
    final verso = _pageSnapshots[binding.versoPageIndex];
    final bottom = _pageSnapshots[binding.bottomPageIndex];
    for (final index in binding.prioritizedPageIndices) {
      if (_pageSnapshots.containsKey(index) ||
          _pendingCaptureIndices.contains(index)) {
        continue;
      }
      _pendingCaptureIndices.add(index);
    }
    if (recto == null || verso == null || bottom == null) {
      return null;
    }
    return ArticlePageTextureBundle(recto: recto, verso: verso, bottom: bottom);
  }

  bool _isDirectionReady(PageflipBookIsolatedDirection direction) {
    if (!_shadersReady) {
      return false;
    }
    for (final pageIndex in _controller.textureWindowForDirection(direction)) {
      if (!_pageSnapshots.containsKey(pageIndex)) {
        if (!_pendingCaptureIndices.contains(pageIndex)) {
          _pendingCaptureIndices.add(pageIndex);
          _scheduleCapture();
        }
        return false;
      }
    }
    return true;
  }

  bool get _shadersReady =>
      _lightingProgram != null && _backfaceProgram != null;

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
      setState(() {
        _lightingProgram = lighting;
        _backfaceProgram = backface;
      });
    } catch (_) {
      // 隔离组件不提供用户可见 fallback；shader 未就绪时直接阻止翻页启动。
    }
  }

  void _scheduleCapture() {
    if (_captureScheduled) {
      return;
    }
    _captureScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _captureScheduled = false;
      unawaited(_capturePendingTextures());
    });
  }

  Future<void> _capturePendingTextures() async {
    final pageSize = _lastPageSize;
    if (!mounted || pageSize == null || _pendingCaptureIndices.isEmpty) {
      return;
    }
    final pixelRatio =
        WidgetsBinding.instance.platformDispatcher.views.first.devicePixelRatio;
    final pendingNow = _pendingCaptureIndices.toList(growable: false);
    for (final pageIndex in pendingNow) {
      final boundaryKey = _captureBoundaryKeys[pageIndex];
      final boundaryContext = boundaryKey?.currentContext;
      final boundary =
          boundaryContext?.findRenderObject() as RenderRepaintBoundary?;
      if (boundary == null || boundary.debugNeedsPaint) {
        _scheduleCapture();
        return;
      }
      final image = await boundary.toImage(pixelRatio: pixelRatio);
      final retired = _pageSnapshots.remove(pageIndex);
      if (retired != null) {
        _retiredSnapshots.add(retired);
      }
      _pageSnapshots[pageIndex] = ArticlePageTextureSnapshot(
        image: image,
        logicalSize: pageSize,
        pixelRatio: pixelRatio,
      );
      _pendingCaptureIndices.remove(pageIndex);
      if (!mounted) {
        return;
      }
    }
    if (mounted) {
      setState(() {});
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

class _RelativePathClipper extends CustomClipper<Path> {
  const _RelativePathClipper(this.path);

  final Path path;

  @override
  Path getClip(Size size) => path;

  @override
  bool shouldReclip(covariant _RelativePathClipper oldClipper) {
    return oldClipper.path != path;
  }
}
