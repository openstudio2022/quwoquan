import 'dart:async';
import 'dart:collection';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_engine.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_mode.dart';
import 'package:quwoquan_app/components/pageflip/src/render/pageflip_render_frame.dart';
import 'package:quwoquan_app/components/pageflip/src/scene/pageflip_scene.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_renderer.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

typedef PageflipPageBuilder = Widget Function(
  BuildContext context,
  int pageIndex,
);

@immutable
class PageflipWidget extends StatefulWidget {
  const PageflipWidget({
    super.key,
    required this.engine,
    required this.pageBuilder,
    this.pageAspectRatio = 0.72,
    this.stagePadding = const EdgeInsets.all(AppSpacing.containerSm),
    this.stageColor,
    this.onPageChanged,
    this.onSceneChanged,
  });

  final PageflipEngine engine;
  final PageflipPageBuilder pageBuilder;
  final double pageAspectRatio;
  final EdgeInsets stagePadding;
  final Color? stageColor;
  final ValueChanged<int>? onPageChanged;
  final ValueChanged<PageflipScene>? onSceneChanged;

  @override
  State<PageflipWidget> createState() => _PageflipWidgetState();
}

class _PageflipWidgetState extends State<PageflipWidget> {
  final ArticlePageCurlMeshBuilder _meshBuilder =
      const ArticlePageCurlMeshBuilder();
  final Map<int, GlobalKey> _captureBoundaryKeys = <int, GlobalKey>{};
  final Map<int, ArticlePageTextureSnapshot> _pageSnapshots =
      <int, ArticlePageTextureSnapshot>{};
  final List<ArticlePageTextureSnapshot> _retiredSnapshots =
      <ArticlePageTextureSnapshot>[];
  final ListQueue<int> _pendingCaptureIndices = ListQueue<int>();
  ArticlePageTextureSession? _textureSession;

  Size? _lastStageSize;
  Size? _lastPageSize;
  bool _captureScheduled = false;
  bool _dragActive = false;
  ui.FragmentProgram? _lightingProgram;
  ui.FragmentProgram? _backfaceProgram;
  String? _lastReportedSceneSignature;

  @override
  void initState() {
    super.initState();
    unawaited(_loadShaders());
  }

  @override
  void didUpdateWidget(covariant PageflipWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.pageBuilder != widget.pageBuilder ||
        oldWidget.pageAspectRatio != widget.pageAspectRatio ||
        oldWidget.stagePadding != widget.stagePadding ||
        oldWidget.engine != widget.engine) {
      _clearAllSnapshots();
      _dragActive = false;
      _resetDragTracking();
      _textureSession = null;
    }
  }

  @override
  void dispose() {
    _clearAllSnapshots();
    _disposeRetiredSnapshots();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final isDark = Theme.of(context).brightness == Brightness.dark;
        final stageColor = widget.stageColor ??
            AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
        final stageSize = Size(
          constraints.maxWidth.isFinite ? constraints.maxWidth : 0,
          constraints.maxHeight.isFinite ? constraints.maxHeight : 0,
        );
        if (stageSize.width <= 0 || stageSize.height <= 0) {
          return const SizedBox.expand();
        }

        final pageSize = _resolvePageSize(stageSize);
        _updateViewport(stageSize: stageSize, pageSize: pageSize);

        final scene = widget.engine.buildScene(stageSize);
        if (scene == null) {
          return ColoredBox(color: stageColor);
        }

        final textureBinding = _resolveTextureBinding(scene);
        _textureSession = _resolveTextureSession(scene, textureBinding);
        _queueSceneTextureWindow(scene, textureBinding);
        if (_pendingCaptureIndices.isNotEmpty) {
          _scheduleCapture();
        }

        final renderScene = _buildRenderScene(scene);
        _reportScene(scene);
        final staticPageIndex = scene.isInteractive && scene.underlayPageIndex != null
            ? scene.underlayPageIndex!
            : scene.currentPageIndex;

        return ColoredBox(
          color: stageColor,
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              _buildStaticPage(context, scene.pageRect, staticPageIndex),
              if (renderScene != null)
                Positioned.fill(
                  child: IgnorePointer(
                    child: ArticlePageCurlRenderer(
                      key: const ValueKey('pageflip_curl_renderer'),
                      scene: renderScene,
                      lightingProgram:
                          renderScene.direction == StPageFlipDirection.forward
                              ? null
                              : _lightingProgram,
                      backfaceProgram:
                          renderScene.direction == StPageFlipDirection.forward
                              ? null
                              : _backfaceProgram,
                    ),
                  ),
                ),
              Positioned.fill(child: _buildGestureLayer(scene)),
              if (_pendingCaptureIndices.isNotEmpty)
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

  void _reportScene(PageflipScene scene) {
    final signature = _sceneSignature(scene);
    if (signature == _lastReportedSceneSignature) {
      return;
    }
    _lastReportedSceneSignature = signature;
    widget.onSceneChanged?.call(scene);
  }

  String _sceneSignature(PageflipScene scene) {
    final renderFrame = scene.renderFrame;
    final rect = scene.pageRect;
    final progress = renderFrame?.progress.toStringAsFixed(4) ?? 'none';
    final direction = scene.direction?.name ?? 'idle';
    final renderDirection = renderFrame?.direction.name ?? 'none';
    return [
      scene.currentPageIndex,
      scene.turningPageIndex,
      scene.underlayPageIndex,
      scene.coveredPageIndex,
      direction,
      renderDirection,
      progress,
      rect.left.toStringAsFixed(1),
      rect.top.toStringAsFixed(1),
      rect.width.toStringAsFixed(1),
      rect.height.toStringAsFixed(1),
    ].join('|');
  }

  Widget _buildGestureLayer(PageflipScene scene) {
    final halfWidth = scene.stageSize.width / 2;
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onTapUp: (details) => _handleTap(details.localPosition),
      onPanStart: (details) => _handlePanStart(details.localPosition),
      onPanUpdate: (details) => _handlePanUpdate(details.localPosition),
      onPanEnd: _handlePanEnd,
      onPanCancel: _handlePanCancel,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          const SizedBox.expand(),
          Positioned(
            left: 0,
            top: 0,
            bottom: 0,
            width: halfWidth,
            child: const IgnorePointer(child: SizedBox.expand()),
          ),
          Positioned(
            right: 0,
            top: 0,
            bottom: 0,
            width: halfWidth,
            child: const IgnorePointer(child: SizedBox.expand()),
          ),
        ],
      ),
    );
  }

  Widget _buildStaticPage(BuildContext context, Rect pageRect, int pageIndex) {
    final pageSize = pageRect.size;
    return Align(
      alignment: Alignment.topLeft,
      child: Padding(
        padding: EdgeInsets.only(left: pageRect.left, top: pageRect.top),
        child: SizedBox.fromSize(
          size: pageSize,
          child: KeyedSubtree(
            key: ValueKey<String>('pageflip_static_page_$pageIndex'),
            child: widget.pageBuilder(context, pageIndex),
          ),
        ),
      ),
    );
  }

  Widget _buildCaptureLayer(
    BuildContext context,
    Size pageSize,
    Size stageSize,
  ) {
    final pendingPages = _pendingCaptureIndices.take(3).toList(growable: false);
    if (pendingPages.isEmpty) {
      return const SizedBox.shrink();
    }
    return Transform.translate(
      offset: Offset(
        stageSize.width + pageSize.width + AppSpacing.buttonHeight,
        0,
      ),
      child: _StableTextureCaptureLayer(
        capturePages: pendingPages,
        pageSize: pageSize,
        boundaryKeys: _captureBoundaryKeys,
        buildPage: (pageIndex) => widget.pageBuilder(context, pageIndex),
      ),
    );
  }

  ArticlePageCurlRenderScene? _buildRenderScene(PageflipScene scene) {
    final renderFrame = scene.renderFrame;
    if (!scene.isInteractive || renderFrame == null) {
      return null;
    }
    final textureBinding = _resolveTextureBinding(scene);
    final bundle = _textureBundleForScene(scene, textureBinding);
    if (bundle == null) {
      return null;
    }

    final meshFrame = _meshBuilder.build(
      pageRect: scene.pageRect,
      pageSize: scene.pageSize,
      dragPoint: renderFrame.canonicalFrame.localPagePoint,
      progress: renderFrame.progress,
      direction: renderFrame.direction == PageflipDirection.forward
          ? StPageFlipDirection.forward
          : StPageFlipDirection.back,
      corner: renderFrame.canonicalFrame.corner == PageflipCorner.top
          ? StPageFlipCorner.top
          : StPageFlipCorner.bottom,
      reversePose: renderFrame.canonicalFrame.reversePose,
      renderFrame: renderFrame.canonicalFrame,
      deriveBottomClipPathFromMesh: true,
    );
    final lightState = resolveArticlePageCurlLightState(
      progress: meshFrame.progress,
      foldXNormalized: meshFrame.foldXNormalized,
      curlLift: meshFrame.curlLift,
      rollProgress: meshFrame.rollProgress,
      cylinderProgress: meshFrame.cylinderProgress,
      unfoldProgress: meshFrame.unfoldProgress,
      cylinderRadiusNormalized:
          renderFrame.canonicalFrame.timeline.cylinderRadiusNormalized,
      unrollWidthNormalized:
          renderFrame.canonicalFrame.timeline.unrollWidthNormalized,
      bottomGapNormalized:
          renderFrame.canonicalFrame.timeline.bottomGapNormalized,
      direction: renderFrame.direction == PageflipDirection.forward
          ? StPageFlipDirection.forward
          : StPageFlipDirection.back,
      corner: renderFrame.canonicalFrame.corner == PageflipCorner.top
          ? StPageFlipCorner.top
          : StPageFlipCorner.bottom,
    );
    return ArticlePageCurlRenderScene(
      stageSize: scene.stageSize,
      pageRect: scene.pageRect,
      textures: bundle,
      meshFrame: meshFrame,
      lightConfig: _resolveLightConfig(),
      lightState: lightState,
      direction: renderFrame.direction == PageflipDirection.forward
          ? StPageFlipDirection.forward
          : StPageFlipDirection.back,
      corner: renderFrame.canonicalFrame.corner == PageflipCorner.top
          ? StPageFlipCorner.top
          : StPageFlipCorner.bottom,
      renderConfig: renderFrame.direction == PageflipDirection.forward
          ? const ArticlePageCurlRenderConfig(
              enableBackPaperWash: false,
              enableBackCreaseOcclusion: false,
              enableBottomProjection: false,
              enableSpineAmbient: false,
            )
          : const ArticlePageCurlRenderConfig(),
    );
  }

  ArticlePageCurlLightConfig _resolveLightConfig() {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return ArticlePageCurlLightConfig(
      shadowColor: AppColors.black.withValues(alpha: isDark ? 0.36 : 0.12),
      highlightColor: AppColors.white.withValues(alpha: isDark ? 0.15 : 0.38),
      paperTintColor: AppColorsFunctional.getColor(
        isDark,
        ColorType.backgroundTertiary,
      ),
      ambientOcclusionColor: AppColors.black.withValues(
        alpha: isDark ? 0.16 : 0.08,
      ),
    );
  }

  ArticlePageTextureBinding? _resolveTextureBinding(PageflipScene scene) {
    final renderFrame = scene.renderFrame;
    final roleState = scene.roleState;
    if (renderFrame == null || roleState == null) {
      return null;
    }

    final flippingPageIndex = scene.turningPageIndex;
    final bottomPageIndex = renderFrame.direction == PageflipDirection.forward
        ? scene.underlayPageIndex
        : scene.currentPageIndex;
    if (flippingPageIndex == null || bottomPageIndex == null) {
      return null;
    }

    return resolveArticlePageTextureBinding(
      direction:
          renderFrame.direction == PageflipDirection.forward
              ? StPageFlipDirection.forward
              : StPageFlipDirection.back,
      flippingPageIndex: flippingPageIndex,
      bottomPageIndex: bottomPageIndex,
      currentPageIndex: scene.currentPageIndex,
    );
  }

  ArticlePageTextureSession? _resolveTextureSession(
    PageflipScene scene,
    ArticlePageTextureBinding? binding,
  ) {
    if (binding == null) {
      return null;
    }
    final bundle = _textureBundleForScene(scene, binding);
    return resolveArticlePageTextureSession(
      existing: _textureSession,
      binding: binding,
      resolvedBundle: bundle,
      supportsHighFidelity: true,
      freezeBinding: scene.isInteractive,
    );
  }

  ArticlePageTextureBundle? _textureBundleForScene(
    PageflipScene scene,
    ArticlePageTextureBinding? binding,
  ) {
    final renderFrame = scene.renderFrame;
    if (renderFrame == null || binding == null) {
      return null;
    }

    if (binding.direction == StPageFlipDirection.forward) {
      final recto = _snapshotForIndex(binding.rectoPageIndex);
      final verso = _snapshotForIndex(binding.versoPageIndex);
      final bottom = _snapshotForIndex(binding.bottomPageIndex);
      if (recto == null || verso == null || bottom == null) {
        return null;
      }
      return ArticlePageTextureBundle(
        recto: recto,
        verso: verso,
        bottom: bottom,
      );
    }

    final covered = _snapshotForIndex(binding.bottomPageIndex);
    final leafRecto = _snapshotForIndex(binding.rectoPageIndex);
    final leafVerso = _snapshotForIndex(binding.versoPageIndex);
    if (covered == null || leafRecto == null || leafVerso == null) {
      return null;
    }
    return ArticleBackwardPageTextureBundle(
      covered: covered,
      leafRecto: leafRecto,
      leafVerso: leafVerso,
    ).toCurlTextureBundle();
  }

  ArticlePageTextureSnapshot? _snapshotForIndex(int index) {
    return _pageSnapshots[index];
  }

  void _queueSceneTextureWindow(
    PageflipScene scene,
    ArticlePageTextureBinding? binding,
  ) {
    final indices = binding?.prioritizedPageIndices ??
        _textureSession?.binding.prioritizedPageIndices ??
        scene.roleState?.prioritizedPageIndices ??
        <int>[scene.currentPageIndex];
    _queueTextureIndices(indices);
  }

  void _queueTextureIndices(
    Iterable<int> pageIndices, {
    bool prioritize = false,
  }) {
    var added = false;
    final orderedIndices = pageIndices.toList(growable: false);
    final iteration = prioritize ? orderedIndices.reversed : orderedIndices;
    for (final pageIndex in iteration) {
      if (pageIndex < 0) {
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
        () => GlobalKey(debugLabel: 'pageflip_capture_$pageIndex'),
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
    widget.engine.updateViewport(stageSize: stageSize, pageSize: pageSize);
  }

  Size _resolvePageSize(Size stageSize) {
    final paddedWidth =
        (stageSize.width - widget.stagePadding.horizontal).clamp(1.0, double.infinity);
    final paddedHeight =
        (stageSize.height - widget.stagePadding.vertical).clamp(1.0, double.infinity);
    var width = paddedWidth;
    var height = width / widget.pageAspectRatio;
    if (height > paddedHeight) {
      height = paddedHeight;
      width = height * widget.pageAspectRatio;
    }
    return Size(width, height);
  }

  void _handleTap(Offset localPosition) {
    if (_dragActive) {
      return;
    }
    final stageWidth = _lastStageSize?.width ?? 0;
    final direction = localPosition.dx < stageWidth / 2
        ? PageflipDirection.back
        : PageflipDirection.forward;
    _startProgrammaticFlip(direction);
  }

  void _handlePanStart(Offset localPosition) {
    if (!_validateStart(localPosition)) {
      return;
    }
    _dragActive = true;
    widget.engine.fold(localPosition);
    setState(() {});
  }

  void _handlePanUpdate(Offset localPosition) {
    if (!_dragActive) {
      return;
    }
    widget.engine.fold(localPosition);
    setState(() {});
  }

  void _handlePanEnd(DragEndDetails details) {
    if (!_dragActive) {
      return;
    }
    _dragActive = false;
    final plan = widget.engine.stopMove(details.velocity);
    _resetDragTracking();
    if (plan.commitsTurn) {
      widget.engine.settleToIndex(plan.targetPageIndex);
      widget.onPageChanged?.call(plan.targetPageIndex);
    }
    if (mounted) {
      setState(() {});
    }
  }

  void _handlePanCancel() {
    _dragActive = false;
    widget.engine.stopMove(const Velocity(pixelsPerSecond: Offset.zero));
    if (mounted) {
      setState(() {});
    }
  }

  bool _validateStart(Offset localPosition) {
    if (_lastStageSize == null) {
      return false;
    }
    return widget.engine.start(localPosition);
  }

  void _startProgrammaticFlip(PageflipDirection direction) {
    final stageWidth = _lastStageSize?.width ?? 0;
    if (stageWidth <= 0) {
      return;
    }
    final localPosition = direction == PageflipDirection.forward
        ? Offset(
            stageWidth - AppSpacing.xs,
            (_lastStageSize?.height ?? 0) / 2,
          )
        : Offset(
            AppSpacing.xs,
            (_lastStageSize?.height ?? 0) / 2,
          );
    if (!widget.engine.start(localPosition)) {
      return;
    }
    widget.engine.fold(localPosition);
    final plan = widget.engine.stopMove(
      Velocity(pixelsPerSecond: Offset(direction == PageflipDirection.forward
          ? 420
          : -420, 0)),
    );
    if (plan.commitsTurn) {
      widget.engine.settleToIndex(plan.targetPageIndex);
      widget.onPageChanged?.call(plan.targetPageIndex);
    }
    if (mounted) {
      setState(() {});
    }
  }

  void _resetDragTracking() {
  }

  void _scheduleCapture() {
    if (_captureScheduled ||
        _pendingCaptureIndices.isEmpty ||
        !mounted ||
        _lastPageSize == null) {
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
    return pixelRatio.clamp(1.0, double.infinity).toDouble();
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
      setState(() {});
    } catch (_) {
      // Shader is optional; the canonical renderer still runs without it.
    }
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

class _StableTextureCaptureLayerState extends State<_StableTextureCaptureLayer> {
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
          .map(
            (index) => RepaintBoundary(
              key: widget.boundaryKeys.putIfAbsent(
                index,
                () => GlobalKey(debugLabel: 'pageflip_capture_$index'),
              ),
              child: SizedBox(
                width: widget.pageSize.width,
                height: widget.pageSize.height,
                child: _cachedWidgets[index] ?? const SizedBox.shrink(),
              ),
            ),
          )
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
