import 'dart:async';
import 'dart:collection';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:quwoquan_app/design_system/pageflip/book_layout.dart';
import 'package:quwoquan_app/design_system/pageflip/controller.dart';
import 'package:quwoquan_app/design_system/pageflip/geometry.dart';
import 'package:quwoquan_app/design_system/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/design_system/pageflip/release_policy.dart';
import 'package:quwoquan_app/design_system/pageflip/spread_model.dart';
import 'package:quwoquan_app/design_system/pageflip/types.dart';
import 'package:quwoquan_app/design_system/gestures/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/design_system/gestures/immersive_pointer_gesture_layer.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

part 'media_page_flip_book_gestures.dart';
part 'media_page_flip_book_soft_surface.dart';
part 'media_page_flip_book_texture_cache.dart';

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
class MediaPageFlipMotionEvent {
  const MediaPageFlipMotionEvent({
    required this.direction,
    required this.motionProfile,
    required this.settleDuration,
    required this.reducedMotion,
    required this.committed,
  });

  final StPageFlipDirection direction;
  final String motionProfile;
  final Duration settleDuration;
  final bool reducedMotion;
  final bool committed;

  String get directionName {
    return switch (direction) {
      StPageFlipDirection.forward => 'forward',
      StPageFlipDirection.back => 'back',
    };
  }
}

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
    this.onMotionEvent,
    this.onTextureTransactionActiveChanged,
    this.onOverflowPrevious,
    this.onOverflowNext,
    this.gestureIntentController,
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
  final ValueChanged<MediaPageFlipMotionEvent>? onMotionEvent;
  final ValueChanged<bool>? onTextureTransactionActiveChanged;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;
  final ImmersiveGestureIntentController? gestureIntentController;

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
  static const double _reducedMotionCommitDistance = AppSpacing.buttonHeight;

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
  Offset? _latestDragLocalPosition;
  DateTime? _dragStartedAt;
  StPageFlipDirection? _activeDragDirection;
  StPageFlipCorner? _activeDragCorner;
  StPageFlipDirection? _pendingOverflowDirection;
  double _edgeOverflowDistance = 0;
  bool _dragActive = false;
  bool _textureTransactionActive = false;
  bool _overflowTriggered = false;
  bool _captureScheduled = false;
  bool _captureInFlight = false;
  bool _deferredDirectTextureRefresh = false;
  bool _reducedMotionTurnCommitted = false;
  int _viewportCaptureGeneration = 0;
  int _lastAnimationFrameIndex = -1;
  late int _currentPage;

  int get _safeInitialPage {
    if (widget.pageCount <= 0) {
      return 0;
    }
    return widget.initialPage.clamp(0, widget.pageCount - 1).toInt();
  }

  void _rebuild() {
    if (mounted) {
      setState(() {});
    }
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
        _refreshDirectTextureSnapshots();
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
        final dynamicLayers = _buildDynamicLayers(scene);
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

  Widget _buildStaticPage(BuildContext context, Rect pageRect, int pageIndex) {
    return Positioned.fromRect(
      rect: pageRect,
      child: KeyedSubtree(
        key: ValueKey<String>('media-pageflip-static-page-$pageIndex'),
        child: widget.pageBuilder(context, pageIndex),
      ),
    );
  }
}
