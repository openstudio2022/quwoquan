import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_mode.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_role_resolver.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_state.dart';
import 'package:quwoquan_app/components/pageflip/src/geometry/pageflip_forward_calculation.dart';
import 'package:quwoquan_app/components/pageflip/src/geometry/pageflip_reverse_calculation.dart';
import 'package:quwoquan_app/components/pageflip/src/layout/pageflip_layout_resolver.dart';
import 'package:quwoquan_app/components/pageflip/src/render/pageflip_render_frame.dart';
import 'package:quwoquan_app/components/pageflip/src/scene/pageflip_scene.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart' as canonical;
import 'package:quwoquan_app/ui/content/pageflip/release_policy.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class PageflipTurnPlan {
  const PageflipTurnPlan({
    required this.commitsTurn,
    required this.direction,
    required this.targetPageIndex,
    required this.velocity,
  });

  final bool commitsTurn;
  final PageflipDirection direction;
  final int targetPageIndex;
  final Velocity velocity;
}

class PageflipEngine {
  PageflipEngine({
    required int pageCount,
    int initialPage = 0,
    this.mode = PageflipMode.single,
    PageflipLayoutResolver? layoutResolver,
    PageflipRoleResolver? roleResolver,
  })  : _pageCount = pageCount,
        _currentPageIndex = initialPage,
        _layoutResolver = layoutResolver ?? const PageflipLayoutResolver(),
        _roleResolver = roleResolver ?? const PageflipSinglePageRoleResolver() {
    _state = PageflipState(
      mode: mode,
      currentPageIndex: _currentPageIndex,
    );
  }

  final int _pageCount;
  final PageflipMode mode;
  final PageflipLayoutResolver _layoutResolver;
  final PageflipRoleResolver _roleResolver;

  Size? _stageSize;
  Size? _pageSize;
  late PageflipState _state;
  int _currentPageIndex;
  PageflipDirection? _direction;
  PageflipCorner? _corner;
  Offset? _localPagePoint;
  Offset? _dragStartPoint;
  DateTime? _dragStartedAt;

  PageflipState get state => _state;
  int get currentPageIndex => _currentPageIndex;

  void updateViewport({
    required Size stageSize,
    required Size pageSize,
  }) {
    _stageSize = stageSize;
    _pageSize = pageSize;
    _syncState();
  }

  bool start(Offset stagePoint) {
    final layout = _resolveLayout();
    if (_pageSize == null) {
      return false;
    }
    final direction = stagePoint.dx >= (layout.bounds.left + layout.bounds.width / 2)
        ? PageflipDirection.forward
        : PageflipDirection.back;
    final corner = stagePoint.dy >= (layout.bounds.top + layout.bounds.height / 2)
        ? PageflipCorner.bottom
        : PageflipCorner.top;
    _direction = direction;
    _corner = corner;
    _localPagePoint = layout.convertViewportPointToPage(
      stagePoint,
      direction: direction == PageflipDirection.forward
          ? StPageFlipDirection.forward
          : StPageFlipDirection.back,
    );
    _syncState(isInteractive: true);
    _dragStartPoint = stagePoint;
    _dragStartedAt = DateTime.now();
    return true;
  }

  void fold(Offset stagePoint) {
    final layout = _resolveLayout();
    final direction = _direction ?? PageflipDirection.forward;
    _localPagePoint = layout.convertViewportPointToPage(
      stagePoint,
      direction: direction == PageflipDirection.forward
          ? StPageFlipDirection.forward
          : StPageFlipDirection.back,
    );
    _dragStartedAt ??= DateTime.now();
    _syncState(isInteractive: true);
  }

  PageflipTurnPlan stopMove(Velocity velocity) {
    final direction = _direction ?? PageflipDirection.forward;
    final layout = _resolveLayout();
    final progress = _state.renderFrame?.canonicalFrame.progress ?? 0.0;
    final release = resolvePageflipReleaseDecision(
      isForwardDirection: direction == PageflipDirection.forward,
      progress: progress,
      pageWidth: _pageSize?.width ?? layout.bounds.pageWidth,
      velocityDx: velocity.pixelsPerSecond.dx,
      dragStart: _dragStartPoint,
      dragLatest: _localPagePoint,
      dragStartedAt: _dragStartedAt,
      usesMirroredBackwardReplay:
          direction == PageflipDirection.back &&
          layout.orientation == StPageFlipOrientation.portrait,
    );
    final commitsTurn = release.commitsTurn;
    final targetPageIndex = commitsTurn
        ? (direction == PageflipDirection.forward
              ? (_currentPageIndex + 1).clamp(0, _pageCount - 1).toInt()
              : (_currentPageIndex - 1).clamp(0, _pageCount - 1).toInt())
        : _currentPageIndex;
    if (commitsTurn) {
      _currentPageIndex = targetPageIndex;
    }
    _direction = null;
    _corner = null;
    _localPagePoint = null;
    _dragStartPoint = null;
    _dragStartedAt = null;
    _syncState(isInteractive: false, isSettling: !commitsTurn);
    return PageflipTurnPlan(
      commitsTurn: commitsTurn,
      direction: direction,
      targetPageIndex: targetPageIndex,
      velocity: velocity,
    );
  }

  void settleToIndex(int pageIndex) {
    _currentPageIndex = pageIndex.clamp(0, _pageCount - 1).toInt();
    _direction = null;
    _corner = null;
    _localPagePoint = null;
    _dragStartPoint = null;
    _dragStartedAt = null;
    _syncState(isInteractive: false, isSettling: false);
  }

  PageflipScene? buildScene(Size stageSize) {
    if (_pageSize == null) {
      return null;
    }
    final layout = _resolveLayout();
    final direction = _direction;
    final roleState = direction == null
        ? null
        : _roleResolver.resolve(
            mode: mode,
            direction: direction,
            currentPageIndex: _currentPageIndex,
            pageCount: _pageCount,
          );
    final renderFrame = roleState == null || _corner == null || _localPagePoint == null
        ? null
        : _buildRenderFrame(
            layout: layout,
            roleState: roleState,
            direction: direction!,
            corner: _corner!,
            localPagePoint: _localPagePoint!,
          );
    final state = _state.copyWith(
      mode: mode,
      currentPageIndex: _currentPageIndex,
      direction: direction,
      roleState: roleState,
      renderFrame: renderFrame,
      isInteractive: direction != null,
      isSettling: false,
    );
    _state = state;
    final pageRect = layout.resolvePageRect(
      isRightPage: mode == PageflipMode.spread ? true : true,
    );
    final scene = PageflipScene(
      stageSize: stageSize,
      pageRect: pageRect,
      pageSize: _pageSize!,
      layout: layout,
      state: state,
      renderFrame: renderFrame,
    );
    return scene;
  }

  PageflipLayout _resolveLayout() {
    final stageSize = _stageSize ?? const Size(1, 1);
    final pageSize = _pageSize ?? const Size(1, 1);
    return _layoutResolver.resolve(
      viewportSize: stageSize,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
      mode: mode,
    );
  }

  PageflipRenderFrame _buildRenderFrame({
    required PageflipLayout layout,
    required PageflipRoleState roleState,
    required PageflipDirection direction,
    required PageflipCorner corner,
    required Offset localPagePoint,
  }) {
    final pageSize = _pageSize ?? const Size(1, 1);
    if (direction == PageflipDirection.forward) {
      final angleBand = canonical.resolveForwardCurlAngleBand(
        localPagePoint: localPagePoint,
        pageSize: pageSize,
        corner: corner == PageflipCorner.top
            ? StPageFlipCorner.top
            : StPageFlipCorner.bottom,
      );
      final calc = PageflipForwardCalculation(
        corner: corner == PageflipCorner.top
            ? StPageFlipCorner.top
            : StPageFlipCorner.bottom,
        pageWidth: pageSize.width,
        pageHeight: pageSize.height,
      );
      calc.calc(localPagePoint);
      final canonicalFrame = canonical.StPageFlipRenderFrame(
        localPagePoint: localPagePoint,
        progress: calc.getProgress(),
        direction: StPageFlipDirection.forward,
        renderDirection: StPageFlipDirection.forward,
        corner: corner == PageflipCorner.top
            ? StPageFlipCorner.top
            : StPageFlipCorner.bottom,
        flippingClipArea: const <Offset>[],
        bottomClipArea: const <Offset>[],
        flippingAnchor: calc.getActiveCorner(),
        bottomAnchor: calc.getBottomPagePosition(),
        angle: calc.getAngle(),
        shadow: null,
        timeline: canonical.resolvePageCurlTimeline(
          direction: StPageFlipDirection.forward,
          renderDirection: StPageFlipDirection.forward,
          progress: calc.getProgress(),
          localPagePoint: localPagePoint,
          pageSize: pageSize,
          corner: corner == PageflipCorner.top
              ? StPageFlipCorner.top
              : StPageFlipCorner.bottom,
          angleBand: angleBand,
        ),
      );
      return PageflipRenderFrame(
        mode: mode,
        direction: PageflipDirection.forward,
        roleState: roleState,
        canonicalFrame: canonicalFrame,
      );
    }

    final calc = PageflipReverseCalculation(
      corner: corner == PageflipCorner.top
          ? StPageFlipCorner.top
          : StPageFlipCorner.bottom,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
    );
    calc.calc(localPagePoint);
    final angleBand = canonical.resolveForwardCurlAngleBand(
      localPagePoint: localPagePoint,
      pageSize: pageSize,
      corner: corner == PageflipCorner.top
          ? StPageFlipCorner.top
          : StPageFlipCorner.bottom,
    );
    final canonicalFrame = canonical.StPageFlipRenderFrame(
      localPagePoint: localPagePoint,
      progress: calc.getProgress(),
      direction: StPageFlipDirection.back,
      renderDirection: canonical.resolvePageFlipRenderDirection(
        direction: StPageFlipDirection.back,
        orientation: layout.orientation,
        reversePose: calc.pose,
      ),
      corner: corner == PageflipCorner.top
          ? StPageFlipCorner.top
          : StPageFlipCorner.bottom,
      flippingClipArea: const <Offset>[],
      bottomClipArea: const <Offset>[],
      flippingAnchor: calc.getActiveCorner(),
      bottomAnchor: calc.getBottomPagePosition(),
      angle: calc.getAngle(),
      shadow: null,
      timeline: canonical.resolvePageCurlTimeline(
        direction: StPageFlipDirection.back,
        renderDirection: canonical.resolvePageFlipRenderDirection(
          direction: StPageFlipDirection.back,
          orientation: layout.orientation,
          reversePose: calc.pose,
        ),
        progress: calc.getProgress(),
        localPagePoint: localPagePoint,
        pageSize: pageSize,
        corner: corner == PageflipCorner.top
            ? StPageFlipCorner.top
            : StPageFlipCorner.bottom,
        angleBand: angleBand,
        reversePose: calc.pose,
      ),
      reversePose: calc.pose,
      backwardLeafFrame: canonical.resolveArticlePageBackwardLeafFrame(
        direction: StPageFlipDirection.back,
        progress: calc.getProgress(),
        reversePose: calc.pose,
      ),
    );
    return PageflipRenderFrame(
      mode: mode,
      direction: PageflipDirection.back,
      roleState: roleState,
      canonicalFrame: canonicalFrame,
    );
  }

  void _syncState({bool? isInteractive, bool? isSettling}) {
    _state = _state.copyWith(
      mode: mode,
      currentPageIndex: _currentPageIndex,
      direction: _direction,
      roleState: _state.roleState,
      renderFrame: _state.renderFrame,
      isInteractive: isInteractive ?? _state.isInteractive,
      isSettling: isSettling ?? _state.isSettling,
    );
  }
}
