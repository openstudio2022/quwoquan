import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/pageflip/backward_render_frame_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/forward_render_frame_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/reverse_curl_calculation.dart';
import 'package:quwoquan_app/ui/content/pageflip/spread_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class StPageFlipAnimationPlan {
  const StPageFlipAnimationPlan({
    required this.frames,
    required this.duration,
    required this.isTurned,
    required this.needReset,
    required this.direction,
    required this.corner,
    this.reversePoses,
  });

  final List<Offset> frames;
  final Duration duration;
  final bool isTurned;
  final bool needReset;
  final StPageFlipDirection direction;
  final StPageFlipCorner corner;
  final List<ReverseFlipPose>? reversePoses;
}

@immutable
class StPageFlipScene {
  const StPageFlipScene({
    required this.state,
    required this.layout,
    required this.currentSpreadIndex,
    required this.currentPageIndex,
    required this.visibleSpread,
    required this.direction,
    required this.corner,
    required this.calculation,
    required this.shadow,
    required this.flippingPageIndex,
    required this.bottomPageIndex,
    required this.flippingPageDensity,
    required this.bottomPageDensity,
    required this.usesTemporaryCopy,
    this.reversePose,
    this.renderFrame,
  });

  final StPageFlipState state;
  final StPageFlipLayout layout;
  final int currentSpreadIndex;
  final int currentPageIndex;
  final StPageFlipVisibleSpread visibleSpread;
  final StPageFlipDirection? direction;
  final StPageFlipCorner? corner;
  final StPageFlipCalculation? calculation;
  final StPageFlipShadowData? shadow;
  final int? flippingPageIndex;
  final int? bottomPageIndex;
  final StPageFlipDensity? flippingPageDensity;
  final StPageFlipDensity? bottomPageDensity;
  final bool usesTemporaryCopy;
  final ReverseFlipPose? reversePose;
  final StPageFlipRenderFrame? renderFrame;

  StPageFlipDirection? get effectiveRenderDirection =>
      renderFrame?.renderDirection ?? direction;
}

class StPageFlipController {
  StPageFlipController({
    required StPageFlipSpreadModel spreadModel,
    required StPageFlipLayout layout,
    int initialPage = 0,
    this.flippingTimeMs = 1000,
    this.maxShadowOpacity = 1.0,
  }) : _spreadModel = spreadModel,
       _layout = layout {
    setCurrentPage(initialPage);
  }

  final int flippingTimeMs;
  final double maxShadowOpacity;
  StPageFlipSpreadModel _spreadModel;
  StPageFlipLayout _layout;
  StPageFlipCalculation? _calculation;
  StPageFlipState _state = StPageFlipState.read;
  StPageFlipDirection? _direction;
  StPageFlipCorner? _corner;
  StPageFlipShadowData? _shadow;
  StPageFlipRenderFrame? _renderFrame;
  int _currentSpreadIndex = 0;
  int _currentPageIndex = 0;

  StPageFlipLayout get layout => _layout;

  int get currentPageIndex => _currentPageIndex;

  int get currentSpreadIndex => _currentSpreadIndex;

  StPageFlipState get state => _state;

  StPageFlipScene get scene {
    final visibleSpread = _spreadModel.visibleSpreadForIndex(
      _currentSpreadIndex,
      _layout.orientation,
    );
    final flippingPageIndex = _direction == null
        ? null
        : _spreadModel.getFlippingPageIndex(
            direction: _direction!,
            currentSpreadIndex: _currentSpreadIndex,
            orientation: _layout.orientation,
          );
    final bottomPageIndex = _direction == null
        ? null
        : _spreadModel.getBottomPageIndex(
            direction: _direction!,
            currentSpreadIndex: _currentSpreadIndex,
            orientation: _layout.orientation,
          );
    return StPageFlipScene(
      state: _state,
      layout: _layout,
      currentSpreadIndex: _currentSpreadIndex,
      currentPageIndex: _currentPageIndex,
      visibleSpread: visibleSpread,
      direction: _direction,
      corner: _corner,
      calculation: _calculation,
      shadow: _shadow,
      flippingPageIndex: flippingPageIndex,
      bottomPageIndex: bottomPageIndex,
      flippingPageDensity: flippingPageIndex == null
          ? null
          : _spreadModel.densityForPage(flippingPageIndex),
      bottomPageDensity: bottomPageIndex == null
          ? null
          : _spreadModel.densityForPage(bottomPageIndex),
      usesTemporaryCopy:
          _direction != null &&
          _spreadModel.usesTemporaryCopyForFlipping(
            direction: _direction!,
            orientation: _layout.orientation,
          ),
      reversePose: _renderFrame?.reversePose,
      renderFrame: _renderFrame,
    );
  }

  void updateConfiguration({
    required StPageFlipSpreadModel spreadModel,
    required StPageFlipLayout layout,
    int? currentPage,
  }) {
    final targetPage = currentPage ?? _currentPageIndex;
    final preservesCurrentPage = targetPage == _currentPageIndex;
    final preservesSpread =
        spreadModel.pageCount == _spreadModel.pageCount &&
        spreadModel.showCover == _spreadModel.showCover;
    final preservesLayout = _sameLayout(layout, _layout);
    _spreadModel = spreadModel;
    _layout = layout;
    if (preservesCurrentPage && preservesSpread && preservesLayout) {
      return;
    }
    setCurrentPage(targetPage);
  }

  void setCurrentPage(int pageIndex) {
    if (_spreadModel.pageCount == 0) {
      _currentSpreadIndex = 0;
      _currentPageIndex = 0;
      _renderFrame = null;
      return;
    }
    final safePage = pageIndex.clamp(0, _spreadModel.pageCount - 1).toInt();
    final spreadIndex =
        _spreadModel.getSpreadIndexByPage(safePage, _layout.orientation) ?? 0;
    _currentSpreadIndex = spreadIndex;
    _currentPageIndex = _spreadModel
        .visibleSpreadForIndex(spreadIndex, _layout.orientation)
        .currentPageIndex;
    _renderFrame = null;
  }

  bool canFlipDirection(StPageFlipDirection direction) {
    final spreadCount = _spreadModel.spreadCountFor(_layout.orientation);
    if (spreadCount <= 1) {
      return false;
    }
    if (direction == StPageFlipDirection.forward) {
      return _currentSpreadIndex < spreadCount - 1;
    }
    return _currentSpreadIndex > 0;
  }

  StPageFlipDirection directionForGlobalPoint(Offset globalPos) {
    return _directionByPoint(
      convertViewportPointToBook(globalPos, _layout.bounds),
    );
  }

  StPageFlipCorner cornerForGlobalPoint(Offset globalPos) {
    final bookPos = convertViewportPointToBook(globalPos, _layout.bounds);
    return bookPos.dy >= _layout.bounds.height / 2
        ? StPageFlipCorner.bottom
        : StPageFlipCorner.top;
  }

  bool start(Offset globalPos) {
    _resetTransientState();

    final bookPos = convertViewportPointToBook(globalPos, _layout.bounds);
    final direction = _directionByPoint(bookPos);
    final corner = bookPos.dy >= _layout.bounds.height / 2
        ? StPageFlipCorner.bottom
        : StPageFlipCorner.top;

    if (!canFlipDirection(direction)) {
      return false;
    }

    final flippingPageIndex = _spreadModel.getFlippingPageIndex(
      direction: direction,
      currentSpreadIndex: _currentSpreadIndex,
      orientation: _layout.orientation,
    );
    final bottomPageIndex = _spreadModel.getBottomPageIndex(
      direction: direction,
      currentSpreadIndex: _currentSpreadIndex,
      orientation: _layout.orientation,
    );
    if (flippingPageIndex == null || bottomPageIndex == null) {
      return false;
    }

    _direction = direction;
    _corner = corner;
    _calculation = _createCalculation(direction: direction, corner: corner);
    return true;
  }

  void fold(Offset globalPos) {
    _setState(StPageFlipState.userFold);
    if (_calculation == null && !start(globalPos)) {
      return;
    }
    _applyPagePosition(
      convertViewportPointToPage(
        globalPos,
        _layout.bounds,
        direction: _direction!,
      ),
    );
  }

  StPageFlipAnimationPlan? flip(Offset globalPos) {
    if (_calculation != null) {
      _shadow = null;
    }
    if (!start(globalPos)) {
      return null;
    }

    final rect = _layout.bounds;
    _setState(StPageFlipState.flipping);

    final topMargins = rect.height / 10;
    final startEdgeInset = _direction == StPageFlipDirection.back
        ? topMargins * 0.22
        : topMargins;
    final startPoint = _resolveTurnAnimationPoint(
      useLeadingEdge: _direction == StPageFlipDirection.back,
      edgeInset: startEdgeInset,
      overflow: 0,
      yLocal: _corner == StPageFlipCorner.bottom
          ? rect.height - topMargins
          : topMargins,
    );
    final endPoint = _resolveTurnAnimationPoint(
      useLeadingEdge: _direction == StPageFlipDirection.forward,
      edgeInset: 0,
      overflow: topMargins * 0.45,
      yLocal: (_corner == StPageFlipCorner.bottom ? rect.height : 0.0)
          .toDouble(),
    );
    _applyPagePosition(startPoint);

    return _animationPlan(
      startPoint,
      endPoint,
      isTurned: true,
      needReset: true,
    );
  }

  StPageFlipAnimationPlan? flipNext(
    StPageFlipCorner corner, {
    bool allowOutOfBoundsTap = true,
  }) {
    if (!allowOutOfBoundsTap &&
        !canFlipDirection(StPageFlipDirection.forward)) {
      return null;
    }
    return flip(
      Offset(
        _layout.bounds.left + (_layout.bounds.pageWidth * 2) - 10,
        _layout.bounds.top +
            (corner == StPageFlipCorner.top ? 1 : _layout.bounds.height - 2),
      ),
    );
  }

  StPageFlipAnimationPlan? flipPrev(
    StPageFlipCorner corner, {
    bool allowOutOfBoundsTap = true,
  }) {
    if (!allowOutOfBoundsTap && !canFlipDirection(StPageFlipDirection.back)) {
      return null;
    }
    return flip(
      Offset(
        _layout.bounds.left + 10,
        _layout.bounds.top +
            (corner == StPageFlipCorner.top ? 1 : _layout.bounds.height - 2),
      ),
    );
  }

  StPageFlipAnimationPlan? stopMove() {
    if (_calculation == null) {
      return null;
    }

    final pos = _calculation!.getPosition();
    final y = (_corner == StPageFlipCorner.bottom ? _layout.bounds.height : 0.0)
        .toDouble();
    if (_direction == StPageFlipDirection.back) {
      return pos.dx <= -_layout.bounds.pageWidth
          ? _animationPlan(
              pos,
              Offset(-_layout.bounds.pageWidth, y),
              isTurned: true,
              needReset: true,
            )
          : _animationPlan(
              pos,
              Offset.zero.translate(0, y),
              isTurned: false,
              needReset: true,
            );
    }
    return pos.dx <= 0
        ? _animationPlan(
            pos,
            Offset(-_layout.bounds.pageWidth, y),
            isTurned: true,
            needReset: true,
          )
        : _animationPlan(
            pos,
            Offset(_layout.bounds.pageWidth, y),
            isTurned: false,
            needReset: true,
          );
  }

  StPageFlipAnimationPlan? showCorner(Offset globalPos) {
    if (!_checkState(StPageFlipState.read, StPageFlipState.foldCorner)) {
      return null;
    }

    final rect = _layout.bounds;
    if (isPointOnCorners(globalPos)) {
      if (_calculation == null) {
        if (!start(globalPos)) {
          return null;
        }

        _setState(StPageFlipState.foldCorner);
        _applyPagePosition(Offset(rect.pageWidth - 1, 1));

        const fixedCornerSize = 50.0;
        final yStart = _corner == StPageFlipCorner.bottom
            ? rect.height - 1
            : 1.0;
        final yDest = _corner == StPageFlipCorner.bottom
            ? rect.height - fixedCornerSize
            : fixedCornerSize;
        return _animationPlan(
          Offset(rect.pageWidth - 1, yStart),
          Offset(rect.pageWidth - fixedCornerSize, yDest),
          isTurned: false,
          needReset: false,
        );
      }

      _applyPagePosition(
        convertViewportPointToPage(
          globalPos,
          _layout.bounds,
          direction: _direction!,
        ),
      );
      return null;
    }

    _setState(StPageFlipState.read);
    if (_calculation == null) {
      return null;
    }
    return stopMove();
  }

  void applyAnimationFrame(
    Offset localPagePoint, {
    ReverseFlipPose? reversePose,
    Offset? renderLocalPagePoint,
  }) {
    _applyPagePosition(
      localPagePoint,
      reversePose: reversePose,
      renderLocalPagePoint: renderLocalPagePoint,
    );
  }

  void completeAnimation(StPageFlipAnimationPlan plan) {
    if (plan.isTurned && _direction != null) {
      if (_direction == StPageFlipDirection.back) {
        _showPrev();
      } else {
        _showNext();
      }
    }

    if (plan.needReset) {
      _shadow = null;
      _setState(StPageFlipState.read);
      _resetTransientState();
    }
  }

  void cancelInteraction() {
    _shadow = null;
    _setState(StPageFlipState.read);
    _resetTransientState();
  }

  bool isPointOnCorners(Offset globalPos) {
    final rect = _layout.bounds;
    final operatingDistance =
        distanceBetweenPoints(
          Offset.zero,
          Offset(rect.pageWidth, rect.height),
        ) /
        5;
    final bookPos = convertViewportPointToBook(globalPos, rect);
    return bookPos.dx > 0 &&
        bookPos.dy > 0 &&
        bookPos.dx < rect.width &&
        bookPos.dy < rect.height &&
        (bookPos.dx < operatingDistance ||
            bookPos.dx > rect.width - operatingDistance) &&
        (bookPos.dy < operatingDistance ||
            bookPos.dy > rect.height - operatingDistance);
  }

  StPageFlipDirection _directionByPoint(Offset touchPos) {
    final rect = _layout.bounds;
    if (_layout.orientation == StPageFlipOrientation.portrait) {
      if (touchPos.dx - rect.pageWidth <= rect.width / 5) {
        return StPageFlipDirection.back;
      }
    } else if (touchPos.dx < rect.width / 2) {
      return StPageFlipDirection.back;
    }
    return StPageFlipDirection.forward;
  }

  bool _checkState(StPageFlipState a, StPageFlipState b) {
    return _state == a || _state == b;
  }

  void _applyPagePosition(
    Offset localPagePoint, {
    ReverseFlipPose? reversePose,
    Offset? renderLocalPagePoint,
  }) {
    if (_calculation == null) {
      return;
    }
    final calculation = _calculation!;
    final direction = _direction;
    final corner = _corner;
    if (direction == null || corner == null) {
      return;
    }
    if (calculation.calc(localPagePoint)) {
      final effectiveLocalPagePoint = renderLocalPagePoint ?? localPagePoint;
      _renderFrame = switch (direction) {
        StPageFlipDirection.forward => _buildForwardRenderFrame(
          calculation: calculation,
          localPagePoint: effectiveLocalPagePoint,
        ),
        StPageFlipDirection.back => _buildBackwardRenderFrame(
          calculation: calculation,
          localPagePoint: effectiveLocalPagePoint,
        ),
      };
      _shadow = _renderFrame?.shadow;
    }
  }

  Offset _resolveTurnAnimationPoint({
    required bool useLeadingEdge,
    required double edgeInset,
    required double overflow,
    required double yLocal,
  }) {
    final rect = _layout.bounds;
    double viewportX;
    if (useLeadingEdge) {
      final leadingX = _layout.orientation == StPageFlipOrientation.portrait
          ? rect.left + rect.pageWidth
          : rect.left;
      viewportX = leadingX + edgeInset - overflow;
    } else {
      viewportX = rect.left + rect.width - edgeInset + overflow;
    }
    final viewportY = rect.top + yLocal;
    return convertViewportPointToPage(
      Offset(viewportX, viewportY),
      rect,
      direction: _direction!,
    );
  }

  StPageFlipShadowData _buildShadowData(
    Offset position,
    double angle,
    double progress,
    StPageFlipDirection direction,
  ) {
    final width = (((_layout.bounds.pageWidth * 3) / 4) * progress) / 100;
    final opacity = (((100 - progress) * (100 * maxShadowOpacity)) / 100 / 100)
        .clamp(0.0, 1.0)
        .toDouble();
    return StPageFlipShadowData(
      position: position,
      angle: angle,
      width: width,
      opacity: opacity,
      direction: direction,
      progress: progress * 2,
    );
  }

  StPageFlipAnimationPlan _animationPlan(
    Offset start,
    Offset end, {
    required bool isTurned,
    required bool needReset,
  }) {
    final frames = _buildAnimationFrames(start, end, isTurned: isTurned);
    final durationMs = _animationDuration(frames.length);
    final direction = _direction!;
    final corner = _corner!;

    return StPageFlipAnimationPlan(
      frames: frames,
      duration: Duration(milliseconds: durationMs.round()),
      isTurned: isTurned,
      needReset: needReset,
      direction: direction,
      corner: corner,
      reversePoses: null,
    );
  }

  List<Offset> _buildAnimationFrames(
    Offset start,
    Offset end, {
    required bool isTurned,
  }) {
    // 点列插值：前翻与回翻共用同一组 Offset 帧序列。
    // 回翻主线由 render_frame.dart 中的 backwardLeafFrame / replay timeline
    // 统一解释，动画计划不再携带额外 reversePoses 语义。
    return interpolatePoints(start, end);
  }

  double _animationDuration(int frameCount) {
    if (frameCount >= 1000) {
      return flippingTimeMs.toDouble();
    }
    return (frameCount / 1000) * flippingTimeMs;
  }

  void _showNext() {
    final spreadCount = _spreadModel.spreadCountFor(_layout.orientation);
    if (_currentSpreadIndex < spreadCount - 1) {
      _currentSpreadIndex += 1;
      _currentPageIndex = _spreadModel
          .visibleSpreadForIndex(_currentSpreadIndex, _layout.orientation)
          .currentPageIndex;
    }
  }

  void _showPrev() {
    if (_currentSpreadIndex > 0) {
      _currentSpreadIndex -= 1;
      _currentPageIndex = _spreadModel
          .visibleSpreadForIndex(_currentSpreadIndex, _layout.orientation)
          .currentPageIndex;
    }
  }

  void _setState(StPageFlipState nextState) {
    _state = nextState;
  }

  void _resetTransientState() {
    _calculation = null;
    _direction = null;
    _corner = null;
    _shadow = null;
    _renderFrame = null;
  }

  bool _sameLayout(StPageFlipLayout a, StPageFlipLayout b) {
    final aBounds = a.bounds;
    final bBounds = b.bounds;
    return a.orientation == b.orientation &&
        aBounds.left == bBounds.left &&
        aBounds.top == bBounds.top &&
        aBounds.width == bBounds.width &&
        aBounds.height == bBounds.height &&
        aBounds.pageWidth == bBounds.pageWidth;
  }

  StPageFlipCalculation _createCalculation({
    required StPageFlipDirection direction,
    required StPageFlipCorner corner,
  }) {
    return StPageFlipCalculation(
      direction: direction,
      corner: corner,
      pageWidth: _layout.bounds.pageWidth,
      pageHeight: _layout.bounds.height,
    );
  }

  StPageFlipRenderFrame _buildForwardRenderFrame({
    required StPageFlipCalculation calculation,
    required Offset localPagePoint,
  }) {
    final corner = _corner!;
    final progress = (calculation.getFlippingProgress() / 100)
        .clamp(0.0, 1.0)
        .toDouble();
    final pageSize = Size(_layout.bounds.pageWidth, _layout.bounds.height);
    return buildForwardRenderFrame(
      ForwardRenderFrameData(
        localPagePoint: localPagePoint,
        progress: progress,
        corner: corner,
        pageSize: pageSize,
        flippingClipArea: calculation.getFlippingClipArea(),
        bottomClipArea: calculation.getBottomClipArea(),
        flippingAnchor: calculation.getActiveCorner(),
        bottomAnchor: calculation.getBottomPagePosition(),
        angle: calculation.getAngle(),
        shadow: _buildShadowData(
          calculation.getShadowStartPoint(),
          calculation.getShadowAngle(),
          calculation.getFlippingProgress(),
          StPageFlipDirection.forward,
        ),
      ),
    );
  }

  StPageFlipRenderFrame _buildBackwardRenderFrame({
    required StPageFlipCalculation calculation,
    required Offset localPagePoint,
  }) {
    final corner = _corner!;
    final progress = (calculation.getFlippingProgress() / 100)
        .clamp(0.0, 1.0)
        .toDouble();
    final pageSize = Size(_layout.bounds.pageWidth, _layout.bounds.height);
    final canonicalFoldGeometry = calculation.getCanonicalFoldGeometry();
    return buildBackwardDynamicRenderFrame(
      BackwardRenderFrameData(
        localPagePoint: localPagePoint,
        progress: progress,
        orientation: _layout.orientation,
        corner: corner,
        pageSize: pageSize,
        flippingClipArea: calculation.getFlippingClipArea(),
        bottomClipArea: calculation.getBottomClipArea(),
        flippingAnchor: calculation.getActiveCorner(),
        bottomAnchor: calculation.getBottomPagePosition(),
        angle: calculation.getAngle(),
        foldLine: canonicalFoldGeometry?.foldLine,
        freeEdgeLine: canonicalFoldGeometry?.freeEdgeLine,
        shadow: _buildShadowData(
          calculation.getShadowStartPoint(),
          calculation.getShadowAngle(),
          calculation.getFlippingProgress(),
          StPageFlipDirection.back,
        ),
        maxShadowOpacity: maxShadowOpacity,
      ),
    );
  }
}
