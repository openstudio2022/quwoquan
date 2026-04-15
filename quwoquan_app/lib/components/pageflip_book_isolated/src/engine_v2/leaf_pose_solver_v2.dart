import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/animation.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/fold_axis_state_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/leaf_pose_v2.dart';

LeafPoseV2 resolveLeafPoseV2({
  required FoldAxisStateV2 foldAxisState,
  required Size pageSize,
}) {
  final pageWidth = math.max(1.0, pageSize.width).toDouble();
  final pageHeight = math.max(1.0, pageSize.height).toDouble();
  final progress = foldAxisState.progress.clamp(0.0, 1.0).toDouble();
  final flatLimitX = foldAxisState.position.dx;
  final curlWidth = (pageWidth - flatLimitX)
      .clamp(0.0, pageWidth * 2)
      .toDouble();
  final curlRadius = curlWidth <= 0.5
      ? pageWidth
      : math.max(curlWidth / math.pi, pageWidth * 0.085).toDouble();
  final yNormalized =
      (foldAxisState.touchState.workingPagePoint.dy / pageHeight)
          .clamp(0.0, 1.0)
          .toDouble();
  final cornerInfluence =
      foldAxisState.touchState.corner == PageflipBookIsolatedCorner.bottom
      ? yNormalized
      : (1 - yNormalized);
  final easedProgress = Curves.easeOutCubic.transform(progress);
  final diagonalExtent =
      lerpDouble(pageWidth * 0.02, pageWidth * 0.12, easedProgress) ??
      pageWidth * 0.08;
  final liftAmount =
      pageHeight *
      (0.05 + 0.08 * cornerInfluence) *
      math.sin(easedProgress * math.pi / 2);
  final heightLiftBias = lerpDouble(0.28, 0.44, easedProgress) ?? 0.36;
  return LeafPoseV2(
    pageSize: pageSize,
    touchState: foldAxisState.touchState,
    foldAxisState: foldAxisState,
    flatLimitX: flatLimitX,
    diagonalExtent: diagonalExtent,
    curlRadius: curlRadius,
    maxTheta: math.pi,
    liftAmount: liftAmount,
    heightLiftBias: heightLiftBias,
  );
}
