import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/animation.dart';
import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/reverse_curl_calculation.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class StPageFlipTimeline {
  const StPageFlipTimeline({
    required this.mirrored,
    required this.basePivot,
    required this.diagonalExtent,
    required this.leadingRadius,
    required this.trailingRadius,
    required this.sheetShift,
    required this.perspective,
    required this.rollProgress,
    required this.cylinderProgress,
    required this.unfoldProgress,
    required this.heightLiftBias,
    required this.cylinderRadiusNormalized,
    required this.unrollWidthNormalized,
    required this.bottomGapNormalized,
  });

  final bool mirrored;
  final double basePivot;
  final double diagonalExtent;
  final double leadingRadius;
  final double trailingRadius;
  final double sheetShift;
  final double perspective;
  final double rollProgress;
  final double cylinderProgress;
  final double unfoldProgress;
  final double heightLiftBias;
  final double cylinderRadiusNormalized;
  final double unrollWidthNormalized;
  final double bottomGapNormalized;
}

@immutable
class StPageFlipRenderFrame {
  const StPageFlipRenderFrame({
    required this.localPagePoint,
    required this.progress,
    required this.direction,
    required this.renderDirection,
    required this.corner,
    required this.flippingClipArea,
    required this.bottomClipArea,
    required this.flippingAnchor,
    required this.bottomAnchor,
    required this.angle,
    required this.shadow,
    required this.timeline,
    this.reversePose,
  });

  final ui.Offset localPagePoint;
  final double progress;
  final StPageFlipDirection direction;
  final StPageFlipDirection renderDirection;
  final StPageFlipCorner corner;
  final List<ui.Offset> flippingClipArea;
  final List<ui.Offset> bottomClipArea;
  final ui.Offset flippingAnchor;
  final ui.Offset bottomAnchor;
  final double angle;
  final StPageFlipShadowData? shadow;
  final StPageFlipTimeline timeline;
  final ReverseFlipPose? reversePose;

  bool get usesThreeStageBackflow =>
      direction == StPageFlipDirection.back &&
      renderDirection == StPageFlipDirection.forward &&
      reversePose != null;
}

StPageFlipDirection resolvePageFlipRenderDirection({
  required StPageFlipDirection direction,
  required StPageFlipOrientation orientation,
  ReverseFlipPose? reversePose,
}) {
  if (direction == StPageFlipDirection.back &&
      orientation == StPageFlipOrientation.portrait &&
      reversePose != null) {
    return StPageFlipDirection.forward;
  }
  return direction;
}

StPageFlipTimeline resolvePageCurlTimeline({
  required StPageFlipDirection direction,
  required StPageFlipDirection renderDirection,
  required double progress,
  required ui.Offset localPagePoint,
  required ui.Size pageSize,
  required StPageFlipCorner corner,
  ReverseFlipPose? reversePose,
}) {
  final settledProgress = progress.clamp(0.0, 1.0).toDouble();
  if (direction == StPageFlipDirection.back &&
      renderDirection == StPageFlipDirection.forward &&
      reversePose != null) {
    return _resolveThreeStageBackwardTimeline(
      reversePose: reversePose,
      pageSize: pageSize,
    );
  }
  if (direction == StPageFlipDirection.back) {
    return _resolveMirroredForwardTimeline(
      progress: settledProgress,
      localPagePoint: localPagePoint,
      pageSize: pageSize,
    );
  }
  return _resolveForwardTimeline(
    progress: settledProgress,
    localPagePoint: localPagePoint,
    pageSize: pageSize,
  );
}

StPageFlipTimeline _resolveForwardTimeline({
  required double progress,
  required ui.Offset localPagePoint,
  required ui.Size pageSize,
}) {
  final localDragX = localPagePoint.dx.clamp(0.0, pageSize.width).toDouble();
  final curlWidth = math.max(1.0, pageSize.width - localDragX);
  final diagonalExtent =
      ui.lerpDouble(
        pageSize.width * 0.06,
        pageSize.width * 0.32,
        Curves.easeOutCubic.transform(progress),
      ) ??
      (pageSize.width * 0.18);
  final radiusBase =
      ui.lerpDouble(
        math.max(curlWidth / math.pi, pageSize.width * 0.085),
        pageSize.width * 0.058,
        Curves.easeInOut.transform(progress),
      ) ??
      (pageSize.width * 0.085);
  final sheetShift =
      -(ui.lerpDouble(
            0.0,
            pageSize.width * 0.18,
            Curves.easeOut.transform(progress),
          ) ??
          0.0);
  return StPageFlipTimeline(
    mirrored: false,
    basePivot: localDragX,
    diagonalExtent: diagonalExtent,
    leadingRadius: radiusBase * 1.12,
    trailingRadius: radiusBase * 0.72,
    sheetShift: sheetShift,
    perspective: pageSize.width * 2.7,
    rollProgress: progress,
    cylinderProgress: 0.0,
    unfoldProgress: 0.0,
    heightLiftBias: 0.22,
    cylinderRadiusNormalized: (radiusBase / pageSize.width)
        .clamp(0.0, 1.0)
        .toDouble(),
    unrollWidthNormalized: 0.0,
    bottomGapNormalized: ((pageSize.width - localDragX) / pageSize.width)
        .clamp(0.0, 1.0)
        .toDouble(),
  );
}

StPageFlipTimeline _resolveMirroredForwardTimeline({
  required double progress,
  required ui.Offset localPagePoint,
  required ui.Size pageSize,
}) {
  final mirroredLocalPoint = ui.Offset(
    pageSize.width - localPagePoint.dx.clamp(0.0, pageSize.width),
    localPagePoint.dy,
  );
  final timeline = _resolveForwardTimeline(
    progress: progress,
    localPagePoint: mirroredLocalPoint,
    pageSize: pageSize,
  );
  return StPageFlipTimeline(
    mirrored: true,
    basePivot: timeline.basePivot,
    diagonalExtent: timeline.diagonalExtent,
    leadingRadius: timeline.leadingRadius,
    trailingRadius: timeline.trailingRadius,
    sheetShift: -timeline.sheetShift,
    perspective: timeline.perspective,
    rollProgress: timeline.rollProgress,
    cylinderProgress: timeline.cylinderProgress,
    unfoldProgress: timeline.unfoldProgress,
    heightLiftBias: timeline.heightLiftBias,
    cylinderRadiusNormalized: timeline.cylinderRadiusNormalized,
    unrollWidthNormalized: timeline.unrollWidthNormalized,
    bottomGapNormalized: timeline.bottomGapNormalized,
  );
}

StPageFlipTimeline _resolveThreeStageBackwardTimeline({
  required ReverseFlipPose reversePose,
  required ui.Size pageSize,
}) {
  // 回翻 = 前翻的时间反转 + 水平镜像。
  //
  // 前翻物理过程：
  //   progress 0→1, dragX 从 pageWidth→0, basePivot 从 pageWidth→0
  //   pivot 右侧的纸卷起来，页面从右向左翻过去
  //
  // 回翻物理过程（前翻的逆向）：
  //   progress 0→1, 但对应前翻的 progress 1→0
  //   也就是：回翻初始 = 前翻完成（整页卷着），回翻完成 = 前翻初始（整页平躺）
  //   方向镜像：前翻从右向左卷，回翻从左向右展开
  //
  // 实现：用 (1 - progress) 采样前翻 timeline，然后设 mirrored: true。
  final invertedProgress = (1.0 - reversePose.progress).clamp(0.0, 1.0);

  // 前翻中 dragX ≈ pageWidth * (1 - progress)，
  // 所以 invertedProgress 对应的 dragX = pageWidth * (1 - invertedProgress)
  //                                    = pageWidth * reversePose.progress
  final forwardDragX =
      (pageSize.width * (1.0 - invertedProgress)).clamp(0.0, pageSize.width);

  final forwardTimeline = _resolveForwardTimeline(
    progress: invertedProgress,
    localPagePoint: ui.Offset(forwardDragX, pageSize.height / 2),
    pageSize: pageSize,
  );

  // 镜像前翻 timeline：mirrored: true + sheetShift 取反。
  return StPageFlipTimeline(
    mirrored: true,
    basePivot: forwardTimeline.basePivot,
    diagonalExtent: forwardTimeline.diagonalExtent,
    leadingRadius: forwardTimeline.leadingRadius,
    trailingRadius: forwardTimeline.trailingRadius,
    sheetShift: -forwardTimeline.sheetShift,
    perspective: forwardTimeline.perspective,
    rollProgress: forwardTimeline.rollProgress,
    cylinderProgress: forwardTimeline.cylinderProgress,
    unfoldProgress: forwardTimeline.unfoldProgress,
    heightLiftBias: forwardTimeline.heightLiftBias,
    cylinderRadiusNormalized: forwardTimeline.cylinderRadiusNormalized,
    unrollWidthNormalized: forwardTimeline.unrollWidthNormalized,
    bottomGapNormalized: forwardTimeline.bottomGapNormalized,
  );
}
