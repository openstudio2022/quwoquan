import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/pageflip/src/debug/pageflip_diagnostics_shared.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

class PageflipDiagnosticsApp extends StatefulWidget {
  const PageflipDiagnosticsApp({super.key, this.showDebugOverlay = false});

  final bool showDebugOverlay;

  @override
  State<PageflipDiagnosticsApp> createState() => _PageflipDiagnosticsAppState();
}

class _PageflipDiagnosticsAppState extends State<PageflipDiagnosticsApp> {
  late final _pages = buildPageflipDiagnosticPages();
  final ValueNotifier<StPageFlipScene?> _sceneNotifier =
      ValueNotifier<StPageFlipScene?>(null);
  final ValueNotifier<ArticleReadOnlyBookDebugState?> _debugNotifier =
      ValueNotifier<ArticleReadOnlyBookDebugState?>(null);
  StPageFlipScene? _pendingScene;
  bool _sceneUpdateScheduled = false;
  ArticleReadOnlyBookDebugState? _pendingDebugState;
  bool _debugUpdateScheduled = false;
  String? _lastLoggedSceneSignature;
  String? _lastLoggedDebugSignature;

  @override
  void dispose() {
    _sceneNotifier.dispose();
    _debugNotifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = resolveArticleTemplatePalette(
      context,
      ArticleTemplatePreset.tech,
    );
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: AppScaffold(
        body: ColoredBox(
          color: palette.paperColor,
          child: LayoutBuilder(
            builder: (context, constraints) {
              final metrics = resolveArticleCanvasMetrics(
                context,
                constraints,
                variant: ArticleCanvasVariant.detail,
              );
              final pagePadding = articleReaderStagePagePadding();
              return Column(
                children: [
                  Expanded(
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        Padding(
                          padding: kPageflipDiagnosticsViewportPadding,
                          child: ArticleReadOnlyBookDeck(
                            pages: _pages,
                            template: kPageflipDiagnosticsTemplate,
                            fontPreset: kPageflipDiagnosticsFontPreset,
                            metrics: metrics,
                            pagePadding: pagePadding,
                            initialPage: 2,
                            coverUrl: '',
                            showFooterPageLabel: true,
                            debugPureBackwardGeometry: true,
                            onSceneChanged: (scene) {
                              _pendingScene = scene;
                              if (_sceneUpdateScheduled) {
                                return;
                              }
                              _sceneUpdateScheduled = true;
                              WidgetsBinding.instance.addPostFrameCallback((_) {
                                _sceneUpdateScheduled = false;
                                if (!mounted || _pendingScene == null) {
                                  return;
                                }
                                final nextScene = _pendingScene;
                                _pendingScene = null;
                                if (nextScene == null) {
                                  return;
                                }
                                _sceneNotifier.value = nextScene;
                                _logScene(nextScene);
                              });
                            },
                            onDebugStateChanged: (debugState) {
                              _pendingDebugState = debugState;
                              if (_debugUpdateScheduled) {
                                return;
                              }
                              _debugUpdateScheduled = true;
                              WidgetsBinding.instance.addPostFrameCallback((_) {
                                _debugUpdateScheduled = false;
                                if (!mounted || _pendingDebugState == null) {
                                  return;
                                }
                                final nextDebugState = _pendingDebugState;
                                _pendingDebugState = null;
                                if (nextDebugState == null) {
                                  return;
                                }
                                _debugNotifier.value = nextDebugState;
                                _logDebugState(nextDebugState);
                              });
                            },
                          ),
                        ),
                        if (widget.showDebugOverlay) ...<Widget>[
                          Positioned.fill(
                            child: IgnorePointer(
                              child:
                                  ValueListenableBuilder<
                                    ArticleReadOnlyBookDebugState?
                                  >(
                                    valueListenable: _debugNotifier,
                                    builder: (context, debugState, _) {
                                      return _DiagnosticsDebugHeader(
                                        debugState: debugState,
                                      );
                                    },
                                  ),
                            ),
                          ),
                          Positioned.fill(
                            child: IgnorePointer(
                              child: ValueListenableBuilder<StPageFlipScene?>(
                                valueListenable: _sceneNotifier,
                                builder: (context, scene, _) {
                                  if (scene == null) {
                                    return const SizedBox.shrink();
                                  }
                                  return ValueListenableBuilder<
                                    ArticleReadOnlyBookDebugState?
                                  >(
                                    valueListenable: _debugNotifier,
                                    builder: (context, debugState, _) {
                                      return _SamplingPointsOverlay(
                                        scene: scene,
                                        debugState: debugState,
                                      );
                                    },
                                  );
                                },
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  void _logScene(StPageFlipScene scene) {
    final renderFrame = scene.renderFrame;
    final progress =
        renderFrame?.progress ??
        ((scene.calculation?.getFlippingProgress() ?? 0) / 100)
            .clamp(0.0, 1.0)
            .toDouble();
    final renderDirection = scene.effectiveRenderDirection;
    final signature = <Object?>[
      scene.currentPageIndex,
      scene.flippingPageIndex,
      scene.bottomPageIndex,
      scene.direction?.name,
      renderDirection?.name,
      progress.toStringAsFixed(3),
    ].join('|');
    if (signature == _lastLoggedSceneSignature) {
      return;
    }
    _lastLoggedSceneSignature = signature;
    debugPrint(
      '[pageflip][scene] '
      'state=${scene.state.name} '
      'cur=${_pageLabel(scene.currentPageIndex)} '
      'turn=${_pageLabel(scene.flippingPageIndex)} '
      'under=${_pageLabel(scene.bottomPageIndex)} '
      'dir=${scene.direction?.name ?? "-"} '
      'render=${renderDirection?.name ?? "-"} '
      'progress=${progress.toStringAsFixed(3)}',
    );
  }

  void _logDebugState(ArticleReadOnlyBookDebugState debugState) {
    final signature = debugState.signature;
    if (signature == _lastLoggedDebugSignature) {
      return;
    }
    _lastLoggedDebugSignature = signature;
    debugPrint(
      '[pageflip][debug] '
      'branch=${debugState.renderBranch.name} '
      'dir=${debugState.renderDirection?.name ?? "-"} '
      'cur=${_pageLabel(debugState.currentPageIndex)} '
      'turn=${_pageLabel(debugState.turningPageIndex)} '
      'under=${_pageLabel(debugState.underlayPageIndex)} '
      'req=${_tripletLabel(debugState.requestedRectoPageIndex, debugState.requestedVersoPageIndex, debugState.requestedBottomPageIndex)} '
      'act=${_tripletLabel(debugState.activeRectoPageIndex, debugState.activeVersoPageIndex, debugState.activeBottomPageIndex)} '
      'leaf=${_tripletLabel(debugState.backwardCoveredPageIndex, debugState.backwardLeafRectoPageIndex, debugState.backwardLeafVersoPageIndex)} '
      'render=${debugState.renderSceneReady} '
      'bundle=${debugState.sessionHasBundle} '
      'guide=${_doubleLabel(debugState.guideX)} '
      'flip=${_rectLabel(debugState.flippingClipBounds)} '
      'clip=${_rectLabel(debugState.bottomClipBounds)} '
      'front=${_rectLabel(debugState.frontBounds)} '
      'back=${_rectLabel(debugState.backBounds)} '
      'corner=${debugState.backwardCorner ?? "-"} '
      'hinge=${_offsetLabel(debugState.backwardHinge)} '
      'spineTop=${_offsetLabel(debugState.backwardSpineTop)} '
      'spineBottom=${_offsetLabel(debugState.backwardSpineBottom)} '
      'seam=${_doubleLabel(debugState.backwardSeamX)} '
      'foldX=${_doubleLabel(debugState.backwardFoldX)} '
      'freeEdgeX=${_doubleLabel(debugState.backwardPageEdgeX)} '
      'freeEdgeSurfaceX=${_doubleLabel(debugState.backwardFoldSurfaceEdgeX)} '
      'foldLine=${_offsetLabel(debugState.backwardFoldLineTop)}>${_offsetLabel(debugState.backwardFoldLineBottom)} '
      'freeEdgeLine=${_offsetLabel(debugState.backwardPageEdgeLineTop)}>${_offsetLabel(debugState.backwardPageEdgeLineBottom)} '
      'freeEdgeSurfaceLine=${_offsetLabel(debugState.backwardFoldSurfaceEdgeLineTop)}>${_offsetLabel(debugState.backwardFoldSurfaceEdgeLineBottom)} '
      'coveredWidth=${_doubleLabel(debugState.backwardCoveredWidth)} '
      'rectoCoverage=${_doubleLabel(debugState.backwardRectoCoverage)} '
      'versoWidth=${_doubleLabel(debugState.backwardVersoWidth)} '
      'rectoWidth=${_doubleLabel(debugState.backwardRectoWidth)} '
      'bottomStart=${_doubleLabel(debugState.backwardBottomStart)} '
      'frontLayers=${debugState.backwardReplayFrontLayerCount ?? "-"} '
      'backSurface=${debugState.backwardReplayBackSurfaceStrategy ?? "-"} '
      'bottomLayer=${_pageLabel(debugState.backwardBottomLayerPageIndex)} '
      'flippingLayer=${_pageLabel(debugState.backwardFlippingLayerPageIndex)} '
      'owned=[${debugState.backwardDynamicOwnedPages.join(",")}] '
      'suppressed=[${debugState.backwardStaticSuppressedPages.join(",")}] '
      'slices=${debugState.backwardReplaySlices ?? "-"} '
      'composite=${debugState.backwardCompositeMode ?? "-"} '
      'paintFront=${_rectLabel(debugState.backwardFrontPaintBounds)} '
      'paintBack=${_rectLabel(debugState.backwardBackPaintBounds)} '
      'paintLaidFront=${_rectLabel(debugState.backwardLaidFrontPaintBounds)} '
      'paintFoldSurface=${_rectLabel(debugState.backwardFoldSurfacePaintBounds)} '
      'currentUnderlay=${_rectLabel(debugState.backwardCurrentResidualBounds)} '
      'paintVerso=${_doubleLabel(debugState.backwardPaintedVersoWidth)} '
      'backPixels=${debugState.backwardBackPixelSurfaceStrategy ?? "-"} '
      'surfaceOrigin=${_offsetLabel(debugState.backwardSurfaceOrigin)} '
      'surfaceRect=${_rectLabel(debugState.backwardSurfaceViewportRect)} '
      'pivotLocal=${_offsetLabel(debugState.backwardPivotLocal)} '
      'pivotViewport=${_offsetLabel(debugState.backwardPivotViewport)} '
      'clipLocal=${_rectLabel(debugState.backwardClipLocalBounds)} '
      'clipViewport=${_rectLabel(debugState.backwardClipViewportBounds)} '
      'frontCover=${_doubleLabel(debugState.backwardFrontCoverageRatio)} '
      'spineLocked=${debugState.backwardLeftSpineLocked ?? "-"} '
      'visualPhase=${debugState.backwardSimulatorVisualPhase ?? "-"} '
      'edgeEntered=${debugState.backwardEdgeEnteredPage ?? "-"} '
      'foldDirection=${debugState.backwardFoldDirection ?? "-"} '
      'overlayClipped=${debugState.backwardOverlayClippedToPaper ?? "-"} '
      'backVertices=${debugState.backwardBackVertexCount ?? "-"} '
      'frontVertices=${debugState.backwardFrontVertexCount ?? "-"} '
      'edgeParallelToFold=${debugState.backwardEdgeParallelToFold ?? "-"} '
      'backPoly=${debugState.backwardBackPolygonPoints ?? "-"} '
      'frontPoly=${debugState.backwardFrontPolygonPoints ?? "-"} '
      'currentPoly=${debugState.backwardCurrentPolygonPoints ?? "-"} '
      'flipAnchor=${_offsetLabel(debugState.flippingAnchor)} '
      'backAnchor=${_offsetLabel(debugState.bottomAnchor)} '
      'phase=${debugState.backwardPhase ?? "-"} '
      'snap=[${debugState.availableSnapshotIndices.join(",")}] '
      'pending=[${debugState.pendingCaptureIndices.join(",")}]',
    );
    if (debugState.renderDirection == StPageFlipDirection.back) {
      debugPrint(
        '[pageflip][paint] '
        'dir=back '
        'paintFront=${_rectLabel(debugState.backwardFrontPaintBounds)} '
        'paintBack=${_rectLabel(debugState.backwardBackPaintBounds)} '
        'paintLaidFront=${_rectLabel(debugState.backwardLaidFrontPaintBounds)} '
        'paintFoldSurface=${_rectLabel(debugState.backwardFoldSurfacePaintBounds)} '
        'currentUnderlay=${_rectLabel(debugState.backwardCurrentResidualBounds)} '
        'rectoWidth=${_doubleLabel(debugState.backwardRectoWidth)} '
        'rectoCoverage=${_doubleLabel(debugState.backwardRectoCoverage)} '
        'versoWidth=${_doubleLabel(debugState.backwardVersoWidth)} '
        'freeEdgeX=${_doubleLabel(debugState.backwardPageEdgeX)} '
        'freeEdgeSurfaceX=${_doubleLabel(debugState.backwardFoldSurfaceEdgeX)} '
        'foldDirection=${debugState.backwardFoldDirection ?? "-"} '
        'spineLocked=${debugState.backwardLeftSpineLocked ?? "-"} '
        'phase=${debugState.backwardPhase ?? "-"}',
      );
    }
  }
}

String _pageLabel(int? pageIndex) =>
    pageIndex == null ? '-' : '${pageIndex + 1}';

String _tripletLabel(int? a, int? b, int? c) {
  return '${_pageLabel(a)}/${_pageLabel(b)}/${_pageLabel(c)}';
}

String _doubleLabel(double? value) => value?.toStringAsFixed(1) ?? '-';

String _offsetLabel(Offset? value) {
  if (value == null) {
    return '-';
  }
  return '${value.dx.toStringAsFixed(1)},${value.dy.toStringAsFixed(1)}';
}

String _rectLabel(Rect? rect) {
  if (rect == null) {
    return '-';
  }
  return [
    rect.left.toStringAsFixed(1),
    rect.top.toStringAsFixed(1),
    rect.right.toStringAsFixed(1),
    rect.bottom.toStringAsFixed(1),
  ].join(',');
}

class _SamplingPointsOverlay extends StatelessWidget {
  const _SamplingPointsOverlay({required this.scene, required this.debugState});

  final StPageFlipScene scene;
  final ArticleReadOnlyBookDebugState? debugState;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final pageRect = resolveBookPageRect(scene.layout, isRightPage: true);
    final foldSample = _foldSamplePoint(pageRect);
    final edgeSample = _edgeSamplePoint(pageRect);
    final seamGuideX = debugState?.guideX;
    final sampleRadius = AppSpacing.iconSmall / 2;
    return Stack(
      children: [
        if (seamGuideX != null)
          Positioned(
            left: seamGuideX - AppSpacing.xs / 4,
            top: pageRect.top,
            child: Container(
              width: AppSpacing.xs / 2,
              height: pageRect.height,
              color: AppColors.error.withValues(alpha: 0.8),
            ),
          ),
        if (debugState?.guideX != null)
          Positioned(
            left: foldSample.dx - sampleRadius,
            top: foldSample.dy - sampleRadius,
            child: _SampleDot(
              label: 'fold',
              color: AppColors.warning,
              isDark: isDark,
            ),
          ),
        Positioned(
          left: edgeSample.dx - sampleRadius,
          top: edgeSample.dy - sampleRadius,
          child: _SampleDot(
            label: 'edge',
            color: AppColors.primaryColor,
            isDark: isDark,
          ),
        ),
      ],
    );
  }

  Offset _foldSamplePoint(Rect pageRect) {
    return Offset(debugState?.guideX ?? pageRect.center.dx, pageRect.center.dy);
  }

  Offset _edgeSamplePoint(Rect pageRect) {
    final direction =
        debugState?.renderDirection ?? scene.effectiveRenderDirection;
    final edgeX = direction == StPageFlipDirection.back
        ? pageRect.left + AppSpacing.iconLarge - AppSpacing.xs / 2
        : pageRect.right - AppSpacing.iconLarge + AppSpacing.xs / 2;
    return Offset(edgeX, pageRect.center.dy);
  }
}

class _DiagnosticsDebugHeader extends StatelessWidget {
  const _DiagnosticsDebugHeader({required this.debugState});

  final ArticleReadOnlyBookDebugState? debugState;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.containerXs,
          AppSpacing.containerXs,
          AppSpacing.containerXs,
          0,
        ),
        child: Align(
          alignment: Alignment.topRight,
          child: debugState == null
              ? const SizedBox.shrink()
              : ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 260),
                  child: _DebugInfoCard(
                    debugState: debugState!,
                    isDark: Theme.of(context).brightness == Brightness.dark,
                  ),
                ),
        ),
      ),
    );
  }
}

class _DebugInfoCard extends StatelessWidget {
  const _DebugInfoCard({required this.debugState, required this.isDark});

  final ArticleReadOnlyBookDebugState debugState;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final background = (isDark ? AppColors.black : AppColors.white).withValues(
      alpha: isDark ? 0.72 : 0.86,
    );
    final textColor = isDark ? AppColors.white : AppColors.black;
    final borderColor = (isDark ? AppColors.white : AppColors.black).withValues(
      alpha: 0.18,
    );
    final isBackward = debugState.renderDirection == StPageFlipDirection.back;
    final overlayFrontRect = isBackward
        ? debugState.backwardFrontPaintBounds ?? debugState.frontBounds
        : debugState.frontBounds;
    final overlayBackRect = isBackward
        ? debugState.backwardBackPaintBounds ?? debugState.backBounds
        : debugState.backBounds;
    final faceSummary = isBackward
        ? 'layers ${debugState.backwardReplayFrontLayerCount ?? "-"} | '
              'recto ${_doubleLabel(debugState.backwardRectoCoverage)} | '
              'verso ${_doubleLabel(debugState.backwardVersoWidth)}'
        : null;
    final polygonSummary = isBackward
        ? 'sheet ${_presenceLabel(debugState.backwardSheetPolygonPoints)} | '
              'front ${_presenceLabel(debugState.backwardFrontPolygonPoints)} | '
              'back ${_presenceLabel(debugState.backwardBackPolygonPoints)} | '
              'bottom ${_presenceLabel(debugState.backwardBottomClipPolygonPoints)}'
        : null;
    return DecoratedBox(
      key: const ValueKey('article_read_only_book_debug_card'),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border.all(color: borderColor, width: AppSpacing.hairline),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.containerXs),
        child: DefaultTextStyle(
          style: TextStyle(
            color: textColor,
            fontSize: AppTypography.iosCaption2,
            height: AppTypography.lineHeightTight,
            fontFamily: 'SF Mono',
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              _DebugLine(
                label: 'scene',
                value:
                    'cur ${_pageLabel(debugState.currentPageIndex)} | turn ${_pageLabel(debugState.turningPageIndex)} | under ${_pageLabel(debugState.underlayPageIndex)} | cover ${_pageLabel(debugState.coveredPageIndex)}',
              ),
              _DebugLine(
                label: 'spread',
                value:
                    'l ${_pageLabel(debugState.leftPageIndex)} | r ${_pageLabel(debugState.rightPageIndex)}',
              ),
              _DebugLine(
                label: 'branch',
                value:
                    '${debugState.renderBranch.name} | dir ${debugState.renderDirection?.name ?? '-'}',
              ),
              _DebugLine(
                label: 'request',
                value:
                    'r ${_pageLabel(debugState.requestedRectoPageIndex)} | v ${_pageLabel(debugState.requestedVersoPageIndex)} | b ${_pageLabel(debugState.requestedBottomPageIndex)}',
              ),
              _DebugLine(
                label: 'active',
                value:
                    'r ${_pageLabel(debugState.activeRectoPageIndex)} | v ${_pageLabel(debugState.activeVersoPageIndex)} | b ${_pageLabel(debugState.activeBottomPageIndex)}',
              ),
              _DebugLine(
                label: 'leaf',
                value:
                    'c ${_pageLabel(debugState.backwardCoveredPageIndex)} | r ${_pageLabel(debugState.backwardLeafRectoPageIndex)} | v ${_pageLabel(debugState.backwardLeafVersoPageIndex)}',
              ),
              _DebugLine(
                label: 'bundle',
                value:
                    '${debugState.renderSceneReady ? 'render' : 'wait'} | ${debugState.sessionHasBundle ? 'session ok' : 'session missing'}',
              ),
              _DebugLine(
                label: 'cache',
                value:
                    'snap [${_pageListLabel(debugState.availableSnapshotIndices)}] | pending [${_pageListLabel(debugState.pendingCaptureIndices)}]',
              ),
              _DebugLine(
                label: 'clip',
                value: _rectLabel(debugState.bottomClipBounds),
              ),
              _DebugLine(label: 'front', value: _rectLabel(overlayFrontRect)),
              _DebugLine(label: 'back', value: _rectLabel(overlayBackRect)),
              if (faceSummary != null)
                _DebugLine(label: 'faces', value: faceSummary),
              if (polygonSummary != null)
                _DebugLine(label: 'polys', value: polygonSummary),
              _DebugLine(
                label: 'guide',
                value: debugState.guideX == null
                    ? '-'
                    : debugState.guideX!.toStringAsFixed(1),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _pageLabel(int? index) {
    if (index == null) {
      return '-';
    }
    return '${index + 1}';
  }

  String _pageListLabel(List<int> indices) {
    if (indices.isEmpty) {
      return '-';
    }
    return indices.map((index) => '${index + 1}').join(',');
  }

  String _rectLabel(Rect? rect) {
    if (rect == null) {
      return '-';
    }
    return '${rect.left.toStringAsFixed(0)},${rect.top.toStringAsFixed(0)} → ${rect.right.toStringAsFixed(0)},${rect.bottom.toStringAsFixed(0)}';
  }

  String _presenceLabel(String? value) {
    return value == null || value == '-' ? '-' : 'ok';
  }
}

class _DebugLine extends StatelessWidget {
  const _DebugLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.xs / 2),
      child: Text('$label  $value'),
    );
  }
}

class _SampleDot extends StatelessWidget {
  const _SampleDot({
    required this.label,
    required this.color,
    required this.isDark,
  });

  final String label;
  final Color color;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: AppSpacing.iconSmall,
          height: AppSpacing.iconSmall,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color.withValues(alpha: 0.92),
            border: Border.all(
              color: isDark
                  ? AppColors.white.withValues(alpha: 0.35)
                  : AppColors.black.withValues(alpha: 0.35),
              width: AppSpacing.xs / 4,
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        DecoratedBox(
          decoration: BoxDecoration(
            color: (isDark ? AppColors.black : AppColors.white).withValues(
              alpha: isDark ? 0.6 : 0.78,
            ),
            borderRadius: BorderRadius.circular(
              AppSpacing.borderRadius - AppSpacing.xs / 2,
            ),
          ),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.xs + AppSpacing.xs / 2,
              vertical: AppSpacing.xs / 2,
            ),
            child: Text(
              label,
              style: TextStyle(
                color: isDark ? AppColors.white : AppColors.black,
                fontSize: AppTypography.iosCaption2,
                height: AppTypography.lineHeightTight,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
