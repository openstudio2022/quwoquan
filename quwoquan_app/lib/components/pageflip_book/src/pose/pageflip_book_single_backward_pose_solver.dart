import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/animation.dart';
import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book/src/pose/pageflip_book_single_backward_pose.dart';

@immutable
class PageflipBookSingleBackwardPoseSolver {
  const PageflipBookSingleBackwardPoseSolver();

  PageflipBookSingleBackwardPose solve({
    required Size pageSize,
    required Offset localPoint,
    required PageflipBookCorner corner,
    Offset? startPoint,
  }) {
    final safePageWidth = math.max(pageSize.width, 1.0).toDouble();
    final safePageHeight = math.max(pageSize.height, 1.0).toDouble();
    final clampedPoint = Offset(
      localPoint.dx.clamp(0.0, safePageWidth).toDouble(),
      localPoint.dy.clamp(0.0, safePageHeight).toDouble(),
    );
    final clampedStartPoint = Offset(
      (startPoint?.dx ?? clampedPoint.dx).clamp(0.0, safePageWidth).toDouble(),
      (startPoint?.dy ?? clampedPoint.dy).clamp(0.0, safePageHeight).toDouble(),
    );
    final startEdgeX = math.min(clampedStartPoint.dx, safePageWidth * 0.08);
    final dragProgress =
        ((clampedPoint.dx - startEdgeX) /
                math.max(1.0, safePageWidth - startEdgeX))
            .clamp(0.0, 1.0)
            .toDouble();
    final coveredWidth = (clampedPoint.dx / safePageWidth).clamp(0.0, 1.0);
    final emergenceProgress = Curves.easeOutCubic.transform(
      (coveredWidth / 0.16).clamp(0.0, 1.0),
    );
    final unrollProgress = Curves.easeInOutCubic.transform(
      ((coveredWidth - 0.08) / 0.64).clamp(0.0, 1.0),
    );
    final settleProgress = Curves.easeOutCubic.transform(
      ((coveredWidth - 0.82) / 0.18).clamp(0.0, 1.0),
    );
    final cornerProximity = _resolveCornerProximity(
      pageHeight: safePageHeight,
      localPoint: clampedPoint,
      startPoint: clampedStartPoint,
      corner: corner,
    );
    final verticalTravel = ((clampedPoint.dy - clampedStartPoint.dy).abs() /
            safePageHeight)
        .clamp(0.0, 1.0)
        .toDouble();
    final emergedCurlWidth =
        (lerpDouble(0.045, 0.13 + cornerProximity * 0.02, emergenceProgress) ??
                0.07)
            .clamp(0.045, 0.18)
            .toDouble();
    final flattenProgress = Curves.easeInOutCubic.transform(
      ((coveredWidth - 0.18) / 0.34).clamp(0.0, 1.0),
    );
    final unrolledCurlWidth =
        (lerpDouble(
                  emergedCurlWidth,
                  0.07 + (1 - cornerProximity) * 0.015,
                  flattenProgress,
                ) ??
                emergedCurlWidth)
            .clamp(0.035, 0.16)
            .toDouble();
    final curlWidth =
        (lerpDouble(unrolledCurlWidth, 0.0, settleProgress) ??
                unrolledCurlWidth)
            .clamp(0.0, 0.18)
            .toDouble();
    final laidDownTarget = math.max(0.0, coveredWidth - curlWidth * 0.58);
    final laidDownWidth =
        (lerpDouble(
                  0.0,
                  laidDownTarget,
                  Curves.easeOutCubic.transform(
                    ((coveredWidth - 0.06) / 0.82).clamp(0.0, 1.0),
                  ),
                ) ??
                laidDownTarget)
            .clamp(0.0, coveredWidth)
            .toDouble();
    final rectoRevealWidth = math.min(
      curlWidth * (0.34 + unrollProgress * 0.28),
      curlWidth * 0.72,
    );
    final curlPivotNormalized = (laidDownWidth + curlWidth * 0.5)
        .clamp(laidDownWidth, coveredWidth)
        .toDouble();
    final edgeLiftBase =
        ((lerpDouble(0.16, 0.34, cornerProximity) ?? 0.2) *
                (corner == PageflipBookCorner.top ? 1.04 : 0.96))
            .clamp(0.14, 0.34)
            .toDouble();
    final edgeLift =
        (edgeLiftBase *
                (0.74 +
                    emergenceProgress * 0.18 +
                    verticalTravel * 0.14 +
                    unrollProgress * 0.12) *
                (1 - settleProgress * 0.62))
            .clamp(0.08, 0.42)
            .toDouble();
    final liftDirection = corner == PageflipBookCorner.top ? -1.0 : 1.0;
    final shadowAxisNormalized = (laidDownWidth + curlWidth * 0.78)
        .clamp(0.0, coveredWidth)
        .toDouble();
    final commitProgress = (coveredWidth * 0.64 +
            laidDownWidth * 0.22 +
            unrollProgress * 0.14)
        .clamp(0.0, 1.0)
        .toDouble();
    final phase = settleProgress > 0.001
        ? PageflipBookSingleBackwardPosePhase.settle
        : unrollProgress > 0.001
        ? PageflipBookSingleBackwardPosePhase.unroll
        : PageflipBookSingleBackwardPosePhase.emerge;

    return PageflipBookSingleBackwardPose(
      phase: phase,
      dragPoint: clampedPoint,
      startPoint: clampedStartPoint,
      corner: corner,
      dragProgress: dragProgress.toDouble(),
      emergenceProgress: emergenceProgress,
      unrollProgress: unrollProgress,
      settleProgress: settleProgress,
      coveredWidthNormalized: coveredWidth,
      laidDownWidthNormalized: laidDownWidth,
      curlWidthNormalized: curlWidth,
      rectoRevealWidthNormalized: rectoRevealWidth,
      curlPivotNormalized: curlPivotNormalized,
      edgeLift: edgeLift,
      liftDirection: liftDirection,
      shadowAxisNormalized: shadowAxisNormalized,
      commitProgress: commitProgress,
    );
  }

  double _resolveCornerProximity({
    required double pageHeight,
    required Offset localPoint,
    required Offset startPoint,
    required PageflipBookCorner corner,
  }) {
    double proximityFor(Offset point) {
      final yProgress = (point.dy / pageHeight).clamp(0.0, 1.0).toDouble();
      return corner == PageflipBookCorner.top ? 1 - yProgress : yProgress;
    }

    final currentProximity = proximityFor(localPoint);
    final startProximity = proximityFor(startPoint);
    return (lerpDouble(startProximity, currentProximity, 0.55) ??
            currentProximity)
        .clamp(0.35, 1.0)
        .toDouble();
  }
}
