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
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_renderer.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

typedef PageflipPageBuilder =
    Widget Function(BuildContext context, int pageIndex);

@immutable
class PageflipWidgetDebugState {
  const PageflipWidgetDebugState({
    required this.currentPageIndex,
    required this.turningPageIndex,
    required this.underlayPageIndex,
    required this.coveredPageIndex,
    required this.staticPageIndex,
    required this.renderDirection,
    required this.meshReady,
    required this.renderSceneReady,
    required this.sessionHasBundle,
    required this.sessionPrefersHighFidelity,
    required this.requestedRectoPageIndex,
    required this.requestedVersoPageIndex,
    required this.requestedBottomPageIndex,
    required this.activeRectoPageIndex,
    required this.activeVersoPageIndex,
    required this.activeBottomPageIndex,
    required this.bottomClipBounds,
    required this.frontBounds,
    required this.backBounds,
    required this.spineDelta,
    required this.seamDelta,
    required this.availableSnapshotIndices,
    required this.missingSnapshotIndices,
    required this.pendingCaptureIndices,
  });

  final int currentPageIndex;
  final int? turningPageIndex;
  final int? underlayPageIndex;
  final int? coveredPageIndex;
  final int staticPageIndex;
  final PageflipDirection? renderDirection;
  final bool meshReady;
  final bool renderSceneReady;
  final bool sessionHasBundle;
  final bool sessionPrefersHighFidelity;
  final int? requestedRectoPageIndex;
  final int? requestedVersoPageIndex;
  final int? requestedBottomPageIndex;
  final int? activeRectoPageIndex;
  final int? activeVersoPageIndex;
  final int? activeBottomPageIndex;
  final Rect? bottomClipBounds;
  final Rect? frontBounds;
  final Rect? backBounds;
  final double? spineDelta;
  final double? seamDelta;
  final List<int> availableSnapshotIndices;
  final List<int> missingSnapshotIndices;
  final List<int> pendingCaptureIndices;

  String get signature => [
    currentPageIndex,
    turningPageIndex ?? 'null',
    underlayPageIndex ?? 'null',
    coveredPageIndex ?? 'null',
    staticPageIndex,
    renderDirection?.name ?? 'null',
    meshReady,
    renderSceneReady,
    sessionHasBundle,
    sessionPrefersHighFidelity,
    requestedRectoPageIndex ?? 'null',
    requestedVersoPageIndex ?? 'null',
    requestedBottomPageIndex ?? 'null',
    activeRectoPageIndex ?? 'null',
    activeVersoPageIndex ?? 'null',
    activeBottomPageIndex ?? 'null',
    _rectSignature(bottomClipBounds),
    _rectSignature(frontBounds),
    _rectSignature(backBounds),
    spineDelta?.toStringAsFixed(4) ?? 'null',
    seamDelta?.toStringAsFixed(4) ?? 'null',
    availableSnapshotIndices.join(','),
    missingSnapshotIndices.join(','),
    pendingCaptureIndices.join(','),
  ].join('|');

  static String _rectSignature(Rect? rect) {
    if (rect == null) {
      return 'null';
    }
    return [
      rect.left.toStringAsFixed(1),
      rect.top.toStringAsFixed(1),
      rect.right.toStringAsFixed(1),
      rect.bottom.toStringAsFixed(1),
    ].join(',');
  }
}

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
    this.onDebugStateChanged,
  });

  final PageflipEngine engine;
  final PageflipPageBuilder pageBuilder;
  final double pageAspectRatio;
  final EdgeInsets stagePadding;
  final Color? stageColor;
  final ValueChanged<int>? onPageChanged;
  final ValueChanged<PageflipScene>? onSceneChanged;
  final ValueChanged<PageflipWidgetDebugState>? onDebugStateChanged;

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
  bool _captureInFlight = false;
  bool _dragActive = false;
  ui.FragmentProgram? _lightingProgram;
  ui.FragmentProgram? _backfaceProgram;
  String? _lastReportedSceneSignature;
  String? _lastReportedDebugSignature;
  int _viewportCaptureGeneration = 0;

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
      _viewportCaptureGeneration += 1;
      _clearAllSnapshots();
      _dragActive = false;
      _resetDragTracking();
      _textureSession = null;
      _lastStageSize = null;
      _lastPageSize = null;
      _lastReportedSceneSignature = null;
      _lastReportedDebugSignature = null;
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
        final stageColor =
            widget.stageColor ??
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
        final activeBinding = _textureSession?.binding;
        final dynamicallyRenderedPages = renderScene == null
            ? const <int>{}
            : (activeBinding?.requiredPageIndices ?? const <int>{});
        _reportScene(scene);
        final staticPageIndex =
            scene.isInteractive &&
                scene.renderFrame?.direction == PageflipDirection.forward
            ? (scene.coveredPageIndex ?? scene.currentPageIndex)
            : scene.isInteractive && scene.underlayPageIndex != null
            ? scene.underlayPageIndex!
            : scene.currentPageIndex;
        _reportDebugState(
          _buildDebugState(
            scene: scene,
            staticPageIndex: staticPageIndex,
            requestedBinding: textureBinding,
            activeSession: _textureSession,
            renderScene: renderScene,
          ),
        );
        return ColoredBox(
          color: stageColor,
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              if (!dynamicallyRenderedPages.contains(staticPageIndex))
                _buildStaticPage(context, scene.pageRect, staticPageIndex),
              if (renderScene != null)
                Positioned.fill(
                  child: IgnorePointer(
                    child: ArticlePageCurlRenderer(
                      key: const ValueKey('pageflip_curl_renderer'),
                      scene: renderScene,
                      lightingProgram: _lightingProgram,
                      backfaceProgram: _backfaceProgram,
                    ),
                  ),
                ),
              _buildHotzoneAnchors(scene.pageRect),
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

  void _reportDebugState(PageflipWidgetDebugState state) {
    final signature = state.signature;
    if (signature == _lastReportedDebugSignature) {
      return;
    }
    _lastReportedDebugSignature = signature;
    widget.onDebugStateChanged?.call(state);
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

  PageflipWidgetDebugState _buildDebugState({
    required PageflipScene scene,
    required int staticPageIndex,
    required ArticlePageTextureBinding? requestedBinding,
    required ArticlePageTextureSession? activeSession,
    required ArticlePageCurlRenderScene? renderScene,
  }) {
    final availableSnapshotIndices = _pageSnapshots.keys.toList()..sort();
    final activeBinding = activeSession?.binding;
    final requestedIndices = <int>{
      if (requestedBinding?.rectoPageIndex case final recto?) recto,
      if (requestedBinding?.versoPageIndex case final verso?) verso,
      if (requestedBinding?.bottomPageIndex case final bottom?) bottom,
    }.toList()..sort();
    final missingSnapshotIndices = requestedIndices
        .where((index) => !availableSnapshotIndices.contains(index))
        .toList(growable: false);
    final alignmentDiagnostics = renderScene?.meshFrame.alignmentDiagnostics;
    return PageflipWidgetDebugState(
      currentPageIndex: scene.currentPageIndex,
      turningPageIndex: scene.turningPageIndex,
      underlayPageIndex: scene.underlayPageIndex,
      coveredPageIndex: scene.coveredPageIndex,
      staticPageIndex: staticPageIndex,
      renderDirection: scene.renderFrame?.direction ?? scene.direction,
      meshReady: renderScene != null,
      renderSceneReady: renderScene != null,
      sessionHasBundle: activeSession?.bundle != null,
      sessionPrefersHighFidelity: activeSession?.preferHighFidelity ?? false,
      requestedRectoPageIndex: requestedBinding?.rectoPageIndex,
      requestedVersoPageIndex: requestedBinding?.versoPageIndex,
      requestedBottomPageIndex: requestedBinding?.bottomPageIndex,
      activeRectoPageIndex: activeBinding?.rectoPageIndex,
      activeVersoPageIndex: activeBinding?.versoPageIndex,
      activeBottomPageIndex: activeBinding?.bottomPageIndex,
      bottomClipBounds: renderScene?.meshFrame.bottomClipPath.getBounds(),
      frontBounds: renderScene?.meshFrame.frontBounds,
      backBounds: renderScene?.meshFrame.backBounds,
      spineDelta: alignmentDiagnostics?.spineDelta,
      seamDelta: alignmentDiagnostics?.seamDelta,
      availableSnapshotIndices: List<int>.unmodifiable(
        availableSnapshotIndices,
      ),
      missingSnapshotIndices: List<int>.unmodifiable(missingSnapshotIndices),
      pendingCaptureIndices: List<int>.unmodifiable(
        _pendingCaptureIndices.toList(growable: false),
      ),
    );
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

  Widget _buildHotzoneAnchors(Rect pageRect) {
    const hotzoneSize = 44.0;
    final leftHotzoneLeft = (pageRect.left - hotzoneSize)
        .clamp(0.0, pageRect.left)
        .toDouble();
    return IgnorePointer(
      child: Stack(
        children: <Widget>[
          _buildHotzone(
            key: TestKeys.articlePageCurlHotzoneTopLeft,
            left: leftHotzoneLeft,
            top: pageRect.top,
            size: hotzoneSize,
          ),
          _buildHotzone(
            key: TestKeys.articlePageCurlHotzoneTopRight,
            left: pageRect.right - hotzoneSize,
            top: pageRect.top,
            size: hotzoneSize,
          ),
          _buildHotzone(
            key: TestKeys.articlePageCurlHotzoneBottomLeft,
            left: leftHotzoneLeft,
            top: pageRect.bottom - hotzoneSize,
            size: hotzoneSize,
          ),
          _buildHotzone(
            key: TestKeys.articlePageCurlHotzoneBottomRight,
            left: pageRect.right - hotzoneSize,
            top: pageRect.bottom - hotzoneSize,
            size: hotzoneSize,
          ),
        ],
      ),
    );
  }

  Widget _buildHotzone({
    required Key key,
    required double left,
    required double top,
    required double size,
  }) {
    return Positioned(
      left: left,
      top: top,
      width: size,
      height: size,
      child: SizedBox(key: key, width: size, height: size),
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
    assert(
      bundle.recto.matchesLogicalSize(scene.pageSize) &&
          bundle.verso.matchesLogicalSize(scene.pageSize) &&
          bundle.bottom.matchesLogicalSize(scene.pageSize),
      'Pageflip textures must match scene.pageSize for consistent scaling.',
    );
    final isForward = renderFrame.direction == PageflipDirection.forward;
    final renderDirection = renderFrame.direction == PageflipDirection.forward
        ? StPageFlipDirection.forward
        : StPageFlipDirection.back;
    final canonicalCorner = renderFrame.canonicalFrame.corner;
    final renderConfig = isForward
        ? const ArticlePageCurlRenderConfig()
        : const ArticlePageCurlRenderConfig(
            enableBackPaperWash: true,
            enableBackCreaseOcclusion: true,
            enableBottomProjection: false,
            enableSpineAmbient: false,
          );

    final canonicalBottomClipPath = isForward
        ? _buildBottomClipPath(
            pageRect: scene.pageRect,
            area: renderFrame.canonicalFrame.bottomClipArea,
            anchor: renderFrame.canonicalFrame.bottomAnchor,
          )
        : _buildRevealClipPath(
            pageRect: scene.pageRect,
            area: renderFrame.canonicalFrame.bottomClipArea,
          );
    final meshFrame = _meshBuilder.build(
      pageRect: scene.pageRect,
      pageSize: scene.pageSize,
      dragPoint: renderFrame.canonicalFrame.localPagePoint,
      progress: renderFrame.progress,
      direction: renderDirection,
      corner: canonicalCorner,
      bottomClipPath: canonicalBottomClipPath,
      reversePose: renderFrame.canonicalFrame.reversePose,
      renderFrame: renderFrame.canonicalFrame,
      deriveBottomClipPathFromMesh: canonicalBottomClipPath == null,
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
      direction: renderDirection,
      corner: canonicalCorner,
    );
    return ArticlePageCurlRenderScene(
      stageSize: scene.stageSize,
      pageRect: scene.pageRect,
      textures: bundle,
      meshFrame: meshFrame,
      lightConfig: _resolveLightConfig(),
      lightState: lightState,
      direction: renderDirection,
      corner: canonicalCorner,
      renderConfig: renderConfig,
    );
  }

  Path? _buildRevealClipPath({
    required Rect pageRect,
    required List<Offset> area,
  }) {
    final pageRectPath = Path()..addRect(pageRect);
    if (area.length < 3) {
      return pageRectPath;
    }
    final path = Path()
      ..moveTo(pageRect.left + area.first.dx, pageRect.top + area.first.dy);
    for (final point in area.skip(1)) {
      path.lineTo(pageRect.left + point.dx, pageRect.top + point.dy);
    }
    path.close();
    return Path.combine(PathOperation.intersect, pageRectPath, path);
  }

  Path _buildBottomClipPath({
    required Rect pageRect,
    required List<Offset> area,
    required Offset anchor,
  }) {
    final pageRectPath = Path()..addRect(pageRect);
    if (area.length < 3) {
      return pageRectPath;
    }
    final polygon = area
        .map((point) => Offset(point.dx - anchor.dx, point.dy - anchor.dy))
        .toList(growable: false);
    final position = Offset(
      pageRect.left + anchor.dx,
      pageRect.top + anchor.dy,
    );
    final path = Path()
      ..moveTo(position.dx + polygon.first.dx, position.dy + polygon.first.dy);
    for (final point in polygon.skip(1)) {
      path.lineTo(position.dx + point.dx, position.dy + point.dy);
    }
    path.close();
    return Path.combine(PathOperation.intersect, pageRectPath, path);
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
        : (scene.coveredPageIndex ?? scene.currentPageIndex);
    if (flippingPageIndex == null || bottomPageIndex == null) {
      return null;
    }

    return resolveArticlePageTextureBinding(
      direction: renderFrame.direction == PageflipDirection.forward
          ? StPageFlipDirection.forward
          : StPageFlipDirection.back,
      flippingPageIndex: flippingPageIndex,
      bottomPageIndex: bottomPageIndex,
      currentPageIndex: scene.coveredPageIndex ?? scene.currentPageIndex,
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
    final nextSession = resolveArticlePageTextureSession(
      existing: _textureSession,
      binding: binding,
      resolvedBundle: bundle,
      supportsHighFidelity: true,
      freezeBinding: scene.isInteractive,
    );
    return nextSession?.copyWith(preferHighFidelity: true);
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
      final recto = _validSnapshotForIndex(
        binding.rectoPageIndex,
        expectedSize: scene.pageSize,
      );
      final verso = _validSnapshotForIndex(
        binding.versoPageIndex,
        expectedSize: scene.pageSize,
      );
      final bottom = _validSnapshotForIndex(
        binding.bottomPageIndex,
        expectedSize: scene.pageSize,
      );
      if (recto == null || verso == null || bottom == null) {
        return null;
      }
      return ArticlePageTextureBundle(
        recto: recto,
        verso: verso,
        bottom: bottom,
      );
    }

    final covered = _validSnapshotForIndex(
      binding.bottomPageIndex,
      expectedSize: scene.pageSize,
    );
    final leafRecto = _validSnapshotForIndex(
      binding.rectoPageIndex,
      expectedSize: scene.pageSize,
    );
    final leafVerso = _validSnapshotForIndex(
      binding.versoPageIndex,
      expectedSize: scene.pageSize,
    );
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

  ArticlePageTextureSnapshot? _validSnapshotForIndex(
    int index, {
    required Size expectedSize,
  }) {
    final snapshot = _pageSnapshots[index];
    if (snapshot == null) {
      return null;
    }
    if (snapshot.matchesLogicalSize(expectedSize)) {
      return snapshot;
    }
    final retired = _pageSnapshots.remove(index);
    if (retired != null) {
      _retiredSnapshots.add(retired);
    }
    _queueTextureIndices(<int>[index], prioritize: true);
    return null;
  }

  void _queueSceneTextureWindow(
    PageflipScene scene,
    ArticlePageTextureBinding? binding,
  ) {
    final indices =
        binding?.prioritizedPageIndices ??
        _textureSession?.binding.prioritizedPageIndices ??
        scene.roleState?.prioritizedPageIndices ??
        <int>[
          scene.currentPageIndex,
          (scene.currentPageIndex + 1),
          (scene.currentPageIndex - 1),
        ];
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
      if (pageIndex >= widget.engine.pageCount) {
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
    final hadViewport = _lastStageSize != null && _lastPageSize != null;
    if (hadViewport) {
      _viewportCaptureGeneration += 1;
      _clearAllSnapshots();
      _textureSession = null;
      _lastReportedSceneSignature = null;
      _lastReportedDebugSignature = null;
    }
    _lastStageSize = stageSize;
    _lastPageSize = pageSize;
    widget.engine.updateViewport(stageSize: stageSize, pageSize: pageSize);
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
        ? Offset(stageWidth - AppSpacing.xs, (_lastStageSize?.height ?? 0) / 2)
        : Offset(AppSpacing.xs, (_lastStageSize?.height ?? 0) / 2);
    if (!widget.engine.start(localPosition)) {
      return;
    }
    widget.engine.fold(localPosition);
    final plan = widget.engine.stopMove(
      Velocity(
        pixelsPerSecond: Offset(
          direction == PageflipDirection.forward ? 420 : -420,
          0,
        ),
      ),
    );
    if (plan.commitsTurn) {
      widget.engine.settleToIndex(plan.targetPageIndex);
      widget.onPageChanged?.call(plan.targetPageIndex);
    }
    if (mounted) {
      setState(() {});
    }
  }

  void _resetDragTracking() {}

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
      _captureInFlight = false;
      return;
    }
    final pendingNow = _pendingCaptureIndices.take(3).toList(growable: false);
    var capturedAny = false;
    try {
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
        final expectedGeneration = _viewportCaptureGeneration;
        final expectedPageSize = _lastPageSize;
        final logicalSize = boundary.size;
        final pixelRatio = _capturePixelRatio(boundaryContext);
        try {
          final image = await boundary.toImage(pixelRatio: pixelRatio);
          if (!mounted) {
            image.dispose();
            return;
          }
          final isStaleCapture =
              expectedPageSize == null ||
              expectedGeneration != _viewportCaptureGeneration ||
              !_sizeEquals(expectedPageSize, logicalSize) ||
              !_sizeEquals(boundary.size, logicalSize) ||
              !identical(_captureBoundaryKeys[pageIndex], boundaryKey);
          if (isStaleCapture) {
            image.dispose();
            continue;
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
    } finally {
      _captureInFlight = false;
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
