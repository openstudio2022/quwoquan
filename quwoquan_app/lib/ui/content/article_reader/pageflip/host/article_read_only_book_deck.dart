import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';

import 'package:quwoquan_app/ui/content/article_reader/content/article_reader_page_surfaces.dart';
import 'package:quwoquan_app/ui/content/article_reader/templates/article_reader_template_theme.dart';

import 'package:quwoquan_app/ui/content/article_reader/pageflip/diagnostics/article_reader_debug_mapper.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/diagnostics/article_reader_diagnostic_signatures.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_reader_stage_widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_dynamic_layers.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/modes/single_page_mode_strategy.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/backward_article_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/forward_article_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/pointer_bridge.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/spread_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

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

typedef _PageLine = (Offset, Offset);

/// 后翻 diagnostic 几何 record。所有字段都从 native BACK soft layer 与同一张
/// moving sheet 的 recto/verso 分段派生，diagnostics 不维护第二套折纸真相。
typedef _BackwardDiagnosticGeometry = ({
  SoftPageLayerGeometry softGeometry,
  List<Offset> sheetLocalPolygon,
  Rect? sheetLocalBounds,
  Rect? sheetViewportBounds,
  List<Offset> previousBackLocalPolygon,
  Rect? previousBackViewportBounds,
  List<Offset> previousFrontLocalPolygon,
  Rect? previousFrontViewportBounds,
  (Offset, Offset)? foldLineViewport,
  (Offset, Offset)? freeEdgeLineViewport,
  List<Offset> currentResidualPagePolygon,
  List<Offset> currentResidualViewportPolygon,
  Rect? currentResidualViewportBounds,
});

class _BackwardGeometryGuidePainter extends CustomPainter {
  const _BackwardGeometryGuidePainter({
    required this.foldLine,
    this.freeEdgeLine,
  });

  final (Offset, Offset) foldLine;
  final (Offset, Offset)? freeEdgeLine;

  @override
  void paint(Canvas canvas, Size size) {
    final foldPaint = Paint()
      ..color = AppColors.error
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke;
    final pageEdgePaint = Paint()
      ..color = AppColors.iosSystemCyanAccent
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke;
    canvas.drawLine(foldLine.$1, foldLine.$2, foldPaint);
    if (freeEdgeLine case final freeEdge?) {
      canvas.drawLine(freeEdge.$1, freeEdge.$2, pageEdgePaint);
    }
    _paintLabel(canvas, 'F', foldLine.$1 + const Offset(4, 4), foldPaint.color);
    if (freeEdgeLine case final freeEdge?) {
      _paintLabel(
        canvas,
        'R',
        freeEdge.$1 + const Offset(4, 4),
        pageEdgePaint.color,
      );
    }
  }

  void _paintLabel(Canvas canvas, String label, Offset offset, Color color) {
    final painter = TextPainter(
      text: TextSpan(
        text: label,
        style: TextStyle(
          color: color,
          fontSize: AppTypography.lg,
          fontWeight: AppTypography.extraBold,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    painter.paint(canvas, offset);
  }

  @override
  bool shouldRepaint(covariant _BackwardGeometryGuidePainter oldDelegate) {
    return oldDelegate.foldLine != foldLine ||
        oldDelegate.freeEdgeLine != freeEdgeLine;
  }
}

class _BackwardFoldBoundaryPainter extends CustomPainter {
  const _BackwardFoldBoundaryPainter({
    required this.foldLine,
    required this.color,
  });

  final (Offset, Offset) foldLine;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;
    canvas.drawLine(foldLine.$1, foldLine.$2, paint);
  }

  @override
  bool shouldRepaint(covariant _BackwardFoldBoundaryPainter oldDelegate) {
    return oldDelegate.foldLine != foldLine || oldDelegate.color != color;
  }
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
    this.showFooterPageLabel = true,
    this.paperTexture,
    this.debugPureBackwardGeometry = false,
    this.debugPageSurfaceBuilder,
    this.debugBackPageSurfaceBuilder,
  });

  static const int maxPageCurlPages = 80;

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
  final bool showFooterPageLabel;
  final ArticlePaperTexture? paperTexture;
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
  bool _overflowLocked = false;
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
  final SinglePageModeStrategy _articleReaderModeStrategy =
      const SinglePageModeStrategy();
  final ForwardArticleFlipPipeline _forwardFlipPipeline =
      const ForwardArticleFlipPipeline();
  final BackwardArticleFlipPipeline _backwardFlipPipeline =
      const BackwardArticleFlipPipeline();
  final ArticleReaderDebugMapper _articleReaderDebugMapper =
      const ArticleReaderDebugMapper();

  Size? _cachedSurfaceSize;

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
        widget.showFooterPageLabel != oldWidget.showFooterPageLabel ||
        widget.paperTexture != oldWidget.paperTexture) {
      _pageSurfaceCache.clear();
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
    final pageWidth = math.min(
      availableWidth,
      availableHeight * widget.metrics.aspectRatio,
    );
    final pageHeight = pageWidth / widget.metrics.aspectRatio;
    return Size(pageWidth, pageHeight);
  }

  void _configurePageFlipController(Size stageSize) {
    if (widget.pages.isEmpty) {
      _pageFlipController = null;
      _pageSurfaceCache.clear();
      _cachedSurfaceSize = null;
      return;
    }
    final pageSize = _resolvePageSizeForStage(stageSize);
    if (_cachedSurfaceSize != pageSize) {
      _cachedSurfaceSize = pageSize;
      _pageSurfaceCache.clear();
    }
    final layout = computeStPageFlipLayout(
      viewportSize: stageSize,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
      usePortrait: true,
    );
    final spreadModel = StPageFlipSpreadModel(
      pageCount: widget.pages.length,
      showCover: widget.coverUrl.trim().isNotEmpty,
    );
    if (_pageFlipController == null) {
      _pageFlipController = StPageFlipController(
        spreadModel: spreadModel,
        layout: layout,
        initialPage: _currentPage,
      );
      return;
    }
    _pageFlipController!.updateConfiguration(
      spreadModel: spreadModel,
      layout: layout,
      currentPage: _currentPage,
    );
  }

  ArticlePageTextureBinding? _textureBindingForScene(StPageFlipScene scene) {
    return resolveArticlePageTextureBinding(
      direction: scene.direction,
      flippingPageIndex: scene.flippingPageIndex,
      bottomPageIndex: scene.bottomPageIndex,
      currentPageIndex: scene.currentPageIndex,
    );
  }

  ArticleBackwardPageSurfaceBinding? _backwardSurfaceBindingForScene(
    StPageFlipScene scene,
  ) {
    return resolveArticleBackwardPageSurfaceBinding(
      direction: scene.direction,
      flippingPageIndex: scene.flippingPageIndex,
      currentPageIndex: scene.currentPageIndex,
    );
  }

  double _sceneProgress(StPageFlipScene scene) {
    return scene.renderFrame?.progress ??
        ((scene.calculation?.getFlippingProgress() ?? 0) / 100)
            .clamp(0.0, 1.0)
            .toDouble();
  }

  /// 仅用于诊断/标签的简单阶段名。新的 backward 主线由旋转角度驱动表面切换，
  /// 这里保留三档进度桶名是为了让记录诊断面板/测试快照保持兼容。
  String _resolveBackwardSurfacePhaseName(double progress) {
    final settledProgress = progress.clamp(0.0, 1.0).toDouble();
    if (settledProgress < 0.32) {
      return 'verso';
    }
    if (settledProgress < 0.68) {
      return 'transition';
    }
    return 'recto';
  }

  String? _resolveBackwardCornerLabel(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final corner = scene.renderFrame?.corner ?? scene.corner;
    if (corner == null) {
      return null;
    }
    return _cornerNameFromPageFlip(corner, StPageFlipDirection.back);
  }

  Offset? _resolveBackwardHinge({
    required StPageFlipScene scene,
    required Size pageSize,
  }) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final corner = scene.renderFrame?.corner ?? scene.corner;
    if (corner == null) {
      return null;
    }
    return corner == StPageFlipCorner.bottom
        ? Offset(0, pageSize.height)
        : Offset.zero;
  }

  Offset? _resolveBackwardSpineTop(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final calculation = scene.calculation;
    if (calculation is StPageFlipCalculation) {
      return calculation.getBackwardSpineTop();
    }
    return Offset.zero;
  }

  Offset? _resolveBackwardSpineBottom({
    required StPageFlipScene scene,
    required Size pageSize,
  }) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final calculation = scene.calculation;
    if (calculation is StPageFlipCalculation) {
      return calculation.getBackwardSpineBottom();
    }
    return Offset(0, pageSize.height);
  }

  double? _resolveBackwardSeamX(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final renderFrame = scene.renderFrame;
    final calculation = scene.calculation;
    if (renderFrame?.flippingClipArea case final area?) {
      return area.fold<double>(
        0,
        (current, point) => math.max(current, point.dx),
      );
    }
    if (calculation is StPageFlipCalculation) {
      return calculation.backwardSeamX;
    }
    return null;
  }

  ArticlePageBackwardLeafFrame? _resolveBackwardLeafFrame(
    StPageFlipScene scene,
  ) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final renderFrameLeaf = scene.renderFrame?.backwardLeafFrame;
    if (renderFrameLeaf != null) {
      return renderFrameLeaf;
    }
    return resolveArticlePageBackwardLeafFrame(
      direction: StPageFlipDirection.back,
      progress: _sceneProgress(scene),
      reversePose: null,
    );
  }

  String _resolveBackwardCompositionPhase(ArticlePageBackwardLeafFrame frame) {
    final versoWidth = frame.versoRevealWidthNormalized;
    final rectoWidth = frame.totalRectoVisibleWidthNormalized;
    if (versoWidth > 0.02 && rectoWidth < 0.02) {
      return 'verso';
    }
    if (versoWidth > 0.01) {
      return 'transition';
    }
    return 'recto';
  }

  ({List<Offset> recto, List<Offset> verso}) _backwardFoldDerivedFacePolygons({
    required Size pageSize,
    required _PageLine? foldLine,
    required _PageLine? freeEdgeLine,
    required List<Offset> sheetLocalPolygon,
  }) {
    return (
      recto: backwardSheetRectoPolygon(
        pageSize: pageSize,
        sheetLocalPolygon: sheetLocalPolygon,
        foldLine: foldLine,
        freeEdgeLine: freeEdgeLine,
      ),
      verso: backwardSheetVersoPolygon(
        pageSize: pageSize,
        sheetLocalPolygon: sheetLocalPolygon,
        foldLine: foldLine,
        freeEdgeLine: freeEdgeLine,
      ),
    );
  }

  String? _resolveBackwardPhaseLabel(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final frame = _resolveBackwardLeafFrame(scene);
    if (frame != null) {
      return _resolveBackwardCompositionPhase(frame);
    }
    return _resolveBackwardSurfacePhaseName(_sceneProgress(scene));
  }

  int? _resolveBackwardReplayFrontLayerCount(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    return _hasBackwardPaperFoldFrame(scene) && scene.flippingPageIndex != null
        ? 1
        : 0;
  }

  String? _resolveBackwardReplayBackSurfaceStrategy(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    return scene.flippingPageIndex == null
        ? null
        : 'paperFoldBackMainlineSurface';
  }

  Set<int> _resolveBackwardDynamicOwnedPageSet(StPageFlipScene scene) {
    if (!_hasBackwardPaperFoldFrame(scene)) {
      return const <int>{};
    }
    return <int>{if (scene.flippingPageIndex != null) scene.flippingPageIndex!};
  }

  List<int> _sortedPageIndices(Iterable<int> pageIndices) {
    return (pageIndices.toSet().toList()..sort()).toList(growable: false);
  }

  List<int> _resolveBackwardStaticSuppressedPages({
    required StPageFlipScene scene,
    required Set<int> dynamicOwnedPages,
  }) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return const <int>[];
    }
    return _sortedPageIndices(<int>[
      if (scene.visibleSpread.leftPageIndex != null &&
          dynamicOwnedPages.contains(scene.visibleSpread.leftPageIndex))
        scene.visibleSpread.leftPageIndex!,
      if (scene.visibleSpread.rightPageIndex != null &&
          dynamicOwnedPages.contains(scene.visibleSpread.rightPageIndex))
        scene.visibleSpread.rightPageIndex!,
    ]);
  }

  bool _hasBackwardPaperFoldFrame(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back ||
        scene.bottomPageIndex == null ||
        scene.flippingPageIndex == null) {
      return false;
    }
    final frame = scene.renderFrame;
    return frame != null &&
        frame.flippingClipArea.length >= 3 &&
        frame.bottomClipArea.length >= 3;
  }

  /// 由 backward leaf frame 直接推导诊断阶段标签。新主线下没有了基于 region
  /// 的几何派生，所以用 frame 的覆盖参数直接打档。
  String? _resolveBackwardSimulatorVisualPhase(
    ArticlePageBackwardLeafFrame? frame,
  ) {
    if (frame == null) {
      return null;
    }
    final frontCoverage = frame.rectoCoverageNormalized.clamp(0.0, 1.0);
    final visibleBack = frame.versoRevealWidthNormalized.clamp(0.0, 1.0);
    if (frontCoverage <= 0.02 && visibleBack > 0.05) {
      return 'versoDominant';
    }
    if (visibleBack > 0.08 && frontCoverage < 0.72) {
      return 'mixedReplay';
    }
    if (frontCoverage >= 0.72) {
      return 'rectoTakeover';
    }
    return 'transition';
  }

  String? _resolveBackwardReplaySliceLabel(
    ArticlePageBackwardLeafFrame? frame,
    StPageFlipScene scene, {
    required Rect pageRect,
    required Rect? frontPaintBounds,
    required Rect? backPaintBounds,
    required double? surfaceAngle,
    required int flippingSheetCount,
    required String? frontSheetId,
    required String? backSheetId,
    required bool currentLayerPresent,
    required bool multiSliceViolation,
  }) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final backStrategy = _resolveBackwardReplayBackSurfaceStrategy(scene);
    if (backStrategy == null) {
      return null;
    }
    final renderFrame = scene.renderFrame;
    final staticBottomSuppressed =
        scene.bottomPageIndex != null &&
        _resolveBackwardStaticSuppressedPages(
          scene: scene,
          dynamicOwnedPages: _resolveBackwardDynamicOwnedPageSet(scene),
        ).contains(scene.bottomPageIndex);
    final surfaceShowsFront = frontPaintBounds != null;
    final foldDirection = surfaceAngle == null
        ? 'unknown'
        : surfaceAngle >= 0
        ? 'leftward'
        : 'rightward';
    final frontFirst = frontPaintBounds != null && backPaintBounds == null;
    final phase = frontPaintBounds == null ? 'backOnly' : 'frontTakeover';
    return <String>[
      'route=paperFoldBackwardMainline',
      'mainline=paperFoldBackMainline',
      'flipping=singleTurningSheet',
      'flippingSheetCount=$flippingSheetCount',
      'frontSheetId=${frontSheetId ?? "none"}',
      'backSheetId=${backSheetId ?? "none"}',
      'frontBackSameLeaf=${frontSheetId != null && frontSheetId == backSheetId}',
      'frontLayer=sheetRectoPreviousFront',
      'backLayer=rotatingFoldBand',
      'currentLayerPresent=$currentLayerPresent',
      'multiSliceViolation=$multiSliceViolation',
      'frontLayers=${frontPaintBounds == null ? 0 : 1}',
      'backSurface=$backStrategy',
      'backFirst=${backPaintBounds != null && frontPaintBounds == null}',
      'frontFirst=$frontFirst',
      'sheetSource=canonicalBackMovingEdge',
      'localPoint=${articleDiagnosticOffsetSignature(renderFrame?.localPagePoint)}',
      'staticBottomSuppressed=$staticBottomSuppressed',
      'foldDirection=$foldDirection',
      'surfaceShowsFront=$surfaceShowsFront',
      'surfacePhase=$phase',
      if (frame != null) ...<String>[
        'foldF=${frame.coveredWidthNormalized.toStringAsFixed(3)}',
        'edgeE=${frame.laidDownWidthNormalized.toStringAsFixed(3)}',
        'rectoCoverage=${frame.rectoCoverageNormalized.toStringAsFixed(3)}',
        'verso=${frame.versoRevealWidthNormalized.toStringAsFixed(3)}',
      ],
    ].join('/');
  }

  SoftPageLayerGeometry? _resolveDynamicLayerGeometry({
    required List<Offset>? area,
    required Offset? anchor,
    required double angle,
    required StPageFlipDirection? direction,
    StPageFlipDirection? visualGeometryDirection,
    required StPageFlipBoundsRect bounds,
    required bool isFlippingPage,
    double progress = 0,
  }) {
    if (area == null ||
        area.length < 3 ||
        anchor == null ||
        direction == null) {
      return null;
    }
    final geometryDirection = visualGeometryDirection ?? direction;
    final pageSize = Size(bounds.pageWidth, bounds.height);
    final surfaceOrigin = softLayerOrigin(
      anchor: anchor,
      pageSize: pageSize,
      direction: geometryDirection,
      isFlippingPage: isFlippingPage,
      lockSpineLine: false,
    );
    final positionViewport = convertBookPointToViewport(
      surfaceOrigin,
      bounds,
      direction: softLayerViewportDirection(geometryDirection),
    );
    final localClipPolygon = _localPolygonFromArea(
      area: area,
      anchor: surfaceOrigin,
      angle: angle,
      direction: geometryDirection,
    );
    final viewportClipPolygon = area
        .map((point) {
          final translated = geometryDirection == StPageFlipDirection.back
              ? Offset(surfaceOrigin.dx - point.dx, point.dy - surfaceOrigin.dy)
              : Offset(
                  point.dx - surfaceOrigin.dx,
                  point.dy - surfaceOrigin.dy,
                );
          final rotated = rotatePoint(translated, Offset.zero, angle);
          return positionViewport + rotated;
        })
        .toList(growable: false);
    return SoftPageLayerGeometry(
      surfaceOrigin: surfaceOrigin,
      pivotLocal: anchor - surfaceOrigin,
      positionViewport: positionViewport,
      surfaceViewportRect: positionViewport & pageSize,
      localClipPolygon: localClipPolygon,
      viewportClipPolygon: viewportClipPolygon,
      clipLocalBounds: polygonBounds(localClipPolygon),
      clipViewportBounds: polygonBounds(viewportClipPolygon),
      transform: Matrix4.identity()
        ..translateByDouble(
          anchor.dx - surfaceOrigin.dx,
          anchor.dy - surfaceOrigin.dy,
          0,
          1,
        )
        ..rotateZ(angle)
        ..translateByDouble(
          surfaceOrigin.dx - anchor.dx,
          surfaceOrigin.dy - anchor.dy,
          0,
          1,
        ),
    );
  }

  /// 后翻 diagnostic 几何：native BACK frame 是唯一几何容器，front/back
  /// 只在同一 moving sheet 内按 recto/verso 宽度分段。
  _BackwardDiagnosticGeometry? _resolveBackwardDiagnosticGeometry(
    StPageFlipScene scene,
  ) {
    final frame = scene.renderFrame;
    if (frame == null ||
        _sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    if (frame.flippingClipArea.length < 3) {
      return null;
    }
    final pageRect = _backwardPageRect(scene);
    final leafFrame = frame.backwardLeafFrame;
    final softGeometry = _resolveDynamicLayerGeometry(
      area: frame.flippingClipArea,
      anchor: frame.flippingAnchor,
      angle: frame.angle,
      direction: StPageFlipDirection.back,
      visualGeometryDirection: frame.visualGeometryDirection,
      bounds: scene.layout.bounds,
      isFlippingPage: true,
      progress: _sceneProgress(scene),
    );
    if (softGeometry == null) {
      return null;
    }
    final sheetLocalPolygon = softGeometry.localClipPolygon;
    final sheetViewportPolygon = softGeometry.viewportClipPolygon;
    final pageSize = Size(
      scene.layout.bounds.pageWidth,
      scene.layout.bounds.height,
    );
    final anchor = frame.flippingAnchor;
    final angle = frame.angle;
    final visualGeometryDirection = frame.visualGeometryDirection;
    final projected = frame.backwardProjectedFrame;
    final localFoldLine = projected?.foldLine == null
        ? null
        : (
            _localPointFromAreaPoint(
              point: projected!.foldLine.$1,
              anchor: softGeometry.surfaceOrigin,
              angle: angle,
              direction: visualGeometryDirection,
            ),
            _localPointFromAreaPoint(
              point: projected.foldLine.$2,
              anchor: softGeometry.surfaceOrigin,
              angle: angle,
              direction: visualGeometryDirection,
            ),
          );
    final localFreeEdgeLine = projected?.projectedRightEdgeLine == null
        ? null
        : (
            _localPointFromAreaPoint(
              point: projected!.projectedRightEdgeLine.$1,
              anchor: softGeometry.surfaceOrigin,
              angle: angle,
              direction: visualGeometryDirection,
            ),
            _localPointFromAreaPoint(
              point: projected.projectedRightEdgeLine.$2,
              anchor: softGeometry.surfaceOrigin,
              angle: angle,
              direction: visualGeometryDirection,
            ),
          );
    final previousFrontLocalPolygon = leafFrame == null
        ? const <Offset>[]
        : backwardSheetRectoPolygon(
            pageSize: pageSize,
            sheetLocalPolygon: sheetLocalPolygon,
            foldLine: localFoldLine,
            freeEdgeLine: localFreeEdgeLine,
          );
    final previousBackLocalPolygon = leafFrame == null
        ? sheetLocalPolygon
        : backwardSheetVersoPolygon(
            pageSize: pageSize,
            sheetLocalPolygon: sheetLocalPolygon,
            foldLine: localFoldLine,
            freeEdgeLine: localFreeEdgeLine,
          );
    final previousFrontViewportPolygon = transformSoftLayerLocalPolygon(
      polygon: previousFrontLocalPolygon,
      geometry: softGeometry,
    );
    final previousBackViewportPolygon = transformSoftLayerLocalPolygon(
      polygon: previousBackLocalPolygon,
      geometry: softGeometry,
    );
    final currentResidualPagePolygon = frame.bottomClipArea.length >= 3
        ? List<Offset>.unmodifiable(frame.bottomClipArea)
        : const <Offset>[];
    final currentResidualViewportPolygon = currentResidualPagePolygon
        .map((p) => pageRect.topLeft + p)
        .toList(growable: false);
    final positionViewport = softGeometry.positionViewport;
    Offset toViewportPoint(Offset p) {
      final translated = visualGeometryDirection == StPageFlipDirection.back
          ? Offset(anchor.dx - p.dx, p.dy - anchor.dy)
          : Offset(p.dx - anchor.dx, p.dy - anchor.dy);
      final rotated = rotatePointForCanvasTransform(translated, angle);
      return positionViewport + rotated;
    }

    (Offset, Offset)? toViewportLine((Offset, Offset)? line) {
      if (line == null) {
        return null;
      }
      return orderViewportLineTopToBottom((
        toViewportPoint(line.$1),
        toViewportPoint(line.$2),
      ));
    }

    return (
      softGeometry: softGeometry,
      sheetLocalPolygon: sheetLocalPolygon,
      sheetLocalBounds: polygonBounds(sheetLocalPolygon),
      sheetViewportBounds: polygonBounds(sheetViewportPolygon),
      previousBackLocalPolygon: previousBackLocalPolygon,
      previousBackViewportBounds: polygonBounds(previousBackViewportPolygon),
      previousFrontLocalPolygon: previousFrontLocalPolygon,
      previousFrontViewportBounds: polygonBounds(previousFrontViewportPolygon),
      foldLineViewport: toViewportLine(projected?.foldLine),
      freeEdgeLineViewport: toViewportLine(projected?.projectedRightEdgeLine),
      currentResidualPagePolygon: currentResidualPagePolygon,
      currentResidualViewportPolygon: currentResidualViewportPolygon,
      currentResidualViewportBounds: polygonBounds(
        currentResidualViewportPolygon,
      ),
    );
  }

  Rect _backwardPageRect(StPageFlipScene scene) {
    return resolveBookPageRect(scene.layout, isRightPage: true);
  }

  List<Offset> _resolveDynamicLayerPolygon({
    required List<Offset>? area,
    required Offset? anchor,
    required double angle,
    required StPageFlipDirection? direction,
    required StPageFlipBoundsRect bounds,
    required bool isFlippingPage,
  }) {
    return _resolveDynamicLayerGeometry(
          area: area,
          anchor: anchor,
          angle: angle,
          direction: direction,
          bounds: bounds,
          isFlippingPage: isFlippingPage,
        )?.viewportClipPolygon ??
        const <Offset>[];
  }

  Rect? _resolveDynamicLayerBounds({
    required List<Offset>? area,
    required Offset? anchor,
    required double angle,
    required StPageFlipDirection? direction,
    required StPageFlipBoundsRect bounds,
    required bool isFlippingPage,
  }) {
    final polygon = _resolveDynamicLayerPolygon(
      area: area,
      anchor: anchor,
      angle: angle,
      direction: direction,
      bounds: bounds,
      isFlippingPage: isFlippingPage,
    );
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

  double? _resolveBackwardSeamGuideX({
    required Rect pageRect,
    required StPageFlipRenderFrame? renderFrame,
    required StPageFlipCalculation? calculation,
  }) {
    if (renderFrame?.flippingClipArea case final area?) {
      final seamX = area.fold<double>(
        0,
        (current, point) => math.max(current, point.dx),
      );
      return pageRect.left + seamX;
    }
    if (calculation is StPageFlipCalculation) {
      return pageRect.left + calculation.backwardSeamX;
    }
    return null;
  }

  StPageFlipDirection? _sceneRenderDirection(StPageFlipScene scene) {
    return scene.effectiveRenderDirection ?? scene.direction;
  }

  StPageFlipShadowData? _sceneShadow(StPageFlipScene scene) {
    return scene.renderFrame?.shadow ?? scene.shadow;
  }

  ArticleFlipPipelineOutput? _resolveArticleFlipPipelineOutput(
    StPageFlipScene scene, {
    required Set<int> dynamicallyRenderedPages,
  }) {
    final renderFrame = scene.renderFrame;
    final direction = _sceneRenderDirection(scene);
    if (renderFrame == null || direction == null) {
      return null;
    }
    final modeLayout = _articleReaderModeStrategy.resolveLayout(
      scene: scene,
      dynamicallyRenderedPages: dynamicallyRenderedPages,
    );
    final textureBinding = _textureBindingForScene(scene);
    final input = ArticleFlipPipelineInput(
      scene: scene,
      renderFrame: renderFrame,
      pageSize: Size(scene.layout.bounds.pageWidth, scene.layout.bounds.height),
      modeLayout: modeLayout,
      textureBinding: textureBinding,
      textureBundle: null,
    );
    final pipeline = switch (direction) {
      StPageFlipDirection.forward => _forwardFlipPipeline,
      StPageFlipDirection.back => _backwardFlipPipeline,
    };
    final output = pipeline.resolve(input);
    // Keep the mapper on the hot path so diagnostics evolve from pipeline
    // output instead of from ad hoc renderer branches.
    _articleReaderDebugMapper.mapPipelineOutput(output: output, input: input);
    return output;
  }

  String _sceneSignature(StPageFlipScene scene) {
    final renderFrame = scene.renderFrame;
    return <Object?>[
      scene.state.name,
      scene.currentSpreadIndex,
      scene.currentPageIndex,
      scene.visibleSpread.leftPageIndex,
      scene.visibleSpread.rightPageIndex,
      scene.flippingPageIndex,
      scene.bottomPageIndex,
      scene.direction?.name,
      scene.effectiveRenderDirection?.name,
      renderFrame?.progress.toStringAsFixed(4),
      renderFrame?.corner.name,
    ].join('|');
  }

  void _scheduleSceneReport(StPageFlipScene scene) {
    if (widget.onSceneChanged == null) {
      return;
    }
    final signature = _sceneSignature(scene);
    if (signature == _lastReportedSceneSignature) {
      return;
    }
    _pendingReportedScene = scene;
    if (_sceneReportScheduled) {
      return;
    }
    _sceneReportScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _sceneReportScheduled = false;
      final nextScene = _pendingReportedScene;
      _pendingReportedScene = null;
      if (!mounted || nextScene == null) {
        return;
      }
      final nextSignature = _sceneSignature(nextScene);
      if (nextSignature == _lastReportedSceneSignature) {
        return;
      }
      _lastReportedSceneSignature = nextSignature;
      widget.onSceneChanged?.call(nextScene);
    });
  }

  void _scheduleDebugStateReport(ArticleReadOnlyBookDebugState state) {
    if (widget.onDebugStateChanged == null) {
      return;
    }
    if (state.signature == _lastReportedDebugSignature) {
      return;
    }
    _pendingReportedDebugState = state;
    if (_debugReportScheduled) {
      return;
    }
    _debugReportScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _debugReportScheduled = false;
      final nextState = _pendingReportedDebugState;
      _pendingReportedDebugState = null;
      if (!mounted || nextState == null) {
        return;
      }
      if (nextState.signature == _lastReportedDebugSignature) {
        return;
      }
      _lastReportedDebugSignature = nextState.signature;
      widget.onDebugStateChanged?.call(nextState);
    });
  }

  double? _resolveDiagnosticGuideX({
    required Rect pageRect,
    required StPageFlipScene scene,
  }) {
    final renderFrame = scene.renderFrame;
    final backwardLeafFrame = renderFrame?.backwardLeafFrame;
    if (backwardLeafFrame != null) {
      return pageRect.left + pageRect.width * backwardLeafFrame.seamXNormalized;
    }
    if (renderFrame != null) {
      if (scene.direction == StPageFlipDirection.back) {
        return _resolveBackwardSeamGuideX(
          pageRect: pageRect,
          renderFrame: renderFrame,
          calculation: scene.calculation,
        );
      }
      return pageRect.left + renderFrame.timeline.basePivot;
    }
    final calculation = scene.calculation;
    if (calculation != null) {
      if (scene.direction == StPageFlipDirection.back) {
        return _resolveBackwardSeamGuideX(
          pageRect: pageRect,
          renderFrame: null,
          calculation: calculation,
        );
      }
      final position = calculation.getPosition();
      final normalizedX = scene.direction == StPageFlipDirection.back
          ? pageRect.width - position.dx.clamp(0.0, pageRect.width)
          : position.dx.clamp(0.0, pageRect.width);
      return pageRect.left + normalizedX;
    }
    return null;
  }

  ArticleReadOnlyBookDebugState _buildDiagnosticDebugState({
    required StPageFlipScene scene,
    required Rect pageRect,
    required ArticleReadOnlyBookRenderBranch renderBranch,
  }) {
    final direction = _sceneRenderDirection(scene);
    final renderFrame = scene.renderFrame;
    final backwardDiagnosticGeometry = _resolveBackwardDiagnosticGeometry(
      scene,
    );
    final backwardPageRect = _backwardPageRect(scene);
    final diagnosticBottomArea =
        renderFrame?.bottomClipArea ?? scene.calculation?.getBottomClipArea();
    final diagnosticFlippingArea =
        renderFrame?.flippingClipArea ??
        scene.calculation?.getFlippingClipArea();
    final requestedBinding = _textureBindingForScene(scene);
    final backwardBinding = _backwardSurfaceBindingForScene(scene);
    final backwardLeafFrame = _resolveBackwardLeafFrame(scene);
    final backwardDynamicOwnedPageSet = _resolveBackwardDynamicOwnedPageSet(
      scene,
    );
    final dynamicBottomBounds = _resolveDynamicLayerBounds(
      area: diagnosticBottomArea,
      anchor:
          renderFrame?.bottomAnchor ??
          scene.calculation?.getBottomPagePosition(),
      angle: 0,
      direction: direction,
      bounds: scene.layout.bounds,
      isFlippingPage: false,
    );
    final dynamicFlippingBounds =
        direction == StPageFlipDirection.back &&
            backwardDiagnosticGeometry != null
        ? backwardDiagnosticGeometry.sheetViewportBounds
        : _resolveDynamicLayerBounds(
            area: diagnosticFlippingArea,
            anchor:
                renderFrame?.flippingAnchor ??
                scene.calculation?.getActiveCorner(),
            angle: renderFrame?.angle ?? scene.calculation?.getAngle() ?? 0,
            direction: direction,
            bounds: scene.layout.bounds,
            isFlippingPage: true,
          );
    final dynamicFlippingGeometry =
        direction == StPageFlipDirection.back &&
            backwardDiagnosticGeometry != null
        ? null
        : _resolveDynamicLayerGeometry(
            area: diagnosticFlippingArea,
            anchor:
                renderFrame?.flippingAnchor ??
                scene.calculation?.getActiveCorner(),
            angle: renderFrame?.angle ?? scene.calculation?.getAngle() ?? 0,
            direction: direction,
            bounds: scene.layout.bounds,
            isFlippingPage: true,
          );
    final backwardFoldLine = backwardDiagnosticGeometry?.foldLineViewport;
    final backwardPageEdgeLine =
        backwardDiagnosticGeometry?.freeEdgeLineViewport;
    final backwardFoldSurfaceEdgeLine =
        backwardDiagnosticGeometry?.freeEdgeLineViewport;
    final backwardSurfaceAngle =
        renderFrame?.angle ?? scene.calculation?.getAngle();
    final backwardSurfaceShowsBack =
        direction == StPageFlipDirection.back && backwardSurfaceAngle != null
        ? backwardSurfaceAngle.abs() <= math.pi / 2
        : false;
    final backwardFoldDirection =
        direction == StPageFlipDirection.back && backwardSurfaceAngle != null
        ? (backwardSurfaceAngle >= 0 ? 'leftward' : 'rightward')
        : null;

    final backwardMovingPaintBounds =
        dynamicFlippingBounds ??
        dynamicFlippingGeometry?.clipViewportBounds ??
        dynamicFlippingGeometry?.surfaceViewportRect;
    final backwardFoldSurfaceBounds = _intersectNonEmptyRects(
      backwardMovingPaintBounds,
      pageRect,
    );

    /// BACK 真实绘制是一张书脊固定的纸：previous back 始终跟随 sheet，
    /// previous front 在后段叠加揭示；diagnostics 只跟随这条主线。
    final backBoundsViewport =
        backwardDiagnosticGeometry?.previousBackViewportBounds ??
        (backwardSurfaceShowsBack ? backwardFoldSurfaceBounds : null);
    final backwardBackFoldBounds = backBoundsViewport;
    final frontBoundsViewport =
        backwardDiagnosticGeometry?.previousFrontViewportBounds;
    final backwardFrontFoldVisible = frontBoundsViewport != null;
    final backwardFrontFoldBounds = backwardFrontFoldVisible
        ? frontBoundsViewport
        : null;
    final backwardFoldFrontBounds = backwardFrontFoldBounds;
    final backwardBackBounds = backwardBackFoldBounds;
    final backwardFrontBounds = backwardFoldFrontBounds;
    final backwardCurrentResidualBounds =
        backwardDiagnosticGeometry?.currentResidualViewportBounds ??
        backwardPageRect;
    final backwardMainline = direction == StPageFlipDirection.back
        ? 'paperFoldBackMainline'
        : null;
    final backwardFlippingSheetCount =
        direction == StPageFlipDirection.back &&
            renderBranch == ArticleReadOnlyBookRenderBranch.paperFoldDynamic &&
            scene.flippingPageIndex != null
        ? 1
        : null;
    final backwardLeafSheetId =
        direction == StPageFlipDirection.back && scene.flippingPageIndex != null
        ? 'mainlineLeaf:${scene.flippingPageIndex}'
        : null;
    final backwardFrontSheetId = backwardFrontFoldVisible
        ? backwardLeafSheetId
        : null;
    final backwardBackSheetId = direction == StPageFlipDirection.back
        ? backwardLeafSheetId
        : null;
    final backwardCurrentLayerPresent = direction == StPageFlipDirection.back
        ? true
        : null;
    final backwardMultiSliceViolation = direction == StPageFlipDirection.back
        ? backwardFlippingSheetCount != 1
        : null;
    List<Offset> rectToPolygon(Rect? rect) {
      if (rect == null || rect.isEmpty) {
        return const <Offset>[];
      }
      return <Offset>[
        rect.topLeft,
        rect.topRight,
        rect.bottomRight,
        rect.bottomLeft,
      ];
    }

    final backwardLocalClipPolygon =
        backwardDiagnosticGeometry?.sheetLocalPolygon ??
        dynamicFlippingGeometry?.localClipPolygon ??
        const <Offset>[];
    final backwardBackLocalPolygon =
        backwardDiagnosticGeometry?.previousBackLocalPolygon ??
        backwardLocalClipPolygon;
    final backwardFrontLocalPolygon =
        backwardDiagnosticGeometry?.previousFrontLocalPolygon ??
        const <Offset>[];
    final backwardCurrentResidualPolygon =
        backwardDiagnosticGeometry?.currentResidualViewportPolygon ??
        rectToPolygon(backwardCurrentResidualBounds);
    double? normalizedLineX(Offset top, Offset bottom) {
      if (pageRect.width <= 0) {
        return null;
      }
      return ((((top.dx + bottom.dx) / 2) - pageRect.left) / pageRect.width)
          .clamp(0.0, 1.0)
          .toDouble();
    }

    return ArticleReadOnlyBookDebugState(
      currentPageIndex: scene.currentPageIndex,
      turningPageIndex: scene.flippingPageIndex,
      underlayPageIndex: scene.bottomPageIndex,
      coveredPageIndex: scene.currentPageIndex,
      leftPageIndex: scene.visibleSpread.leftPageIndex,
      rightPageIndex: scene.visibleSpread.rightPageIndex,
      renderBranch: renderBranch,
      renderDirection: _sceneRenderDirection(scene),
      renderSceneReady: false,
      sessionHasBundle: false,
      requestedRectoPageIndex: requestedBinding?.rectoPageIndex,
      requestedVersoPageIndex: requestedBinding?.versoPageIndex,
      requestedBottomPageIndex: requestedBinding?.bottomPageIndex,
      activeRectoPageIndex: null,
      activeVersoPageIndex: null,
      activeBottomPageIndex: null,
      backwardCoveredPageIndex: backwardBinding?.coveredPageIndex,
      backwardLeafRectoPageIndex: backwardBinding?.leafRectoPageIndex,
      backwardLeafVersoPageIndex: backwardBinding?.leafVersoPageIndex,
      availableSnapshotIndices: const <int>[],
      pendingCaptureIndices: const <int>[],
      bottomClipBounds: dynamicBottomBounds,
      flippingClipBounds: dynamicFlippingBounds,
      frontBounds: direction == StPageFlipDirection.back
          ? backwardFrontBounds
          : null,
      backBounds: direction == StPageFlipDirection.back
          ? backwardBackBounds
          : null,
      flippingAnchor:
          renderFrame?.flippingAnchor ?? scene.calculation?.getActiveCorner(),
      bottomAnchor:
          renderFrame?.bottomAnchor ??
          scene.calculation?.getBottomPagePosition(),
      backwardCorner: _resolveBackwardCornerLabel(scene),
      backwardHinge: _resolveBackwardHinge(
        scene: scene,
        pageSize: pageRect.size,
      ),
      backwardSpineTop: _resolveBackwardSpineTop(scene),
      backwardSpineBottom: _resolveBackwardSpineBottom(
        scene: scene,
        pageSize: pageRect.size,
      ),
      backwardSeamX: _resolveBackwardSeamX(scene),
      backwardFoldX: backwardFoldLine == null
          ? null
          : ((backwardFoldLine.$1.dx + backwardFoldLine.$2.dx) / 2) -
                pageRect.left,
      backwardPageEdgeX: backwardPageEdgeLine == null
          ? null
          : ((backwardPageEdgeLine.$1.dx + backwardPageEdgeLine.$2.dx) / 2) -
                pageRect.left,
      backwardFoldSurfaceEdgeX: backwardFoldSurfaceEdgeLine == null
          ? null
          : ((backwardFoldSurfaceEdgeLine.$1.dx +
                        backwardFoldSurfaceEdgeLine.$2.dx) /
                    2) -
                pageRect.left,
      backwardFoldLineTop: backwardFoldLine?.$1,
      backwardFoldLineBottom: backwardFoldLine?.$2,
      backwardPageEdgeLineTop: backwardPageEdgeLine?.$1,
      backwardPageEdgeLineBottom: backwardPageEdgeLine?.$2,
      backwardFoldSurfaceEdgeLineTop: backwardFoldSurfaceEdgeLine?.$1,
      backwardFoldSurfaceEdgeLineBottom: backwardFoldSurfaceEdgeLine?.$2,
      backwardCoveredWidth: backwardFoldLine == null
          ? backwardLeafFrame?.coveredWidthNormalized
          : normalizedLineX(backwardFoldLine.$1, backwardFoldLine.$2),
      backwardRectoCoverage: backwardLeafFrame?.rectoCoverageNormalized,
      backwardVersoWidth: backwardLeafFrame?.versoRevealWidthNormalized,
      backwardRectoWidth: backwardLeafFrame?.totalRectoVisibleWidthNormalized,
      backwardBottomStart: backwardLeafFrame?.bottomRevealStartNormalized,
      backwardPhase: _resolveBackwardPhaseLabel(scene),
      backwardReplayFrontLayerCount: _resolveBackwardReplayFrontLayerCount(
        scene,
      ),
      backwardReplayBackSurfaceStrategy:
          _resolveBackwardReplayBackSurfaceStrategy(scene),
      backwardBottomLayerPageIndex: direction == StPageFlipDirection.back
          ? scene.bottomPageIndex
          : null,
      backwardFlippingLayerPageIndex: direction == StPageFlipDirection.back
          ? scene.flippingPageIndex
          : null,
      backwardDynamicOwnedPages: _sortedPageIndices(
        backwardDynamicOwnedPageSet,
      ),
      backwardStaticSuppressedPages: _resolveBackwardStaticSuppressedPages(
        scene: scene,
        dynamicOwnedPages: backwardDynamicOwnedPageSet,
      ),
      backwardReplaySlices: direction == StPageFlipDirection.back
          ? 'route=paperFoldBackwardMainline/mainline=paperFoldBackMainline/flipping=singleTurningSheet/frontEnabled=$backwardFrontFoldVisible/currentLayerPresent=${backwardCurrentLayerPresent ?? false}/multiSliceViolation=${backwardMultiSliceViolation ?? true}'
          : _resolveBackwardReplaySliceLabel(
              backwardLeafFrame,
              scene,
              pageRect: pageRect,
              frontPaintBounds: backwardFrontBounds,
              backPaintBounds: backwardBackBounds,
              surfaceAngle: backwardSurfaceAngle,
              flippingSheetCount: backwardFlippingSheetCount ?? 0,
              frontSheetId: backwardFrontSheetId,
              backSheetId: backwardBackSheetId,
              currentLayerPresent: backwardCurrentLayerPresent ?? false,
              multiSliceViolation: backwardMultiSliceViolation ?? true,
            ),
      backwardCompositeMode: _hasBackwardPaperFoldFrame(scene)
          ? 'paperFoldBackwardMainline'
          : null,
      backwardFrontPaintBounds: backwardFrontBounds,
      backwardBackPaintBounds: backwardBackBounds,
      backwardLaidFrontPaintBounds: backwardFrontBounds,
      backwardFoldSurfacePaintBounds: backwardFoldSurfaceBounds,
      backwardCurrentResidualBounds: backwardCurrentResidualBounds,
      backwardMainline: backwardMainline,
      backwardFlippingSheetCount: backwardFlippingSheetCount,
      backwardFrontSheetId: backwardFrontSheetId,
      backwardBackSheetId: backwardBackSheetId,
      backwardCurrentLayerPresent: backwardCurrentLayerPresent,
      backwardMultiSliceViolation: backwardMultiSliceViolation,
      backwardPaintedVersoWidth: backwardLeafFrame?.versoRevealWidthNormalized,
      backwardBackPixelSurfaceStrategy: _hasBackwardPaperFoldFrame(scene)
          ? 'paperFoldBackMainlineSurface'
          : null,
      backwardSurfaceOrigin: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry?.softGeometry.surfaceOrigin
          : null,
      backwardSurfaceViewportRect: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry?.softGeometry.surfaceViewportRect
          : null,
      backwardPivotLocal: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry?.softGeometry.pivotLocal
          : null,
      backwardPivotViewport: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry == null
                ? null
                : transformSoftLayerLocalPoint(
                    point: backwardDiagnosticGeometry.softGeometry.pivotLocal,
                    geometry: backwardDiagnosticGeometry.softGeometry,
                  )
          : null,
      backwardClipLocalBounds: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry?.sheetLocalBounds
          : null,
      backwardClipViewportBounds: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry?.sheetViewportBounds
          : null,
      backwardFrontCoverageRatio: backwardLeafFrame?.rectoCoverageNormalized,
      backwardLeftSpineLocked:
          direction == StPageFlipDirection.back &&
              backwardDiagnosticGeometry?.sheetLocalBounds != null
          ? (backwardDiagnosticGeometry!.sheetLocalBounds!.left).abs() <= 1.0
          : (backwardPageEdgeLine == null
                ? null
                : (normalizedLineX(
                            backwardPageEdgeLine.$1,
                            backwardPageEdgeLine.$2,
                          ) ??
                          0) <=
                      0.005),
      backwardSimulatorVisualPhase: _resolveBackwardSimulatorVisualPhase(
        backwardLeafFrame,
      ),
      backwardEdgeEnteredPage: direction == StPageFlipDirection.back
          ? backBoundsViewport != null
          : null,
      backwardOverlayClippedToPaper: direction == StPageFlipDirection.back
          ? !widget.debugPureBackwardGeometry && backBoundsViewport != null
          : null,
      backwardBackVertexCount: backwardBackLocalPolygon.length >= 3
          ? backwardBackLocalPolygon.length
          : null,
      backwardFrontVertexCount: backwardFrontLocalPolygon.length >= 3
          ? backwardFrontLocalPolygon.length
          : null,
      backwardEdgeParallelToFold:
          backwardFoldLine == null || backwardPageEdgeLine == null
          ? null
          : linesAreParallel(backwardFoldLine, backwardPageEdgeLine),
      backwardBackPolygonPoints: backwardBackLocalPolygon.length >= 3
          ? articleDiagnosticPolygonSignature(backwardBackLocalPolygon)
          : null,
      backwardFrontPolygonPoints: backwardFrontLocalPolygon.length >= 3
          ? articleDiagnosticPolygonSignature(backwardFrontLocalPolygon)
          : null,
      backwardSheetPolygonPoints: backwardLocalClipPolygon.length >= 3
          ? articleDiagnosticPolygonSignature(backwardLocalClipPolygon)
          : null,
      backwardBottomClipPolygonPoints:
          diagnosticBottomArea != null && diagnosticBottomArea.length >= 3
          ? articleDiagnosticPolygonSignature(diagnosticBottomArea)
          : null,
      backwardCurrentPolygonPoints: backwardCurrentResidualPolygon.length >= 3
          ? articleDiagnosticPolygonSignature(backwardCurrentResidualPolygon)
          : null,
      backwardFoldDirection: backwardFoldDirection,
      guideX: _resolveDiagnosticGuideX(pageRect: pageRect, scene: scene),
    );
  }

  ArticleReadOnlyBookRenderBranch _buildForwardDynamicLayers({
    required BuildContext context,
    required StPageFlipScene scene,
    required Size pageSize,
    required StPageFlipDirection direction,
    required List<Widget> layers,
  }) {
    final calculation = scene.calculation;
    final renderFrame = scene.renderFrame;
    final bottomArea =
        renderFrame?.bottomClipArea ?? calculation?.getBottomClipArea();
    final bottomAnchor =
        renderFrame?.bottomAnchor ?? calculation?.getBottomPagePosition();
    if (bottomArea != null &&
        bottomAnchor != null &&
        scene.bottomPageIndex != null) {
      layers.add(
        _buildDynamicPageLayer(
          context: context,
          pageIndex: scene.bottomPageIndex!,
          pageSize: pageSize,
          area: bottomArea,
          anchor: bottomAnchor,
          angle: 0,
          scene: scene,
          direction: direction,
          density:
              scene.flippingPageDensity ??
              scene.bottomPageDensity ??
              StPageFlipDensity.soft,
          isFlippingPage: false,
        ),
      );
    }

    final flippingArea =
        renderFrame?.flippingClipArea ?? calculation?.getFlippingClipArea();
    final flippingAnchor =
        renderFrame?.flippingAnchor ?? calculation?.getActiveCorner();
    final flippingAngle = renderFrame?.angle ?? calculation?.getAngle();
    if (flippingArea != null &&
        flippingAnchor != null &&
        flippingAngle != null &&
        scene.flippingPageIndex != null) {
      layers.add(
        _buildDynamicPageLayer(
          context: context,
          pageIndex: scene.flippingPageIndex!,
          pageSize: pageSize,
          area: flippingArea,
          anchor: flippingAnchor,
          angle: flippingAngle,
          scene: scene,
          direction: direction,
          density: scene.flippingPageDensity ?? StPageFlipDensity.soft,
          isFlippingPage: true,
        ),
      );
    }
    return ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
  }

  ArticleReadOnlyBookRenderBranch _buildBackwardDynamicLayers({
    required BuildContext context,
    required StPageFlipScene scene,
    required Size pageSize,
    required List<Widget> layers,
  }) {
    final frame = scene.renderFrame;
    if (!_hasBackwardPaperFoldFrame(scene) || frame == null) {
      return ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
    }
    if (scene.flippingPageIndex == null) {
      return ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
    }

    if (scene.bottomPageIndex != null && frame.bottomClipArea.length >= 3) {
      layers.add(
        _buildDynamicPageLayer(
          context: context,
          pageIndex: scene.bottomPageIndex!,
          pageSize: pageSize,
          area: frame.bottomClipArea,
          anchor: frame.bottomAnchor,
          angle: 0,
          scene: scene,
          direction: StPageFlipDirection.back,
          visualGeometryDirection: frame.visualGeometryDirection,
          density: scene.bottomPageDensity ?? StPageFlipDensity.soft,
          isFlippingPage: false,
        ),
      );
    }

    if (frame.flippingClipArea.length >= 3) {
      layers.add(
        _buildDynamicPageLayer(
          context: context,
          pageIndex: scene.flippingPageIndex!,
          pageSize: pageSize,
          area: frame.flippingClipArea,
          anchor: frame.flippingAnchor,
          angle: frame.angle,
          scene: scene,
          direction: StPageFlipDirection.back,
          visualGeometryDirection: frame.visualGeometryDirection,
          density: scene.flippingPageDensity ?? StPageFlipDensity.soft,
          isFlippingPage: true,
          backwardLeafFrame: frame.backwardLeafFrame,
          backwardFoldLine: frame.backwardProjectedFrame?.foldLine,
          backwardFreeEdgeLine:
              frame.backwardProjectedFrame?.projectedRightEdgeLine,
        ),
      );
    }

    if (widget.debugPureBackwardGeometry) {
      layers.add(_buildBackwardGeometryGuideLayer(scene));
    }
    return ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
  }

  Widget _buildBackwardGeometryGuideLayer(StPageFlipScene scene) {
    final geometry = _resolveBackwardDiagnosticGeometry(scene);
    final foldLine = geometry?.foldLineViewport;
    if (foldLine == null) {
      return const SizedBox.shrink();
    }
    return Positioned.fill(
      child: IgnorePointer(
        child: CustomPaint(
          painter: _BackwardGeometryGuidePainter(
            foldLine: foldLine,
            freeEdgeLine: geometry?.freeEdgeLineViewport,
          ),
        ),
      ),
    );
  }

  bool _shouldCommitPageFlip({
    required StPageFlipController controller,
    required StPageFlipDirection direction,
    required double progress,
    required Velocity velocity,
    Offset? dragStart,
    Offset? dragLatest,
    DateTime? dragStartedAt,
  }) {
    final directionSign = direction == StPageFlipDirection.forward ? -1.0 : 1.0;
    final directionalVelocity = velocity.pixelsPerSecond.dx * directionSign;
    final directionalDistance = dragStart != null && dragLatest != null
        ? (dragLatest.dx - dragStart.dx) * directionSign
        : 0.0;
    final dragRatio = (directionalDistance / controller.layout.bounds.pageWidth)
        .clamp(0.0, 1.0)
        .toDouble();
    final elapsedMs = dragStartedAt == null
        ? 0
        : DateTime.now().difference(dragStartedAt).inMilliseconds;
    final crossedMidpoint = progress > 0.44;
    final sustainedPull = dragRatio > 0.24;
    final deliberateCornerLift = progress > 0.14 && dragRatio > 0.08;
    final deliberateDrag = progress > 0.2 && dragRatio > 0.16;
    final decisiveVelocity = directionalVelocity > 260;
    final quickLift =
        elapsedMs > 0 && elapsedMs < 420 && dragRatio > 0.06 && progress > 0.12;
    final assistedSnap = deliberateCornerLift && directionalVelocity > 120;
    return crossedMidpoint ||
        sustainedPull ||
        deliberateDrag ||
        decisiveVelocity ||
        quickLift ||
        assistedSnap;
  }

  String _cornerNameFromPageFlip(
    StPageFlipCorner corner,
    StPageFlipDirection direction,
  ) {
    if (corner == StPageFlipCorner.top) {
      return direction == StPageFlipDirection.forward
          ? 'top_right'
          : 'top_left';
    }
    return direction == StPageFlipDirection.forward
        ? 'bottom_right'
        : 'bottom_left';
  }

  void _emitPageCurlAbortForPlan(StPageFlipAnimationPlan plan) {
    final calculation = _pageFlipScene?.calculation;
    final progress = ((calculation?.getFlippingProgress() ?? 0) / 100)
        .clamp(0.0, 1.0)
        .toDouble();
    _clearPageTransition();
    if (progress <= 0) {
      return;
    }
    widget.onPageCurlAborted?.call(
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
    if (!mounted) {
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
    setState(() {});
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
    controller.completeAnimation(plan);
    _activePageFlipAnimation = null;
    _lastAnimationFrameIndex = -1;
    final nextPage = controller.currentPageIndex;
    if (!mounted) {
      return;
    }
    setState(() {
      _currentPage = nextPage;
    });
    if (plan.isTurned) {
      widget.onPageChanged?.call(_currentPage);
      _emitPageFlipCommit(fromPage: previousPage, toPage: _currentPage);
    }
  }

  void _runPageFlipAnimation(
    StPageFlipAnimationPlan plan, {
    bool reportAbort = false,
  }) {
    if (reportAbort) {
      _emitPageCurlAbortForPlan(plan);
    }
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
      widget.onOverflowNext?.call();
    } else {
      widget.onOverflowPrevious?.call();
    }
  }

  void _resetOverflowTracking() {
    _edgeOverflowDistance = 0;
    _pendingOverflowDirection = null;
    _overflowTriggered = false;
  }

  void _trackEdgeOverflow(Offset delta, StPageFlipDirection direction) {
    if (_pendingOverflowDirection != direction) {
      _pendingOverflowDirection = direction;
      _edgeOverflowDistance = 0;
    }
    _edgeOverflowDistance += delta.dx.abs();
    if (_edgeOverflowDistance >= _overflowSwitchDistance) {
      _triggerOverflow(direction);
    }
  }

  void _handleStageTapUp(TapUpDetails details) {
    if (!_showsPageCurl || _hasActivePageCurlAnimation) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    final plan = controller.flip(details.localPosition);
    if (plan == null) {
      return;
    }
    _startPageTransition('page_curl');
    setState(() {});
    _runPageFlipAnimation(plan);
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
    final direction = controller.directionForGlobalPoint(startPosition);
    if (!controller.canFlipDirection(direction)) {
      _pendingOverflowDirection = direction;
      _edgeOverflowDistance = 0;
      return;
    }
    _startPageTransition('page_curl');
    controller.fold(startPosition);
    if ((localPosition - startPosition).distance > 0) {
      controller.fold(localPosition);
    }
    setState(() {});
  }

  void _handleStagePanUpdate(Offset localPosition, Offset delta) {
    if (!_showsPageCurl || _hasActivePageCurlAnimation) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    _latestDragGlobalPosition = localPosition;
    final direction = controller.directionForGlobalPoint(localPosition);
    if (!controller.canFlipDirection(direction)) {
      _trackEdgeOverflow(delta, direction);
      return;
    }
    controller.fold(localPosition);
    setState(() {});
  }

  void _handleStagePanCancel() {
    _pointerDownLocalPosition = null;
    _dragStartGlobalPosition = null;
    _latestDragGlobalPosition = null;
    _dragStartedAt = null;
    _resetOverflowTracking();
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    controller.cancelInteraction();
    _clearPageTransition();
    setState(() {});
  }

  void _handleStagePanEnd(Velocity velocity) {
    final controller = _pageFlipController;
    final dragStart = _dragStartGlobalPosition;
    final dragLatest = _latestDragGlobalPosition;
    final dragStartedAt = _dragStartedAt;
    _pointerDownLocalPosition = null;
    _dragStartGlobalPosition = null;
    _latestDragGlobalPosition = null;
    _dragStartedAt = null;
    if (controller == null) {
      _resetOverflowTracking();
      return;
    }
    if (dragStart != null) {
      final direction = controller.directionForGlobalPoint(dragStart);
      if (!controller.canFlipDirection(direction)) {
        final velocityX = velocity.pixelsPerSecond.dx;
        if (!_overflowTriggered && velocityX.abs() >= _overflowSwitchVelocity) {
          _triggerOverflow(direction);
        }
        _resetOverflowTracking();
        return;
      }
    }

    var plan = controller.stopMove();
    _resetOverflowTracking();
    if (plan == null) {
      controller.cancelInteraction();
      setState(() {});
      return;
    }
    if (!plan.isTurned) {
      final direction =
          controller.scene.direction ??
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
      final shouldCommit = _shouldCommitPageFlip(
        controller: controller,
        direction: direction,
        progress: progress,
        velocity: velocity,
        dragStart: dragStart,
        dragLatest: dragLatest,
        dragStartedAt: dragStartedAt,
      );
      if (shouldCommit) {
        plan = direction == StPageFlipDirection.forward
            ? controller.flipNext(corner)
            : controller.flipPrev(corner);
      }
    }
    if (plan == null) {
      controller.cancelInteraction();
      setState(() {});
      return;
    }
    if (!plan.isTurned) {
      _runPageFlipAnimation(plan, reportAbort: true);
    } else {
      _runPageFlipAnimation(plan);
    }
  }

  void _handleStageMouseHover(PointerHoverEvent event) {
    if (!_showsPageCurl || _hasActivePageCurlAnimation) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    final plan = controller.showCorner(event.localPosition);
    if (plan != null) {
      _runPageFlipAnimation(plan);
      return;
    }
    setState(() {});
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
    setState(() {});
  }

  void _handleStagePointerDown(PointerDownEvent event) {
    if (!_showsPageCurl) {
      return;
    }
    _pointerDownLocalPosition = event.localPosition;
    _pointerBridge.handleTouchStart(event.localPosition, () {});
  }

  void _handleStagePointerMove(PointerMoveEvent event) {
    if (!_showsPageCurl || _dragStartGlobalPosition != null) {
      return;
    }
    _pointerBridge.handleTouchMove(event.localPosition, () {});
  }

  void _handleStagePointerUp(PointerUpEvent event) {
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
      event.localPosition,
      pageHeight: controller.layout.bounds.height,
    );
    if (swipe == null || !controller.canFlipDirection(swipe.direction)) {
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

  void _handleStagePointerCancel(PointerCancelEvent event) {
    _pointerDownLocalPosition = null;
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
    widget.onPageFlipCommitted?.call(
      ArticleReaderPageFlipCommit(
        fromPage: fromPage,
        toPage: toPage,
        durationMs: DateTime.now().difference(startedAt).inMilliseconds,
        mechanism: mechanism,
      ),
    );
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification is ScrollStartNotification &&
        notification.dragDetails != null &&
        _pageTransitionStartedAt == null) {
      _startPageTransition(_useDegradedPager ? 'book_style_pager' : 'pager');
    } else if (notification is OverscrollNotification && !_overflowLocked) {
      if (notification.overscroll < 0) {
        _overflowLocked = true;
        widget.onOverflowPrevious?.call();
      } else if (notification.overscroll > 0) {
        _overflowLocked = true;
        widget.onOverflowNext?.call();
      }
    } else if (notification is ScrollEndNotification) {
      _overflowLocked = false;
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

  Rect _pageRectForStage(Size stageSize) {
    final availableWidth = math.max(
      1.0,
      stageSize.width - widget.pagePadding.horizontal,
    );
    final availableHeight = math.max(
      1.0,
      stageSize.height - widget.pagePadding.vertical,
    );
    final pageWidth = math.min(
      availableWidth,
      availableHeight * widget.metrics.aspectRatio,
    );
    final pageHeight = pageWidth / widget.metrics.aspectRatio;
    final left = (stageSize.width - pageWidth) / 2;
    final minTop = widget.pagePadding.top;
    final maxTop = math.max(
      minTop,
      stageSize.height - widget.pagePadding.bottom - pageHeight,
    );
    final preferredTop = (stageSize.height - pageHeight) / 2;
    final top = preferredTop.clamp(minTop, maxTop).toDouble();
    return Rect.fromLTWH(left, top, pageWidth, pageHeight);
  }

  Widget _buildPageSurfaceWidget(
    BuildContext context,
    int index,
    Size pageSize,
  ) {
    final debugSurface = widget.debugPageSurfaceBuilder?.call(
      context,
      index,
      pageSize,
    );
    if (debugSurface != null) {
      return SizedBox(
        width: pageSize.width,
        height: pageSize.height,
        child: debugSurface,
      );
    }
    final page = widget.pages[index];
    return ArticlePageShell(
      template: widget.template,
      fontPreset: widget.fontPreset,
      pageIndex: index,
      totalPages: widget.pages.length,
      aspectRatio: widget.metrics.aspectRatio,
      outerPadding: widget.metrics.outerPadding,
      contentPadding: widget.metrics.contentPadding,
      headerReservedHeight: widget.metrics.headerReservedHeight,
      footerReservedHeight: widget.metrics.footerReservedHeight,
      variant: ArticlePageShellVariant.readerSheet,
      showIndicator: false,
      footerLabel: widget.showFooterPageLabel
          ? '${index + 1}/${widget.pages.length}'
          : null,
      paperTexture: widget.paperTexture,
      child: index == 0 && widget.coverUrl.trim().isNotEmpty
          ? ArticleFrontispieceView(
              page: page,
              template: widget.template,
              fontPreset: widget.fontPreset,
              coverUrl: widget.coverUrl.trim(),
              paperTexture: widget.paperTexture,
            )
          : ArticlePageReadOnlyView(
              page: page,
              template: widget.template,
              fontPreset: widget.fontPreset,
              metrics: widget.metrics,
              paperTexture: widget.paperTexture,
            ),
    );
  }

  Widget _buildReaderPage(BuildContext context, int index, Size pageSize) {
    return SizedBox(
      width: pageSize.width,
      height: pageSize.height,
      child: RepaintBoundary(
        child: _buildPageSurfaceWidget(context, index, pageSize),
      ),
    );
  }

  Widget _buildMirroredReaderPage(
    BuildContext context,
    int index,
    Size pageSize,
  ) {
    return Transform.flip(
      flipX: true,
      child: SizedBox(
        width: pageSize.width,
        height: pageSize.height,
        child: _buildPageSurfaceWidget(context, index, pageSize),
      ),
    );
  }

  Widget _buildCachedPageSurface(
    BuildContext context,
    int pageIndex,
    Size pageSize, {
    required ArticlePageSurfaceKind kind,
  }) {
    final cacheKey =
        '${kind.name}:$pageIndex:${pageSize.width.toStringAsFixed(2)}:${pageSize.height.toStringAsFixed(2)}:${widget.template.name}:${widget.fontPreset.name}:${widget.coverUrl.trim().isNotEmpty ? 1 : 0}:${widget.showFooterPageLabel ? 1 : 0}:${widget.paperTexture?.name ?? 'none'}:${widget.debugPageSurfaceBuilder == null ? 'normal' : 'debug'}:${widget.debugBackPageSurfaceBuilder == null ? 'normalBack' : 'debugBack'}';
    return _pageSurfaceCache.putIfAbsent(cacheKey, () {
      switch (kind) {
        case ArticlePageSurfaceKind.front:
        case ArticlePageSurfaceKind.bottom:
          return _buildReaderPage(context, pageIndex, pageSize);
        case ArticlePageSurfaceKind.back:
          return _buildOpaqueBackPageSurface(
            context,
            pageIndex,
            pageSize,
            mirrorContent: true,
          );
      }
    });
  }

  Widget _buildOpaqueBackPageSurface(
    BuildContext context,
    int pageIndex,
    Size pageSize, {
    required bool mirrorContent,
    double contentOpacity = 0.72,
  }) {
    final debugSurface = widget.debugBackPageSurfaceBuilder?.call(
      context,
      pageIndex,
      pageSize,
    );
    if (debugSurface != null) {
      return SizedBox(
        width: pageSize.width,
        height: pageSize.height,
        child: debugSurface,
      );
    }
    final palette = resolveArticleTemplatePalette(context, widget.template);
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            Color.alphaBlend(
              AppColors.white.withValues(alpha: 0.22),
              palette.paperColor,
            ),
            palette.paperColor,
            Color.alphaBlend(
              palette.paperBorderColor.withValues(alpha: 0.12),
              palette.paperColor,
            ),
          ],
        ),
        border: Border.all(
          color: palette.paperBorderColor.withValues(alpha: 0.22),
          width: AppSpacing.hairline,
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          ColoredBox(color: palette.paperColor),
          IgnorePointer(
            child: Opacity(
              opacity: contentOpacity,
              child: mirrorContent
                  ? _buildMirroredReaderPage(context, pageIndex, pageSize)
                  : _buildReaderPage(context, pageIndex, pageSize),
            ),
          ),
          IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                  colors: <Color>[
                    palette.paperBorderColor.withValues(alpha: 0.08),
                    AppColors.transparent,
                    palette.shadowColor.withValues(alpha: 0.04),
                  ],
                  stops: const <double>[0.0, 0.58, 1.0],
                ),
              ),
            ),
          ),
          IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    AppColors.white.withValues(alpha: 0.14),
                    AppColors.transparent,
                    palette.shadowColor.withValues(alpha: 0.06),
                  ],
                  stops: const <double>[0.0, 0.42, 1.0],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFlippingSurfaceOverlay({
    required ArticleTemplatePalette palette,
    required StPageFlipDirection direction,
    required double progress,
    required bool showBackside,
  }) {
    final settledProgress = progress.clamp(0.0, 1.0).toDouble();
    final lift = Curves.easeOutCubic.transform(settledProgress);
    final edgeAlignment = direction == StPageFlipDirection.forward
        ? Alignment.centerRight
        : Alignment.centerLeft;
    final oppositeEdge = direction == StPageFlipDirection.forward
        ? Alignment.centerLeft
        : Alignment.centerRight;
    final shadowColor = palette.shadowColor.withValues(
      alpha: (showBackside ? 0.035 : 0.12) + (lift * 0.055),
    );
    final tunnelAlpha = (showBackside ? 0.028 : 0.08) + (lift * 0.04);
    final tunnelColor = AppColors.black.withValues(
      alpha: tunnelAlpha.clamp(0.0, 1.0).toDouble(),
    );
    final highlightColor = AppColors.white.withValues(
      alpha: (showBackside ? 0.12 : 0.14) + (lift * 0.08),
    );
    return IgnorePointer(
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  AppColors.white.withValues(alpha: showBackside ? 0.13 : 0.16),
                  AppColors.transparent,
                  tunnelColor,
                ],
                stops: const <double>[0.0, 0.5, 1.0],
              ),
            ),
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: edgeAlignment,
                end: oppositeEdge,
                colors: <Color>[
                  shadowColor,
                  palette.paperBorderColor.withValues(
                    alpha: 0.08 + lift * 0.06,
                  ),
                  AppColors.transparent,
                ],
                stops: const <double>[0.0, 0.28, 0.9],
              ),
            ),
          ),
          Align(
            alignment: edgeAlignment,
            child: FractionallySizedBox(
              widthFactor: (showBackside ? 0.16 : 0.08) + (lift * 0.04),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: edgeAlignment,
                    end: oppositeEdge,
                    colors: <Color>[highlightColor, AppColors.transparent],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSoftFlippingPageSurface({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required StPageFlipDirection direction,
    required double progress,
    double visualAngle = 0,
    int? backFacePageIndex,
    ArticlePageBackwardLeafFrame? backwardLeafFrame,
    _PageLine? backwardFoldLine,
    _PageLine? backwardFreeEdgeLine,
    List<Offset> sheetLocalPolygon = const <Offset>[],
  }) {
    final palette = resolveArticleTemplatePalette(context, widget.template);
    if (direction == StPageFlipDirection.back && backwardLeafFrame != null) {
      return _buildBackwardRectoVersoFlippingPageSurface(
        context: context,
        pageIndex: pageIndex,
        backFacePageIndex: backFacePageIndex ?? pageIndex,
        pageSize: pageSize,
        foldLine: backwardFoldLine,
        freeEdgeLine: backwardFreeEdgeLine,
        sheetLocalPolygon: sheetLocalPolygon,
        palette: palette,
        progress: progress,
      );
    }
    // 翻折页的正反面切换：前翻在翻起后显示背面；后翻是逆回放，
    // 90° 前显示 previousBack，越过 90° 后切回 previousFront。
    final bool showBackside;
    if (direction == StPageFlipDirection.back) {
      showBackside = visualAngle.abs() <= math.pi / 2;
    } else {
      showBackside = progress > 0.08;
    }
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        _buildCachedPageSurface(
          context,
          showBackside ? (backFacePageIndex ?? pageIndex) : pageIndex,
          pageSize,
          kind: showBackside
              ? ArticlePageSurfaceKind.back
              : ArticlePageSurfaceKind.front,
        ),
        _buildFlippingSurfaceOverlay(
          palette: palette,
          direction: direction,
          progress: progress,
          showBackside: showBackside,
        ),
      ],
    );
  }

  Widget _buildBackwardRectoVersoFlippingPageSurface({
    required BuildContext context,
    required int pageIndex,
    required int backFacePageIndex,
    required Size pageSize,
    required _PageLine? foldLine,
    required _PageLine? freeEdgeLine,
    required List<Offset> sheetLocalPolygon,
    required ArticleTemplatePalette palette,
    required double progress,
  }) {
    final facePolygons = _backwardFoldDerivedFacePolygons(
      pageSize: pageSize,
      foldLine: foldLine,
      freeEdgeLine: freeEdgeLine,
      sheetLocalPolygon: sheetLocalPolygon,
    );
    final children = <Widget>[
      if (facePolygons.verso.length >= 3)
        _buildBackwardSheetFacePolygon(
          context: context,
          pageIndex: backFacePageIndex,
          kind: ArticlePageSurfaceKind.back,
          pageSize: pageSize,
          polygon: facePolygons.verso,
        ),
      if (facePolygons.recto.length >= 3)
        _buildBackwardSheetFacePolygon(
          context: context,
          pageIndex: pageIndex,
          kind: ArticlePageSurfaceKind.front,
          pageSize: pageSize,
          polygon: facePolygons.recto,
        ),
      _buildBackwardRectoVersoFoldOverlay(
        foldLine: foldLine,
        palette: palette,
        progress: progress,
      ),
    ];
    return Stack(
      fit: StackFit.expand,
      clipBehavior: Clip.none,
      children: children,
    );
  }

  Widget _buildBackwardSheetFacePolygon({
    required BuildContext context,
    required int pageIndex,
    required ArticlePageSurfaceKind kind,
    required Size pageSize,
    required List<Offset> polygon,
  }) {
    return Positioned.fill(
      child: ClipPath(
        clipper: ArticlePolygonClipper(polygon),
        child: SizedBox(
          width: pageSize.width,
          height: pageSize.height,
          child: _buildCachedPageSurface(
            context,
            pageIndex,
            pageSize,
            kind: kind,
          ),
        ),
      ),
    );
  }

  Widget _buildBackwardRectoVersoFoldOverlay({
    required _PageLine? foldLine,
    required ArticleTemplatePalette palette,
    required double progress,
  }) {
    final safeFoldLine = foldLine;
    if (safeFoldLine == null) {
      return const SizedBox.shrink();
    }
    return IgnorePointer(
      child: CustomPaint(
        painter: _BackwardFoldBoundaryPainter(
          foldLine: safeFoldLine,
          color: palette.shadowColor.withValues(
            alpha: (0.18 + progress * 0.08).clamp(0.18, 0.26),
          ),
        ),
      ),
    );
  }

  Widget _buildBottomProjectedPageSurface({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required StPageFlipDirection direction,
    StPageFlipShadowData? shadow,
  }) {
    final palette = resolveArticleTemplatePalette(context, widget.template);
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        _buildCachedPageSurface(
          context,
          pageIndex,
          pageSize,
          kind: ArticlePageSurfaceKind.bottom,
        ),
        if (shadow != null)
          _buildBottomPageProjectionOverlay(
            shadow: shadow,
            direction: direction,
            pageSize: pageSize,
            palette: palette,
          ),
        IgnorePointer(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  AppColors.white.withValues(alpha: 0.05),
                  AppColors.transparent,
                  palette.shadowColor.withValues(alpha: 0.03),
                ],
                stops: const <double>[0.0, 0.36, 1.0],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildBottomPageProjectionOverlay({
    required StPageFlipShadowData shadow,
    required StPageFlipDirection direction,
    required Size pageSize,
    required ArticleTemplatePalette palette,
  }) {
    final edgeAlignment = direction == StPageFlipDirection.forward
        ? Alignment.centerLeft
        : Alignment.centerLeft;
    final oppositeEdge = direction == StPageFlipDirection.forward
        ? Alignment.centerRight
        : Alignment.centerRight;
    final widthFactor =
        (math.max(shadow.width, pageSize.width * 0.12) / pageSize.width)
            .clamp(0.12, 0.72)
            .toDouble();
    return IgnorePointer(
      child: Transform.rotate(
        angle: shadow.angle * 0.18,
        alignment: edgeAlignment,
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            Align(
              alignment: edgeAlignment,
              child: FractionallySizedBox(
                widthFactor: widthFactor,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: edgeAlignment,
                      end: oppositeEdge,
                      colors: <Color>[
                        AppColors.black.withValues(
                          alpha: shadow.opacity * 0.26,
                        ),
                        palette.shadowColor.withValues(
                          alpha: shadow.opacity * 0.14,
                        ),
                        AppColors.transparent,
                      ],
                      stops: const <double>[0.0, 0.32, 1.0],
                    ),
                  ),
                ),
              ),
            ),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    AppColors.black.withValues(alpha: shadow.opacity * 0.03),
                    AppColors.transparent,
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// StPageFlip native `HTMLPage.drawSoft` local clip formula.
  ///
  /// In single-page portrait BACK, the previous page lives on the invisible
  /// left-side symmetric plane and is projected around the visible current
  /// page's left edge (the spine). Therefore BACK must use `anchor.x - p.x`;
  /// using the forward `(p.x - anchor.x)` formula flips the sheet to the wrong
  /// side or pushes it into negative viewport coordinates.
  List<Offset> _localPolygonFromArea({
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
  }) {
    return area
        .map((point) {
          return _localPointFromAreaPoint(
            point: point,
            anchor: anchor,
            angle: angle,
            direction: direction,
          );
        })
        .toList(growable: false);
  }

  Offset _localPointFromAreaPoint({
    required Offset point,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
  }) {
    final translated = direction == StPageFlipDirection.back
        ? Offset(anchor.dx - point.dx, point.dy - anchor.dy)
        : Offset(point.dx - anchor.dx, point.dy - anchor.dy);
    return rotatePoint(translated, Offset.zero, angle);
  }

  ArticlePageCurlCorner? _stageCornerForScene(StPageFlipScene scene) {
    final direction = _sceneRenderDirection(scene);
    final corner = scene.renderFrame?.corner ?? scene.corner;
    if (direction == null ||
        corner == null ||
        (scene.renderFrame == null && scene.calculation == null)) {
      return null;
    }
    return switch ((direction, corner)) {
      (StPageFlipDirection.forward, StPageFlipCorner.top) =>
        ArticlePageCurlCorner.topRight,
      (StPageFlipDirection.forward, StPageFlipCorner.bottom) =>
        ArticlePageCurlCorner.bottomRight,
      (StPageFlipDirection.back, StPageFlipCorner.top) =>
        ArticlePageCurlCorner.topLeft,
      (StPageFlipDirection.back, StPageFlipCorner.bottom) =>
        ArticlePageCurlCorner.bottomLeft,
    };
  }

  Widget _buildStaticBookPage(BuildContext context, int pageIndex, Rect rect) {
    return Positioned.fromRect(
      rect: rect,
      child: _buildCachedPageSurface(
        context,
        pageIndex,
        rect.size,
        kind: ArticlePageSurfaceKind.front,
      ),
    );
  }

  Widget _buildSoftPageLayer({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
    StPageFlipDirection? visualGeometryDirection,
    required StPageFlipBoundsRect bounds,
    bool isFlippingPage = false,
    double progress = 0,
    StPageFlipShadowData? projectedShadow,
    bool lockSpineLine = false,
    double? surfaceAngle,
    int? backFacePageIndex,
    ArticlePageBackwardLeafFrame? backwardLeafFrame,
    _PageLine? backwardFoldLine,
    _PageLine? backwardFreeEdgeLine,
  }) {
    final geometryDirection = visualGeometryDirection ?? direction;
    final geometryAngle = lockSpineLine ? 0.0 : angle;
    final layerOrigin = softLayerOrigin(
      anchor: anchor,
      pageSize: pageSize,
      direction: geometryDirection,
      isFlippingPage: isFlippingPage,
      lockSpineLine: lockSpineLine,
    );
    final polygon = _localPolygonFromArea(
      area: area,
      anchor: layerOrigin,
      angle: geometryAngle,
      direction: geometryDirection,
    );
    final localBackwardFoldLine = backwardFoldLine == null
        ? null
        : (
            _localPointFromAreaPoint(
              point: backwardFoldLine.$1,
              anchor: layerOrigin,
              angle: geometryAngle,
              direction: geometryDirection,
            ),
            _localPointFromAreaPoint(
              point: backwardFoldLine.$2,
              anchor: layerOrigin,
              angle: geometryAngle,
              direction: geometryDirection,
            ),
          );
    final localBackwardFreeEdgeLine = backwardFreeEdgeLine == null
        ? null
        : (
            _localPointFromAreaPoint(
              point: backwardFreeEdgeLine.$1,
              anchor: layerOrigin,
              angle: geometryAngle,
              direction: geometryDirection,
            ),
            _localPointFromAreaPoint(
              point: backwardFreeEdgeLine.$2,
              anchor: layerOrigin,
              angle: geometryAngle,
              direction: geometryDirection,
            ),
          );
    final position = convertBookPointToViewport(
      layerOrigin,
      bounds,
      direction: softLayerViewportDirection(geometryDirection),
    );
    return Positioned(
      left: position.dx,
      top: position.dy,
      width: pageSize.width,
      height: pageSize.height,
      child: Transform.rotate(
        angle: geometryAngle,
        alignment: softLayerAlignment(
          anchor: anchor,
          pageSize: pageSize,
          direction: geometryDirection,
          isFlippingPage: isFlippingPage,
          lockSpineLine: lockSpineLine,
        ),
        child: ClipPath(
          clipper: ArticlePolygonClipper(polygon),
          child: isFlippingPage
              ? _buildSoftFlippingPageSurface(
                  context: context,
                  pageIndex: pageIndex,
                  pageSize: pageSize,
                  direction: direction,
                  progress: progress,
                  visualAngle: surfaceAngle ?? angle,
                  backFacePageIndex: backFacePageIndex,
                  backwardLeafFrame: backwardLeafFrame,
                  backwardFoldLine: localBackwardFoldLine,
                  backwardFreeEdgeLine: localBackwardFreeEdgeLine,
                  sheetLocalPolygon: polygon,
                )
              : _buildBottomProjectedPageSurface(
                  context: context,
                  pageIndex: pageIndex,
                  pageSize: pageSize,
                  direction: direction,
                  shadow: projectedShadow,
                ),
        ),
      ),
    );
  }

  Widget _buildHardFlippingPageLayer({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required StPageFlipScene scene,
    required StPageFlipDirection direction,
  }) {
    final progress = _sceneProgress(scene) * 100;
    final hardAngle = direction == StPageFlipDirection.forward
        ? (90 * (200 - progress * 2)) / 100
        : (-90 * (200 - progress * 2)) / 100;
    final isRightPage =
        !(direction == StPageFlipDirection.forward &&
            scene.layout.orientation != StPageFlipOrientation.portrait);
    final pageRect = resolveBookPageRect(
      scene.layout,
      isRightPage: isRightPage,
    );
    return Positioned.fromRect(
      rect: pageRect,
      child: Transform(
        alignment: isRightPage ? Alignment.topLeft : Alignment.topRight,
        transform: Matrix4.identity()
          ..setEntry(3, 2, 0.002)
          ..rotateY(hardAngle * math.pi / 180),
        child: _buildCachedPageSurface(
          context,
          pageIndex,
          pageSize,
          kind: ArticlePageSurfaceKind.front,
        ),
      ),
    );
  }

  Widget _buildDynamicPageLayer({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipScene scene,
    required StPageFlipDirection direction,
    StPageFlipDirection? visualGeometryDirection,
    required StPageFlipDensity density,
    required bool isFlippingPage,
    bool lockSpineLine = false,
    double? surfaceAngle,
    int? backFacePageIndex,
    ArticlePageBackwardLeafFrame? backwardLeafFrame,
    _PageLine? backwardFoldLine,
    _PageLine? backwardFreeEdgeLine,
  }) {
    if (density == StPageFlipDensity.hard && isFlippingPage) {
      return _buildHardFlippingPageLayer(
        context: context,
        pageIndex: pageIndex,
        pageSize: pageSize,
        scene: scene,
        direction: direction,
      );
    }
    return _buildSoftPageLayer(
      context: context,
      pageIndex: pageIndex,
      pageSize: pageSize,
      area: area,
      anchor: anchor,
      angle: angle,
      direction: direction,
      visualGeometryDirection: visualGeometryDirection,
      bounds: scene.layout.bounds,
      isFlippingPage: isFlippingPage,
      progress: _sceneProgress(scene),
      projectedShadow: isFlippingPage ? null : _sceneShadow(scene),
      lockSpineLine: lockSpineLine,
      surfaceAngle: surfaceAngle,
      backFacePageIndex: backFacePageIndex,
      backwardLeafFrame: backwardLeafFrame,
      backwardFoldLine: backwardFoldLine,
      backwardFreeEdgeLine: backwardFreeEdgeLine,
    );
  }

  Widget _buildHotzoneMarkers(StPageFlipScene scene, Size stageSize) {
    const hotzoneExtent = 88.0;
    final rightPageRect = resolveBookPageRect(scene.layout, isRightPage: true);
    final leftAnchorRect =
        scene.layout.orientation == StPageFlipOrientation.portrait
        ? rightPageRect
        : resolveBookPageRect(scene.layout, isRightPage: false);
    final markerOffsets = <ArticlePageCurlCorner, Offset>{
      ArticlePageCurlCorner.topLeft: Offset(
        leftAnchorRect.left
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        leftAnchorRect.top
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
      ArticlePageCurlCorner.topRight: Offset(
        (rightPageRect.right - hotzoneExtent)
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        rightPageRect.top
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
      ArticlePageCurlCorner.bottomLeft: Offset(
        leftAnchorRect.left
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        (leftAnchorRect.bottom - hotzoneExtent)
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
      ArticlePageCurlCorner.bottomRight: Offset(
        (rightPageRect.right - hotzoneExtent)
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        (rightPageRect.bottom - hotzoneExtent)
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
    };
    return Stack(
      children: markerOffsets.entries
          .map((entry) {
            final hotzoneRect = Rect.fromLTWH(
              entry.value.dx,
              entry.value.dy,
              hotzoneExtent,
              hotzoneExtent,
            );
            return Positioned(
              left: hotzoneRect.left,
              top: hotzoneRect.top,
              width: hotzoneRect.width,
              height: hotzoneRect.height,
              child: IgnorePointer(
                child: SizedBox.expand(key: _hotzoneKey(entry.key)),
              ),
            );
          })
          .toList(growable: false),
    );
  }

  Widget _buildDegradedReaderStage(BuildContext context, Rect pageRect) {
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        CustomPaint(
          painter: ArticleReaderStagePainter(
            palette: resolveArticleTemplatePalette(context, widget.template),
            pageRect: pageRect,
            pageCount: widget.pages.length,
          ),
        ),
        NotificationListener<ScrollNotification>(
          onNotification: _handleScrollNotification,
          child: PageView.builder(
            key: TestKeys.articleBookStylePager,
            controller: _pageController,
            itemCount: widget.pages.length,
            onPageChanged: (index) {
              final previousPage = _currentPage;
              setState(() {
                _currentPage = index;
              });
              _emitPageFlipCommit(fromPage: previousPage, toPage: index);
              widget.onPageChanged?.call(index);
            },
            itemBuilder: (context, index) {
              return Align(
                alignment: Alignment.topCenter,
                child: Padding(
                  padding: EdgeInsets.only(top: pageRect.top),
                  child: _buildReaderPage(context, index, pageRect.size),
                ),
              );
            },
          ),
        ),
        Positioned.fill(
          child: IgnorePointer(
            child: CustomPaint(
              painter: ArticleBookStylePagerHintPainter(
                resolveArticleTemplatePalette(context, widget.template),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _wrapInteractiveStageLayers(List<Widget> layers) {
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: _handleStagePointerDown,
      onPointerMove: _handleStagePointerMove,
      onPointerUp: _handleStagePointerUp,
      onPointerCancel: _handleStagePointerCancel,
      child: MouseRegion(
        onHover: _handleStageMouseHover,
        onExit: _handleStageMouseExit,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onTapUp: _handleStageTapUp,
          onPanStart: (details) => _handleStagePanStart(details.localPosition),
          onPanUpdate: (details) =>
              _handleStagePanUpdate(details.localPosition, details.delta),
          onPanCancel: _handleStagePanCancel,
          onPanEnd: (details) => _handleStagePanEnd(details.velocity),
          child: Stack(fit: StackFit.expand, children: layers),
        ),
      ),
    );
  }

  Widget _buildInteractiveReaderStage(BuildContext context, Size stageSize) {
    _configurePageFlipController(stageSize);
    final scene = _pageFlipScene;
    if (scene == null) {
      return const SizedBox.shrink();
    }
    final pageSize = Size(
      scene.layout.bounds.pageWidth,
      scene.layout.bounds.height,
    );
    final bookRect = scene.layout.bounds.rect;
    final progress = _sceneProgress(scene);
    final direction = _sceneRenderDirection(scene);
    final pipelineOutput = _resolveArticleFlipPipelineOutput(
      scene,
      dynamicallyRenderedPages: const <int>{},
    );
    final paperFoldOwnedPages = direction == StPageFlipDirection.back
        ? (pipelineOutput?.staticSuppressionPages ??
              _resolveBackwardDynamicOwnedPageSet(scene))
        : const <int>{};
    final dynamicallyRenderedPages = <int>{...paperFoldOwnedPages};
    final layers = <Widget>[
      RepaintBoundary(
        child: CustomPaint(
          painter: ArticleReaderStagePainter(
            palette: resolveArticleTemplatePalette(context, widget.template),
            pageRect: bookRect,
            pageCount: widget.pages.length,
            activeCorner: _stageCornerForScene(scene),
            progress: progress,
          ),
        ),
      ),
    ];

    final leftPageIndex = scene.visibleSpread.leftPageIndex;
    final rightPageIndex = scene.visibleSpread.rightPageIndex;
    if (leftPageIndex != null &&
        !dynamicallyRenderedPages.contains(leftPageIndex)) {
      layers.add(
        _buildStaticBookPage(
          context,
          leftPageIndex,
          resolveBookPageRect(scene.layout, isRightPage: false),
        ),
      );
    }
    if (rightPageIndex != null &&
        !dynamicallyRenderedPages.contains(rightPageIndex)) {
      layers.add(
        _buildStaticBookPage(
          context,
          rightPageIndex,
          resolveBookPageRect(scene.layout, isRightPage: true),
        ),
      );
    }

    final pageRect = resolveBookPageRect(scene.layout, isRightPage: true);
    ArticleReadOnlyBookRenderBranch renderBranch = direction == null
        ? ArticleReadOnlyBookRenderBranch.staticStage
        : ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
    renderBranch = switch (direction) {
      StPageFlipDirection.back => _buildBackwardDynamicLayers(
        context: context,
        scene: scene,
        pageSize: pageSize,
        layers: layers,
      ),
      StPageFlipDirection.forward => _buildForwardDynamicLayers(
        context: context,
        scene: scene,
        pageSize: pageSize,
        direction: StPageFlipDirection.forward,
        layers: layers,
      ),
      null => ArticleReadOnlyBookRenderBranch.staticStage,
    };
    final debugState = _buildDiagnosticDebugState(
      scene: scene,
      pageRect: pageRect,
      renderBranch: renderBranch,
    );
    _scheduleSceneReport(scene);
    _scheduleDebugStateReport(debugState);

    layers.add(
      Positioned.fill(
        key: TestKeys.articlePageCurlLayer,
        child: _buildHotzoneMarkers(scene, stageSize),
      ),
    );
    return _wrapInteractiveStageLayers(layers);
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
        if (_useDegradedPager) {
          return _buildDegradedReaderStage(context, pageRect);
        }
        return _buildInteractiveReaderStage(context, stageSize);
      },
    );
  }
}
