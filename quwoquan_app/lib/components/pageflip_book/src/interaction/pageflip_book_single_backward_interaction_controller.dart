import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:quwoquan_app/components/pageflip_book/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book/src/pose/pageflip_book_single_backward_pose.dart';
import 'package:quwoquan_app/components/pageflip_book/src/pose/pageflip_book_single_backward_pose_solver.dart';

@immutable
class PageflipBookSingleBackwardInteractionState {
  const PageflipBookSingleBackwardInteractionState({
    required this.pageSize,
    required this.corner,
    required this.startPoint,
    required this.latestPoint,
    required this.pose,
  });

  final Size pageSize;
  final PageflipBookCorner corner;
  final Offset startPoint;
  final Offset latestPoint;
  final PageflipBookSingleBackwardPose pose;
}

@immutable
class PageflipBookSingleBackwardInteractionAnimationPlan {
  const PageflipBookSingleBackwardInteractionAnimationPlan({
    required this.frames,
    required this.duration,
    required this.isTurned,
    required this.corner,
  });

  final List<Offset> frames;
  final Duration duration;
  final bool isTurned;
  final PageflipBookCorner corner;
}

@immutable
class PageflipBookSingleBackwardInteractionEndResult {
  const PageflipBookSingleBackwardInteractionEndResult({
    required this.shouldCommit,
    required this.pose,
    required this.animationPlan,
  });

  final bool shouldCommit;
  final PageflipBookSingleBackwardPose pose;
  final PageflipBookSingleBackwardInteractionAnimationPlan animationPlan;
}

class PageflipBookSingleBackwardInteractionController {
  PageflipBookSingleBackwardInteractionController({
    PageflipBookSingleBackwardPoseSolver? solver,
    this.flippingTimeMs = 260,
  }) : _solver = solver ?? const PageflipBookSingleBackwardPoseSolver();

  final PageflipBookSingleBackwardPoseSolver _solver;
  final int flippingTimeMs;

  PageflipBookSingleBackwardInteractionState? _state;

  PageflipBookSingleBackwardInteractionState? get state => _state;

  bool get isActive => _state != null;

  bool start({
    required Offset localPoint,
    required Size pageSize,
    PageflipBookCorner? corner,
  }) {
    final resolvedCorner =
        corner ??
        (localPoint.dy <= pageSize.height / 2
            ? PageflipBookCorner.top
            : PageflipBookCorner.bottom);
    final pose = _solver.solve(
      pageSize: pageSize,
      localPoint: localPoint,
      startPoint: localPoint,
      corner: resolvedCorner,
    );
    _state = PageflipBookSingleBackwardInteractionState(
      pageSize: pageSize,
      corner: resolvedCorner,
      startPoint: pose.startPoint,
      latestPoint: pose.dragPoint,
      pose: pose,
    );
    return true;
  }

  PageflipBookSingleBackwardInteractionState? update(Offset localPoint) {
    final currentState = _state;
    if (currentState == null) {
      return null;
    }
    return _syncPoint(
      pageSize: currentState.pageSize,
      corner: currentState.corner,
      startPoint: currentState.startPoint,
      localPoint: localPoint,
    );
  }

  PageflipBookSingleBackwardInteractionState? applyAnimationPoint(
    Offset localPoint,
  ) {
    return update(localPoint);
  }

  PageflipBookSingleBackwardInteractionEndResult? end(Velocity velocity) {
    final currentState = _state;
    if (currentState == null) {
      return null;
    }
    final pose = currentState.pose;
    final pageWidth = math.max(currentState.pageSize.width, 1.0);
    final dragDistanceRatio =
        ((currentState.latestPoint.dx - currentState.startPoint.dx) / pageWidth)
            .clamp(0.0, 1.0)
            .toDouble();
    final directionalVelocity = velocity.pixelsPerSecond.dx;
    final crossedMidpoint = pose.commitProgress >= 0.52;
    final deliberateDrag =
        pose.commitProgress >= 0.24 && dragDistanceRatio >= 0.16;
    final decisiveVelocity = directionalVelocity >= 320;
    final assistedSnap =
        pose.commitProgress >= 0.16 && directionalVelocity >= 140;
    final shouldCommit =
        crossedMidpoint || deliberateDrag || decisiveVelocity || assistedSnap;
    final targetPoint = Offset(
      shouldCommit ? currentState.pageSize.width : 0.0,
      currentState.latestPoint.dy
          .clamp(0.0, currentState.pageSize.height)
          .toDouble(),
    );
    final frames = _interpolatePoints(currentState.latestPoint, targetPoint);
    return PageflipBookSingleBackwardInteractionEndResult(
      shouldCommit: shouldCommit,
      pose: pose,
      animationPlan: PageflipBookSingleBackwardInteractionAnimationPlan(
        frames: frames,
        duration: _resolveAnimationDuration(frames.length),
        isTurned: shouldCommit,
        corner: currentState.corner,
      ),
    );
  }

  void cancel() {
    _state = null;
  }

  PageflipBookSingleBackwardInteractionState _syncPoint({
    required Size pageSize,
    required PageflipBookCorner corner,
    required Offset startPoint,
    required Offset localPoint,
  }) {
    final pose = _solver.solve(
      pageSize: pageSize,
      localPoint: localPoint,
      startPoint: startPoint,
      corner: corner,
    );
    final nextState = PageflipBookSingleBackwardInteractionState(
      pageSize: pageSize,
      corner: corner,
      startPoint: pose.startPoint,
      latestPoint: pose.dragPoint,
      pose: pose,
    );
    _state = nextState;
    return nextState;
  }

  List<Offset> _interpolatePoints(Offset start, Offset end) {
    final deltaX = (end.dx - start.dx).abs();
    final deltaY = (end.dy - start.dy).abs();
    final length = math.max(deltaX, deltaY).round().clamp(1, 100000);
    final points = <Offset>[start];
    for (var index = 1; index <= length; index += 1) {
      final t = index / length;
      points.add(
        Offset(
          lerpDouble(start.dx, end.dx, t) ?? end.dx,
          lerpDouble(start.dy, end.dy, t) ?? end.dy,
        ),
      );
    }
    return List<Offset>.unmodifiable(points);
  }

  Duration _resolveAnimationDuration(int frameCount) {
    final clampedMs = ((frameCount / 1000) * flippingTimeMs)
        .clamp(180, flippingTimeMs)
        .round();
    return Duration(milliseconds: clampedMs);
  }
}
