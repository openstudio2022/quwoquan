import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/page_touch_state_v2.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class PageflipBookIsolatedAnimationFrame {
  const PageflipBookIsolatedAnimationFrame({
    required this.touchState,
    required this.progress,
  });

  final PageTouchStateV2 touchState;
  final double progress;
}

@immutable
class PageflipBookIsolatedAnimationPlan {
  const PageflipBookIsolatedAnimationPlan({
    required this.direction,
    required this.corner,
    required this.frames,
    required this.duration,
    required this.commitsTurn,
  });

  final PageflipBookIsolatedDirection direction;
  final PageflipBookIsolatedCorner corner;
  final List<PageflipBookIsolatedAnimationFrame> frames;
  final Duration duration;
  final bool commitsTurn;
}

PageflipBookIsolatedAnimationPlan buildPageflipBookIsolatedAnimationPlan({
  required PageTouchStateV2 fromTouchState,
  required Offset toWorkingPagePoint,
  required StPageFlipBoundsRect bounds,
  required bool commitsTurn,
}) {
  final direction = fromTouchState.direction;
  final corner = fromTouchState.corner;
  final safeFrom = _resolveProgress(
    fromTouchState.workingPagePoint,
    bounds.pageWidth,
  );
  final safeTo = _resolveProgress(toWorkingPagePoint, bounds.pageWidth);
  final delta = (safeTo - safeFrom).abs();
  final frameCount = math.max(10, (delta * 24).round() + 8);
  final frames = List<PageflipBookIsolatedAnimationFrame>.generate(frameCount, (
    index,
  ) {
    final t = frameCount == 1 ? 1.0 : index / (frameCount - 1);
    final eased = 1 - math.pow(1 - t, 3).toDouble();
    final workingPagePoint = Offset(
      fromTouchState.workingPagePoint.dx +
          (toWorkingPagePoint.dx - fromTouchState.workingPagePoint.dx) * eased,
      fromTouchState.workingPagePoint.dy +
          (toWorkingPagePoint.dy - fromTouchState.workingPagePoint.dy) * eased,
    );
    final touchState = PageTouchStateV2.fromWorkingPagePoint(
      workingPagePoint: workingPagePoint,
      bounds: bounds,
      direction: direction,
      corner: corner,
    );
    return PageflipBookIsolatedAnimationFrame(
      touchState: touchState,
      progress: _resolveProgress(workingPagePoint, bounds.pageWidth),
    );
  }, growable: false);
  final durationMs = (180 + delta * 160).round().clamp(180, 360);
  return PageflipBookIsolatedAnimationPlan(
    direction: direction,
    corner: corner,
    frames: frames,
    duration: Duration(milliseconds: durationMs),
    commitsTurn: commitsTurn,
  );
}

double _resolveProgress(Offset workingPagePoint, double pageWidth) {
  if (pageWidth <= 0) {
    return 0;
  }
  return (((workingPagePoint.dx - pageWidth) / (2 * pageWidth)) * 100)
          .abs()
          .clamp(0.0, 100.0)
          .toDouble() /
      100;
}
