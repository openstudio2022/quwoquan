import 'dart:async' show unawaited;
import 'dart:collection';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/rendering.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';

import 'package:quwoquan_app/ui/content/article_reader/content/article_reader_page_surfaces.dart';
import 'package:quwoquan_app/ui/content/article_reader/templates/article_reader_template_theme.dart';

import 'package:quwoquan_app/ui/content/article_reader/pageflip/diagnostics/article_reader_debug_mapper.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/diagnostics/article_reader_diagnostic_signatures.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_reader_stage_widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_dynamic_layers.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_leaf_verso_pixel_probe.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_leaf_verso_uv_mesh.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_sheet_partition.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/modes/single_page_mode_strategy.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/backward_article_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/forward_article_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/texture/article_reader_texture_capture_layer.dart';
import 'package:quwoquan_app/ui/content/models/article_document_models.dart';
import 'package:quwoquan_app/ui/content/models/article_presentation_models.dart';
import 'package:quwoquan_app/components/pageflip/book_layout.dart';
import 'package:quwoquan_app/components/pageflip/controller.dart';
import 'package:quwoquan_app/components/pageflip/geometry.dart';
import 'package:quwoquan_app/components/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/components/pageflip/pointer_bridge.dart';
import 'package:quwoquan_app/components/pageflip/render_frame.dart';
import 'package:quwoquan_app/components/pageflip/release_policy.dart';
import 'package:quwoquan_app/components/pageflip/spread_model.dart';
import 'package:quwoquan_app/components/pageflip/types.dart';
import 'package:quwoquan_app/components/media/shared/gesture/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/components/media/shared/gesture/immersive_pointer_gesture_layer.dart';

part 'article_read_only_book_deck_controller.dart';
part 'article_read_only_book_deck_diagnostic_geometry.dart';
part 'article_read_only_book_deck_diagnostic_reporting.dart';
part 'article_read_only_book_deck_dynamic_layers.dart';
part 'article_read_only_book_deck_gestures.dart';
part 'article_read_only_book_deck_page_surfaces.dart';
part 'article_read_only_book_deck_soft_layers.dart';
part 'article_read_only_book_deck_stage.dart';

enum ArticleReaderFallbackReason {
  forcedDegradedPager,
  pageCurlDisabled,
  accessibilityDisableAnimations,

  /// 超大文档性能降级。
  ///
  /// 仅在页数超过 [ArticleReadOnlyBookDeck.maxPageCurlPages] 时触发，
  /// 作为极端情况的安全网，而非常规长文的禁用开关。
  longDocument,
}

@immutable
class ArticleReaderPageFlipCommit {
  const ArticleReaderPageFlipCommit({
    required this.fromPage,
    required this.toPage,
    required this.durationMs,
    required this.mechanism,
  });

  final int fromPage;
  final int toPage;
  final int durationMs;
  final String mechanism;

  String get direction => toPage >= fromPage ? 'forward' : 'backward';
}

@immutable
class ArticleReaderPageCurlAbort {
  const ArticleReaderPageCurlAbort({
    required this.corner,
    required this.progress,
    required this.direction,
  });

  final String corner;
  final double progress;

  /// `'forward'` or `'backward'`.
  final String direction;
}

enum ArticleReadOnlyBookRenderBranch {
  degradedPager,
  staticStage,
  paperFoldDynamic,
}

enum ArticleReadOnlyBookDeckPresentationStyle { book, immersive }

enum BackwardVersoFailureReason {
  none,
  snapshotWrongSource,
  snapshotUnavailable,
  mirrorDirectionMismatch,
  versoPolygonEmpty,
  meshDegenerate,
  samplePointOutsideBand,
}

enum BackwardGeometryFailureReason {
  none,
  snapshotUnavailable,
  clipAreaDegenerate,
  foldFreeEdgeParallelButCollapsed,
  versoPolygonEmpty,
  meshDegenerate,
  bandOutsideVisiblePage,
  currentResidualLost,
  threeFaceCompositionLost,
  samplePointOutsideBand,
}

@immutable
class ArticleReadOnlyBookDebugState {
  const ArticleReadOnlyBookDebugState({
    required this.currentPageIndex,
    required this.turningPageIndex,
    required this.underlayPageIndex,
    required this.coveredPageIndex,
    required this.leftPageIndex,
    required this.rightPageIndex,
    required this.renderBranch,
    required this.renderDirection,
    required this.renderSceneReady,
    required this.sessionHasBundle,
    required this.requestedRectoPageIndex,
    required this.requestedVersoPageIndex,
    required this.requestedBottomPageIndex,
    required this.activeRectoPageIndex,
    required this.activeVersoPageIndex,
    required this.activeBottomPageIndex,
    this.activeVersoSurfaceKind,
    this.backwardVersoDisplayState,
    this.backwardVersoFailureReason = BackwardVersoFailureReason.none,
    this.backwardGeometryFailureReason = BackwardGeometryFailureReason.none,
    this.backwardVersoProbeLocalPoints = const <Offset>[],
    this.backwardVersoProbeTexturePoints = const <Offset>[],
    this.backwardVersoProbeViewportPoints = const <Offset>[],
    this.backwardBackLocalPolygonRaw = const <Offset>[],
    required this.availableSnapshotIndices,
    required this.pendingCaptureIndices,
    this.backwardCoveredPageIndex,
    this.backwardLeafRectoPageIndex,
    this.backwardLeafVersoPageIndex,
    this.bottomClipBounds,
    this.flippingClipBounds,
    this.frontBounds,
    this.backBounds,
    this.flippingAnchor,
    this.bottomAnchor,
    this.backwardCorner,
    this.backwardHinge,
    this.backwardSpineTop,
    this.backwardSpineBottom,
    this.backwardSeamX,
    this.backwardFoldX,
    this.backwardPageEdgeX,
    this.backwardFoldSurfaceEdgeX,
    this.backwardFoldLineTop,
    this.backwardFoldLineBottom,
    this.backwardPageEdgeLineTop,
    this.backwardPageEdgeLineBottom,
    this.backwardFoldSurfaceEdgeLineTop,
    this.backwardFoldSurfaceEdgeLineBottom,
    this.backwardCoveredWidth,
    this.backwardRectoCoverage,
    this.backwardVersoWidth,
    this.backwardRectoWidth,
    this.backwardBottomStart,
    this.backwardPhase,
    this.backwardReplayFrontLayerCount,
    this.backwardReplayBackSurfaceStrategy,
    this.backwardBottomLayerPageIndex,
    this.backwardFlippingLayerPageIndex,
    this.backwardDynamicOwnedPages = const <int>[],
    this.backwardStaticSuppressedPages = const <int>[],
    this.backwardReplaySlices,
    this.backwardCompositeMode,
    this.backwardFrontPaintBounds,
    this.backwardBackPaintBounds,
    this.backwardLaidFrontPaintBounds,
    this.backwardFoldSurfacePaintBounds,
    this.backwardCurrentResidualBounds,
    this.backwardMainline,
    this.backwardFlippingSheetCount,
    this.backwardFrontSheetId,
    this.backwardBackSheetId,
    this.backwardCurrentLayerPresent,
    this.backwardMultiSliceViolation,
    this.backwardPaintedVersoWidth,
    this.backwardBackPixelSurfaceStrategy,
    this.backwardVersoTextureUvStrategy,
    this.backwardFrontBackOverlapWidth,
    this.backwardBackVisibleUncoveredWidth,
    this.backwardBackVisibleProbeCount,
    this.backwardPaintSources = const <BackwardPaintSourceDiagnostic>[],
    this.backwardSurfaceOrigin,
    this.backwardSurfaceViewportRect,
    this.backwardPivotLocal,
    this.backwardPivotViewport,
    this.backwardClipLocalBounds,
    this.backwardClipViewportBounds,
    this.backwardFrontCoverageRatio,
    this.backwardLeftSpineLocked,
    this.backwardSimulatorVisualPhase,
    this.backwardEdgeEnteredPage,
    this.backwardOverlayClippedToPaper,
    this.backwardBackVertexCount,
    this.backwardFrontVertexCount,
    this.backwardEdgeParallelToFold,
    this.backwardBackPolygonPoints,
    this.backwardFrontPolygonPoints,
    this.backwardSheetPolygonPoints,
    this.backwardBottomClipPolygonPoints,
    this.backwardCurrentPolygonPoints,
    this.backwardFoldDirection,
    this.guideX,
  });

  final int currentPageIndex;
  final int? turningPageIndex;
  final int? underlayPageIndex;
  final int? coveredPageIndex;
  final int? leftPageIndex;
  final int? rightPageIndex;
  final ArticleReadOnlyBookRenderBranch renderBranch;
  final StPageFlipDirection? renderDirection;
  final bool renderSceneReady;
  final bool sessionHasBundle;
  final int? requestedRectoPageIndex;
  final int? requestedVersoPageIndex;
  final int? requestedBottomPageIndex;
  final int? activeRectoPageIndex;
  final int? activeVersoPageIndex;
  final int? activeBottomPageIndex;
  final String? activeVersoSurfaceKind;
  final String? backwardVersoDisplayState;
  final BackwardVersoFailureReason backwardVersoFailureReason;
  final BackwardGeometryFailureReason backwardGeometryFailureReason;
  final List<Offset> backwardVersoProbeLocalPoints;
  final List<Offset> backwardVersoProbeTexturePoints;
  final List<Offset> backwardVersoProbeViewportPoints;
  final List<Offset> backwardBackLocalPolygonRaw;
  final int? backwardCoveredPageIndex;
  final int? backwardLeafRectoPageIndex;
  final int? backwardLeafVersoPageIndex;
  final Rect? bottomClipBounds;
  final Rect? flippingClipBounds;
  final Rect? frontBounds;
  final Rect? backBounds;
  final Offset? flippingAnchor;
  final Offset? bottomAnchor;
  final String? backwardCorner;
  final Offset? backwardHinge;
  final Offset? backwardSpineTop;
  final Offset? backwardSpineBottom;
  final double? backwardSeamX;
  final double? backwardFoldX;
  final double? backwardPageEdgeX;
  final double? backwardFoldSurfaceEdgeX;
  final Offset? backwardFoldLineTop;
  final Offset? backwardFoldLineBottom;
  final Offset? backwardPageEdgeLineTop;
  final Offset? backwardPageEdgeLineBottom;
  final Offset? backwardFoldSurfaceEdgeLineTop;
  final Offset? backwardFoldSurfaceEdgeLineBottom;
  final double? backwardCoveredWidth;
  final double? backwardRectoCoverage;
  final double? backwardVersoWidth;
  final double? backwardRectoWidth;
  final double? backwardBottomStart;
  final String? backwardPhase;
  final int? backwardReplayFrontLayerCount;
  final String? backwardReplayBackSurfaceStrategy;
  final int? backwardBottomLayerPageIndex;
  final int? backwardFlippingLayerPageIndex;
  final List<int> backwardDynamicOwnedPages;
  final List<int> backwardStaticSuppressedPages;
  final String? backwardReplaySlices;
  final String? backwardCompositeMode;
  final Rect? backwardFrontPaintBounds;
  final Rect? backwardBackPaintBounds;
  final Rect? backwardLaidFrontPaintBounds;
  final Rect? backwardFoldSurfacePaintBounds;
  final Rect? backwardCurrentResidualBounds;
  final String? backwardMainline;
  final int? backwardFlippingSheetCount;
  final String? backwardFrontSheetId;
  final String? backwardBackSheetId;
  final bool? backwardCurrentLayerPresent;
  final bool? backwardMultiSliceViolation;
  final double? backwardPaintedVersoWidth;
  final String? backwardBackPixelSurfaceStrategy;
  final String? backwardVersoTextureUvStrategy;
  final double? backwardFrontBackOverlapWidth;
  final double? backwardBackVisibleUncoveredWidth;
  final int? backwardBackVisibleProbeCount;
  final List<BackwardPaintSourceDiagnostic> backwardPaintSources;
  final Offset? backwardSurfaceOrigin;
  final Rect? backwardSurfaceViewportRect;
  final Offset? backwardPivotLocal;
  final Offset? backwardPivotViewport;
  final Rect? backwardClipLocalBounds;
  final Rect? backwardClipViewportBounds;
  final double? backwardFrontCoverageRatio;
  final bool? backwardLeftSpineLocked;
  final String? backwardSimulatorVisualPhase;
  final bool? backwardEdgeEnteredPage;
  final bool? backwardOverlayClippedToPaper;
  final int? backwardBackVertexCount;
  final int? backwardFrontVertexCount;
  final bool? backwardEdgeParallelToFold;
  final String? backwardBackPolygonPoints;
  final String? backwardFrontPolygonPoints;
  final String? backwardSheetPolygonPoints;
  final String? backwardBottomClipPolygonPoints;
  final String? backwardCurrentPolygonPoints;
  final String? backwardFoldDirection;
  final List<int> availableSnapshotIndices;
  final List<int> pendingCaptureIndices;
  final double? guideX;

  String get signature => <Object?>[
    currentPageIndex,
    turningPageIndex,
    underlayPageIndex,
    coveredPageIndex,
    leftPageIndex,
    rightPageIndex,
    renderBranch.name,
    renderDirection?.name,
    renderSceneReady,
    sessionHasBundle,
    requestedRectoPageIndex,
    requestedVersoPageIndex,
    requestedBottomPageIndex,
    activeRectoPageIndex,
    activeVersoPageIndex,
    activeBottomPageIndex,
    activeVersoSurfaceKind,
    backwardVersoDisplayState,
    backwardVersoFailureReason.name,
    backwardGeometryFailureReason.name,
    articleDiagnosticPolygonSignature(backwardVersoProbeLocalPoints),
    articleDiagnosticPolygonSignature(backwardVersoProbeTexturePoints),
    articleDiagnosticPolygonSignature(backwardVersoProbeViewportPoints),
    backwardCoveredPageIndex,
    backwardLeafRectoPageIndex,
    backwardLeafVersoPageIndex,
    articleDiagnosticRectSignature(bottomClipBounds),
    articleDiagnosticRectSignature(flippingClipBounds),
    articleDiagnosticRectSignature(frontBounds),
    articleDiagnosticRectSignature(backBounds),
    articleDiagnosticOffsetSignature(flippingAnchor),
    articleDiagnosticOffsetSignature(bottomAnchor),
    backwardCorner,
    articleDiagnosticOffsetSignature(backwardHinge),
    articleDiagnosticOffsetSignature(backwardSpineTop),
    articleDiagnosticOffsetSignature(backwardSpineBottom),
    backwardSeamX?.toStringAsFixed(2),
    backwardFoldX?.toStringAsFixed(2),
    backwardPageEdgeX?.toStringAsFixed(2),
    backwardFoldSurfaceEdgeX?.toStringAsFixed(2),
    articleDiagnosticOffsetSignature(backwardFoldLineTop),
    articleDiagnosticOffsetSignature(backwardFoldLineBottom),
    articleDiagnosticOffsetSignature(backwardPageEdgeLineTop),
    articleDiagnosticOffsetSignature(backwardPageEdgeLineBottom),
    articleDiagnosticOffsetSignature(backwardFoldSurfaceEdgeLineTop),
    articleDiagnosticOffsetSignature(backwardFoldSurfaceEdgeLineBottom),
    backwardCoveredWidth?.toStringAsFixed(2),
    backwardRectoCoverage?.toStringAsFixed(2),
    backwardVersoWidth?.toStringAsFixed(2),
    backwardRectoWidth?.toStringAsFixed(2),
    backwardBottomStart?.toStringAsFixed(2),
    backwardPhase,
    backwardReplayFrontLayerCount,
    backwardReplayBackSurfaceStrategy,
    backwardBottomLayerPageIndex,
    backwardFlippingLayerPageIndex,
    backwardDynamicOwnedPages.join(','),
    backwardStaticSuppressedPages.join(','),
    backwardReplaySlices,
    backwardCompositeMode,
    articleDiagnosticRectSignature(backwardFrontPaintBounds),
    articleDiagnosticRectSignature(backwardBackPaintBounds),
    articleDiagnosticRectSignature(backwardLaidFrontPaintBounds),
    articleDiagnosticRectSignature(backwardFoldSurfacePaintBounds),
    articleDiagnosticRectSignature(backwardCurrentResidualBounds),
    backwardMainline,
    backwardFlippingSheetCount,
    backwardFrontSheetId,
    backwardBackSheetId,
    backwardCurrentLayerPresent,
    backwardMultiSliceViolation,
    backwardPaintedVersoWidth?.toStringAsFixed(2),
    backwardBackPixelSurfaceStrategy,
    backwardVersoTextureUvStrategy,
    backwardFrontBackOverlapWidth?.toStringAsFixed(2),
    backwardBackVisibleUncoveredWidth?.toStringAsFixed(2),
    backwardBackVisibleProbeCount,
    backwardPaintSources.map((source) => source.summary).join('|'),
    articleDiagnosticOffsetSignature(backwardSurfaceOrigin),
    articleDiagnosticRectSignature(backwardSurfaceViewportRect),
    articleDiagnosticOffsetSignature(backwardPivotLocal),
    articleDiagnosticOffsetSignature(backwardPivotViewport),
    articleDiagnosticRectSignature(backwardClipLocalBounds),
    articleDiagnosticRectSignature(backwardClipViewportBounds),
    backwardFrontCoverageRatio?.toStringAsFixed(2),
    backwardLeftSpineLocked,
    backwardSimulatorVisualPhase,
    backwardEdgeEnteredPage,
    backwardOverlayClippedToPaper,
    backwardBackVertexCount,
    backwardFrontVertexCount,
    backwardEdgeParallelToFold,
    backwardBackPolygonPoints,
    backwardFrontPolygonPoints,
    backwardSheetPolygonPoints,
    backwardBottomClipPolygonPoints,
    backwardCurrentPolygonPoints,
    backwardFoldDirection,
    availableSnapshotIndices.join(','),
    pendingCaptureIndices.join(','),
    guideX?.toStringAsFixed(2),
  ].join('|');
}

Rect? _intersectNonEmptyRects(Rect? a, Rect? b) {
  if (a == null || b == null) {
    return null;
  }
  final intersection = a.intersect(b);
  return intersection.isEmpty ? null : intersection;
}

bool _polygonContainsPoint({
  required List<Offset> polygon,
  required Offset point,
}) {
  if (polygon.length < 3) {
    return false;
  }
  var inside = false;
  for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    final pi = polygon[i];
    final pj = polygon[j];
    final intersects =
        ((pi.dy > point.dy) != (pj.dy > point.dy)) &&
        point.dx <
            (pj.dx - pi.dx) * (point.dy - pi.dy) / (pj.dy - pi.dy) + pi.dx;
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}

class ArticleReadOnlyBookDeck extends StatefulWidget {
  const ArticleReadOnlyBookDeck({
    super.key,
    required this.pages,
    required this.template,
    required this.fontPreset,
    required this.metrics,
    this.coverUrl = '',
    this.initialPage = 0,
    this.pagePadding = EdgeInsets.zero,
    this.enablePageCurl = true,
    this.forceDegradedPager = false,
    this.onPageChanged,
    this.onOverflowPrevious,
    this.onOverflowNext,
    this.onFallbackResolved,
    this.onPageFlipCommitted,
    this.onPageCurlAborted,
    this.onSceneChanged,
    this.onDebugStateChanged,
    this.onEntityTap,
    this.gestureIntentController,
    this.headerLabel,
    this.showFooterPageLabel = true,
    this.paperTexture,
    this.presentationStyle = ArticleReadOnlyBookDeckPresentationStyle.book,
    this.debugPureBackwardGeometry = false,
    this.debugPageSurfaceBuilder,
    this.debugBackPageSurfaceBuilder,
  });

  static const int maxPageCurlPages = 80;
  static const int maxResidentPageTextures = 3;

  final List<ArticlePageData> pages;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final ArticleCanvasMetrics metrics;
  final String coverUrl;
  final int initialPage;
  final EdgeInsets pagePadding;
  final bool enablePageCurl;
  final bool forceDegradedPager;
  final ValueChanged<int>? onPageChanged;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;
  final ValueChanged<ArticleReaderFallbackReason>? onFallbackResolved;
  final ValueChanged<ArticleReaderPageFlipCommit>? onPageFlipCommitted;
  final ValueChanged<ArticleReaderPageCurlAbort>? onPageCurlAborted;
  final ValueChanged<StPageFlipScene>? onSceneChanged;
  final ValueChanged<ArticleReadOnlyBookDebugState>? onDebugStateChanged;
  final ValueChanged<ArticleInlineSpan>? onEntityTap;
  final ImmersiveGestureIntentController? gestureIntentController;
  final String? headerLabel;
  final bool showFooterPageLabel;
  final ArticlePaperTexture? paperTexture;
  final ArticleReadOnlyBookDeckPresentationStyle presentationStyle;
  final bool debugPureBackwardGeometry;
  final Widget Function(BuildContext context, int pageIndex, Size pageSize)?
  debugPageSurfaceBuilder;
  final Widget Function(BuildContext context, int pageIndex, Size pageSize)?
  debugBackPageSurfaceBuilder;

  @override
  State<ArticleReadOnlyBookDeck> createState() =>
      _ArticleReadOnlyBookDeckState();
}

class _ArticleReadOnlyBookDeckState extends State<ArticleReadOnlyBookDeck>
    with SingleTickerProviderStateMixin {
  static const double _overflowSwitchVelocity = 320;
  static const double _overflowSwitchDistance = AppSpacing.buttonHeight;
  static const double _overflowEdgeStartInset =
      AppSpacing.minInteractiveSize / 2;
  static const double _boundaryRubberBandMaxOffset = AppSpacing.buttonHeight;
  static const Duration _boundaryRubberBandResetDuration = Duration(
    milliseconds: 220,
  );

  late final PageController _pageController;
  late final AnimationController _pageFlipAnimationController;
  late final StPageFlipPointerBridge _pointerBridge;

  StPageFlipController? _pageFlipController;
  StPageFlipAnimationPlan? _activePageFlipAnimation;
  Offset? _pointerDownLocalPosition;
  Offset? _dragStartGlobalPosition;
  Offset? _latestDragGlobalPosition;
  DateTime? _dragStartedAt;
  int _lastAnimationFrameIndex = -1;
  double _edgeOverflowDistance = 0;
  StPageFlipDirection? _pendingOverflowDirection;
  bool _overflowTriggered = false;
  Size? _lastInteractiveStageSize;
  Offset? _boundaryDragStartLocalPosition;
  StPageFlipDirection? _boundaryDragDirection;
  StPageFlipDirection? _activeDragDirection;
  double _boundaryRubberBandRawOffset = 0;
  double _boundaryRubberBandOffset = 0;
  bool _shouldAnimateBoundaryRubberBandReset = false;
  late int _currentPage;
  DateTime? _pageTransitionStartedAt;
  String? _pageTransitionMechanism;
  ArticleReaderFallbackReason? _reportedFallbackReason;
  StPageFlipScene? _pendingReportedScene;
  bool _sceneReportScheduled = false;
  String? _lastReportedSceneSignature;
  ArticleReadOnlyBookDebugState? _pendingReportedDebugState;
  bool _debugReportScheduled = false;
  String? _lastReportedDebugSignature;

  final Map<String, Widget> _pageSurfaceCache = <String, Widget>{};
  final Map<int, GlobalKey> _textureCaptureBoundaryKeys = <int, GlobalKey>{};
  final Map<int, ArticlePageTextureSnapshot> _pageTextureSnapshots =
      <int, ArticlePageTextureSnapshot>{};
  final List<ArticlePageTextureSnapshot> _retiredTextureSnapshots =
      <ArticlePageTextureSnapshot>[];
  final ListQueue<int> _pendingTextureCaptureIndices = ListQueue<int>();
  final SinglePageModeStrategy _articleReaderModeStrategy =
      const SinglePageModeStrategy();
  final ForwardArticleFlipPipeline _forwardFlipPipeline =
      const ForwardArticleFlipPipeline();
  final BackwardArticleFlipPipeline _backwardFlipPipeline =
      const BackwardArticleFlipPipeline();
  final ArticleReaderDebugMapper _articleReaderDebugMapper =
      const ArticleReaderDebugMapper();

  Size? _cachedSurfaceSize;
  bool _textureCaptureScheduled = false;
  bool _textureCaptureInFlight = false;
  Set<int>? _activeBackTexturePageIndices;
  bool _textureWarmupBlockedGesture = false;

  bool get _usesImmersivePresentation =>
      widget.presentationStyle ==
      ArticleReadOnlyBookDeckPresentationStyle.immersive;

  int get _safeInitialPage {
    if (widget.pages.isEmpty) {
      return 0;
    }
    return widget.initialPage.clamp(0, widget.pages.length - 1).toInt();
  }

  ArticleReaderFallbackReason? get _fallbackReason {
    final disableAnimations = WidgetsBinding
        .instance
        .platformDispatcher
        .accessibilityFeatures
        .disableAnimations;
    if (widget.forceDegradedPager) {
      return ArticleReaderFallbackReason.forcedDegradedPager;
    }
    if (!widget.enablePageCurl) {
      return ArticleReaderFallbackReason.pageCurlDisabled;
    }
    if (disableAnimations) {
      return ArticleReaderFallbackReason.accessibilityDisableAnimations;
    }
    if (widget.pages.length > ArticleReadOnlyBookDeck.maxPageCurlPages) {
      return ArticleReaderFallbackReason.longDocument;
    }
    return null;
  }

  bool get _useDegradedPager => _fallbackReason != null;
  bool get _showsPageCurl => !_useDegradedPager && widget.pages.length > 1;
  bool get _usesStaticBoundaryStage => !_useDegradedPager && !_showsPageCurl;
  StPageFlipScene? get _pageFlipScene => _pageFlipController?.scene;
  bool get _hasActivePageCurlAnimation => _activePageFlipAnimation != null;

  @override
  void initState() {
    super.initState();
    _currentPage = _safeInitialPage;
    _pageController = PageController(initialPage: _currentPage);
    _pointerBridge = StPageFlipPointerBridge();
    _pageFlipAnimationController =
        AnimationController(
            vsync: this,
            duration: const Duration(milliseconds: 260),
            lowerBound: 0,
            upperBound: 1,
          )
          ..addListener(_handlePageFlipAnimationTick)
          ..addStatusListener(_handlePageFlipAnimationStatus);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.onPageChanged?.call(_currentPage);
    });
    _maybeReportFallbackReason();
  }

  @override
  void didUpdateWidget(covariant ArticleReadOnlyBookDeck oldWidget) {
    super.didUpdateWidget(oldWidget);
    _maybeReportFallbackReason();
    if (widget.pages != oldWidget.pages ||
        widget.template != oldWidget.template ||
        widget.fontPreset != oldWidget.fontPreset ||
        widget.metrics != oldWidget.metrics ||
        widget.coverUrl != oldWidget.coverUrl ||
        widget.enablePageCurl != oldWidget.enablePageCurl ||
        widget.forceDegradedPager != oldWidget.forceDegradedPager ||
        widget.headerLabel != oldWidget.headerLabel ||
        widget.showFooterPageLabel != oldWidget.showFooterPageLabel ||
        widget.paperTexture != oldWidget.paperTexture ||
        widget.presentationStyle != oldWidget.presentationStyle) {
      _pageSurfaceCache.clear();
      _clearPageTextureSnapshots();
      _pageFlipController = null;
    }
    final nextInitialPage = _safeInitialPage;
    if (widget.initialPage != oldWidget.initialPage &&
        nextInitialPage != _currentPage) {
      if (_useDegradedPager && _pageController.hasClients) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted || !_pageController.hasClients) {
            return;
          }
          _pageController.jumpToPage(nextInitialPage);
          setState(() {
            _currentPage = nextInitialPage;
          });
        });
      } else {
        setState(() {
          _currentPage = nextInitialPage;
          _pageFlipController?.setCurrentPage(_currentPage);
        });
      }
    } else if (_currentPage >= widget.pages.length && widget.pages.isNotEmpty) {
      if (_useDegradedPager) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted || !_pageController.hasClients) {
            return;
          }
          final lastPage = widget.pages.length - 1;
          _pageController.jumpToPage(lastPage);
          setState(() {
            _currentPage = lastPage;
          });
        });
      } else {
        setState(() {
          _currentPage = widget.pages.length - 1;
          _pageFlipController?.setCurrentPage(_currentPage);
        });
      }
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    _pageFlipAnimationController.dispose();
    _pointerBridge.dispose();
    _clearPageTextureSnapshots();
    _disposeRetiredTextureSnapshots();
    super.dispose();
  }

  void _maybeReportFallbackReason() {
    final reason = _fallbackReason;
    if (reason == null || reason == _reportedFallbackReason) {
      return;
    }
    _reportedFallbackReason = reason;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      widget.onFallbackResolved?.call(reason);
    });
  }

  Size _resolvePageSizeForStage(Size stageSize) {
    final availableWidth = math.max(
      1.0,
      stageSize.width - widget.pagePadding.horizontal,
    );
    final availableHeight = math.max(
      1.0,
      stageSize.height - widget.pagePadding.vertical,
    );
    if (_usesImmersivePresentation) {
      return Size(availableWidth, availableHeight);
    }
    final pageWidth = math.min(
      availableWidth,
      availableHeight * widget.metrics.aspectRatio,
    );
    final pageHeight = pageWidth / widget.metrics.aspectRatio;
    return Size(pageWidth, pageHeight);
  }

  ArticleReadOnlyBookDeck get _deck => widget;
  bool get _isMounted => mounted;

  void _setDeckState(VoidCallback callback) {
    setState(callback);
  }

  @override
  Widget build(BuildContext context) {
    if (widget.pages.isEmpty) {
      return const SizedBox.expand();
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final stageSize = Size(
          constraints.maxWidth.isFinite ? constraints.maxWidth : 1,
          constraints.maxHeight.isFinite ? constraints.maxHeight : 1,
        );
        final pageRect = _pageRectForStage(stageSize);
        if (_usesStaticBoundaryStage) {
          return _buildStaticBoundaryStage(context, pageRect, stageSize);
        }
        if (_useDegradedPager) {
          return _buildDegradedReaderStage(context, pageRect, stageSize);
        }
        return _buildInteractiveReaderStage(context, stageSize);
      },
    );
  }
}
