import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/animation.dart';
import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/reverse_curl_calculation.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
enum StPageFlipCurlAngleBand { shallow, mid, steep }

StPageFlipCurlAngleBand resolveForwardCurlAngleBand({
  required ui.Offset localPagePoint,
  required ui.Size pageSize,
  required StPageFlipCorner corner,
}) {
  final horizontalDistance = math.max(pageSize.width - localPagePoint.dx, 1.0);
  final verticalDistance = corner == StPageFlipCorner.bottom
      ? math.max(pageSize.height - localPagePoint.dy, 0.0)
      : math.max(localPagePoint.dy, 0.0);
  final angleDegrees =
      math.atan2(verticalDistance, horizontalDistance) * 180 / math.pi;
  if (angleDegrees < 20) {
    return StPageFlipCurlAngleBand.shallow;
  }
  if (angleDegrees < 45) {
    return StPageFlipCurlAngleBand.mid;
  }
  return StPageFlipCurlAngleBand.steep;
}

@immutable
class StPageFlipTimeline {
  const StPageFlipTimeline({
    required this.mirrored,
    required this.curlAngleBand,
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
  final StPageFlipCurlAngleBand curlAngleBand;
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
    this.backwardLeafFrame,
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
  final ArticlePageBackwardLeafFrame? backwardLeafFrame;

  bool get usesThreeStageBackflow =>
      direction == StPageFlipDirection.back &&
      renderDirection == StPageFlipDirection.forward &&
      reversePose != null;
}

enum ArticlePageBackwardLeafPhase { emerge, unroll, settle }

@immutable
class ArticlePageBackwardLeafFrame {
  const ArticlePageBackwardLeafFrame({
    required this.phase,
    required this.emergenceProgress,
    required this.unrollProgress,
    required this.settleProgress,
    required this.coveredWidthNormalized,
    required this.laidDownWidthNormalized,
    required this.curlWidthNormalized,
    required this.rectoRevealWidthNormalized,
    required this.curlPivotNormalized,
    required this.edgeLift,
  });

  final ArticlePageBackwardLeafPhase phase;
  final double emergenceProgress;
  final double unrollProgress;
  final double settleProgress;
  final double coveredWidthNormalized;
  final double laidDownWidthNormalized;
  final double curlWidthNormalized;
  final double rectoRevealWidthNormalized;
  final double curlPivotNormalized;
  final double edgeLift;
}

ArticlePageBackwardLeafFrame? resolveArticlePageBackwardLeafFrame({
  required StPageFlipDirection direction,
  required double progress,
  ReverseFlipPose? reversePose,
}) {
  if (direction != StPageFlipDirection.back) {
    return null;
  }
  final settledProgress = progress.clamp(0.0, 1.0).toDouble();
  final emergenceProgress = reversePose == null
      ? Curves.easeOutCubic.transform((settledProgress / 0.28).clamp(0.0, 1.0))
      : reversePose.emergenceProgress.clamp(0.0, 1.0).toDouble();
  final unrollProgress = reversePose == null
      ? Curves.easeInOutCubic.transform(
          ((settledProgress - 0.18) / 0.58).clamp(0.0, 1.0),
        )
      : reversePose.unrollProgress.clamp(0.0, 1.0).toDouble();
  final settleProgress = Curves.easeOutCubic.transform(
    ((settledProgress - 0.82) / 0.18).clamp(0.0, 1.0),
  );
  final emergedCurlWidth =
      (ui.lerpDouble(0.032, 0.22, emergenceProgress) ?? 0.09)
          .clamp(0.032, 0.26)
          .toDouble();
  final rollingCurlWidth =
      (ui.lerpDouble(emergedCurlWidth, 0.16, unrollProgress) ??
              emergedCurlWidth)
          .clamp(0.04, 0.24)
          .toDouble();
  final curlWidth =
      (ui.lerpDouble(rollingCurlWidth, 0.0, settleProgress) ?? rollingCurlWidth)
          .clamp(0.0, 0.26)
          .toDouble();
  final laidDownBeforeSettle = (ui.lerpDouble(0.0, 0.76, unrollProgress) ?? 0.0)
      .clamp(0.0, 0.82)
      .toDouble();
  final laidDownWidth =
      (ui.lerpDouble(
                laidDownBeforeSettle,
                math.max(0.0, 1.0 - curlWidth),
                settleProgress,
              ) ??
              laidDownBeforeSettle)
          .clamp(0.0, 1.0)
          .toDouble();
  final coveredWidth = math.min(1.0, laidDownWidth + curlWidth * 0.92);
  final rectoRevealWidth = math.min(
    curlWidth * (0.18 + unrollProgress * 0.28),
    curlWidth * 0.42,
  );
  final curlPivotNormalized = (laidDownWidth + curlWidth * 0.5)
      .clamp(0.0, 1.0)
      .toDouble();
  final edgeLift =
      ((ui.lerpDouble(0.12, 0.34, emergenceProgress) ?? 0.18) *
              (1 - settleProgress * 0.55))
          .clamp(0.08, 0.36)
          .toDouble();
  final phase = settleProgress > 0.001
      ? ArticlePageBackwardLeafPhase.settle
      : unrollProgress > 0.001
      ? ArticlePageBackwardLeafPhase.unroll
      : ArticlePageBackwardLeafPhase.emerge;
  return ArticlePageBackwardLeafFrame(
    phase: phase,
    emergenceProgress: emergenceProgress,
    unrollProgress: unrollProgress,
    settleProgress: settleProgress,
    coveredWidthNormalized: coveredWidth,
    laidDownWidthNormalized: laidDownWidth,
    curlWidthNormalized: curlWidth,
    rectoRevealWidthNormalized: rectoRevealWidth,
    curlPivotNormalized: curlPivotNormalized,
    edgeLift: edgeLift,
  );
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
  required StPageFlipCurlAngleBand angleBand,
  ReverseFlipPose? reversePose,
}) {
  final settledProgress = progress.clamp(0.0, 1.0).toDouble();
  if (direction == StPageFlipDirection.back &&
      renderDirection == StPageFlipDirection.forward &&
      reversePose != null) {
    return _resolveThreeStageBackwardTimeline(
      reversePose: reversePose,
      pageSize: pageSize,
      angleBand: angleBand,
    );
  }
  if (direction == StPageFlipDirection.back) {
    return _resolveMirroredForwardTimeline(
      progress: settledProgress,
      localPagePoint: localPagePoint,
      pageSize: pageSize,
      angleBand: angleBand,
    );
  }
  return _resolveForwardTimeline(
    progress: settledProgress,
    localPagePoint: localPagePoint,
    pageSize: pageSize,
    angleBand: angleBand,
  );
}

StPageFlipTimeline _resolveForwardTimeline({
  required double progress,
  required ui.Offset localPagePoint,
  required ui.Size pageSize,
  required StPageFlipCurlAngleBand angleBand,
}) {
  final localDragX = localPagePoint.dx.clamp(0.0, pageSize.width).toDouble();
  final curlWidth = math.max(1.0, pageSize.width - localDragX);
  final diagonalExtent = ui.lerpDouble(
        switch (angleBand) {
          StPageFlipCurlAngleBand.shallow => pageSize.width * 0.015,
          StPageFlipCurlAngleBand.mid => pageSize.width * 0.018,
          StPageFlipCurlAngleBand.steep => pageSize.width * 0.02,
        },
        switch (angleBand) {
          StPageFlipCurlAngleBand.shallow => pageSize.width * 0.072,
          StPageFlipCurlAngleBand.mid => pageSize.width * 0.078,
          StPageFlipCurlAngleBand.steep => pageSize.width * 0.082,
        },
        Curves.easeOutCubic.transform(progress),
      ) ??
      switch (angleBand) {
        StPageFlipCurlAngleBand.shallow => pageSize.width * 0.072,
        StPageFlipCurlAngleBand.mid => pageSize.width * 0.078,
        StPageFlipCurlAngleBand.steep => pageSize.width * 0.082,
      };
  final radiusBase = ui.lerpDouble(
        math.max(
          curlWidth / math.pi,
          switch (angleBand) {
            StPageFlipCurlAngleBand.shallow => pageSize.width * 0.078,
            StPageFlipCurlAngleBand.mid => pageSize.width * 0.075,
            StPageFlipCurlAngleBand.steep => pageSize.width * 0.072,
          },
        ),
        switch (angleBand) {
          StPageFlipCurlAngleBand.shallow => pageSize.width * 0.064,
          StPageFlipCurlAngleBand.mid => pageSize.width * 0.062,
          StPageFlipCurlAngleBand.steep => pageSize.width * 0.06,
        },
        Curves.easeInOut.transform(progress),
      ) ??
      switch (angleBand) {
        StPageFlipCurlAngleBand.shallow => pageSize.width * 0.064,
        StPageFlipCurlAngleBand.mid => pageSize.width * 0.062,
        StPageFlipCurlAngleBand.steep => pageSize.width * 0.06,
      };
  final sheetShift =
      -(ui.lerpDouble(
            0.0,
            pageSize.width * 0.06,
            Curves.easeOut.transform(progress),
          ) ??
          0.0);
  return StPageFlipTimeline(
    mirrored: false,
    curlAngleBand: angleBand,
    basePivot: localDragX,
    diagonalExtent: diagonalExtent,
    leadingRadius: radiusBase *
        switch (angleBand) {
          StPageFlipCurlAngleBand.shallow => 1.08,
          StPageFlipCurlAngleBand.mid => 1.07,
          StPageFlipCurlAngleBand.steep => 1.06,
        },
    trailingRadius: radiusBase *
        switch (angleBand) {
          StPageFlipCurlAngleBand.shallow => 0.86,
          StPageFlipCurlAngleBand.mid => 0.88,
          StPageFlipCurlAngleBand.steep => 0.9,
        },
    sheetShift: sheetShift,
    perspective: pageSize.width * 4.0,
    rollProgress: progress,
    cylinderProgress: 0.0,
    unfoldProgress: 0.0,
    heightLiftBias: switch (angleBand) {
      StPageFlipCurlAngleBand.shallow => 0.040,
      StPageFlipCurlAngleBand.mid => 0.044,
      StPageFlipCurlAngleBand.steep => 0.048,
    },
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
  required StPageFlipCurlAngleBand angleBand,
}) {
  final mirroredLocalPoint = ui.Offset(
    pageSize.width - localPagePoint.dx.clamp(0.0, pageSize.width),
    localPagePoint.dy,
  );
  final timeline = _resolveForwardTimeline(
    progress: progress,
    localPagePoint: mirroredLocalPoint,
    pageSize: pageSize,
    angleBand: angleBand,
  );
  return StPageFlipTimeline(
    mirrored: true,
    curlAngleBand: timeline.curlAngleBand,
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
  required StPageFlipCurlAngleBand angleBand,
}) {
  final coveredWidth = reversePose.coveredWidth
      .clamp(0.0, pageSize.width)
      .toDouble();
  final flatWidth = reversePose.unrollWidth.clamp(0.0, coveredWidth).toDouble();
  final cylinderRadius = reversePose.cylinderRadius
      .clamp(pageSize.width * 0.02, pageSize.width * 0.16)
      .toDouble();
  final curlWidth = math.max(
    coveredWidth - flatWidth,
    reversePose.cylinderArcWidth.clamp(0.0, pageSize.width),
  );
  final diagonalExtent =
      ((ui.lerpDouble(
                    pageSize.width * 0.05,
                    pageSize.width * 0.16,
                    reversePose.emergenceProgress,
                  ) ??
                  (pageSize.width * 0.09)) *
              (1 - reversePose.unrollProgress * 0.28))
          .clamp(pageSize.width * 0.03, pageSize.width * 0.18)
          .toDouble();
  final heightLiftBias =
      (ui.lerpDouble(0.22, 0.08, reversePose.unrollProgress) ?? 0.14)
          .clamp(0.08, 0.22)
          .toDouble();
  final effectiveRadius = math.max(cylinderRadius, curlWidth / math.pi);
  return StPageFlipTimeline(
    mirrored: true,
    curlAngleBand: angleBand,
    basePivot: (pageSize.width - reversePose.leadingEdgeX)
        .clamp(0.0, pageSize.width)
        .toDouble(),
    diagonalExtent: diagonalExtent,
    leadingRadius: effectiveRadius,
    trailingRadius: math.max(pageSize.width * 0.02, cylinderRadius * 0.86),
    sheetShift:
        (ui.lerpDouble(
                  0.0,
                  pageSize.width * 0.04,
                  reversePose.cylinderProgress,
                ) ??
                0.0)
            .toDouble(),
    perspective: pageSize.width * 10.0,
    rollProgress: reversePose.emergenceProgress.clamp(0.0, 1.0).toDouble(),
    cylinderProgress: reversePose.cylinderProgress.clamp(0.0, 1.0).toDouble(),
    unfoldProgress: reversePose.unrollProgress.clamp(0.0, 1.0).toDouble(),
    heightLiftBias: heightLiftBias,
    cylinderRadiusNormalized: (cylinderRadius / pageSize.width)
        .clamp(0.0, 1.0)
        .toDouble(),
    unrollWidthNormalized: (flatWidth / pageSize.width)
        .clamp(0.0, 1.0)
        .toDouble(),
    bottomGapNormalized: ((pageSize.width - coveredWidth) / pageSize.width)
        .clamp(0.0, 1.0)
        .toDouble(),
  );
}
