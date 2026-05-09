import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/animation.dart';
import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/reverse_curl_calculation.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

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
    this.backwardProjectedFrame,
    this.routeBSpineMirroredApplied = false,
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
  final ArticlePageBackwardProjectedFrame? backwardProjectedFrame;

  /// True iff this frame's BACK geometry has been X-mirrored to align with
  /// the forward rendering pipeline (route B M1 invariant). Only set on
  /// portrait single-page BACK frames.
  final bool routeBSpineMirroredApplied;

  bool get usesThreeStageBackflow =>
      direction == StPageFlipDirection.back &&
      renderDirection == StPageFlipDirection.forward &&
      reversePose != null;
}

/// 后翻 projected frame：路线 B 主线下仅承载 fold line 与 free-edge line，
/// 用于 diagnostic guide layer。所有派生多边形（previousFoldSurfacePolygon /
/// previousFrontFoldPolygon / previousBackFoldPolygon / currentResidualPolygon
/// 等）已被废弃；sheet 与 current 的真相源是 `flippingClipArea` 与
/// `bottomClipArea`，渲染层直接消费、不得再在此处派生。
@immutable
class ArticlePageBackwardProjectedFrame {
  const ArticlePageBackwardProjectedFrame({
    required this.foldLine,
    required this.projectedRightEdgeLine,
    required this.replayLocalPoint,
    required this.edgeEnteredPage,
    required this.foldLineSource,
    required this.edgeLineSource,
  });

  final (ui.Offset, ui.Offset) foldLine;
  final (ui.Offset, ui.Offset) projectedRightEdgeLine;
  final ui.Offset replayLocalPoint;
  final bool edgeEnteredPage;
  final String foldLineSource;
  final String edgeLineSource;
}

enum ArticlePageBackwardLeafPhase { emerge, unroll, settle }

@immutable
class ArticlePageBackwardLeafFrame {
  const ArticlePageBackwardLeafFrame({
    required this.phase,
    required this.emergenceProgress,
    required this.unrollProgress,
    required this.settleProgress,
    required this.seamXNormalized,
    required this.versoRevealWidthNormalized,
    required this.edgeBandWidthNormalized,
    required this.coveredWidthNormalized,
    required this.rectoCoverageNormalized,
    required this.versoOverlayStartNormalized,
    required this.versoOverlayEndNormalized,
    required this.laidDownWidthNormalized,
    required this.curlWidthNormalized,
    required this.rectoRevealWidthNormalized,
    required this.bottomRevealStartNormalized,
    required this.curlPivotNormalized,
    required this.edgeLift,
  });

  final ArticlePageBackwardLeafPhase phase;
  final double emergenceProgress;
  final double unrollProgress;
  final double settleProgress;
  final double seamXNormalized;
  final double versoRevealWidthNormalized;
  final double edgeBandWidthNormalized;
  final double coveredWidthNormalized;
  final double rectoCoverageNormalized;
  final double versoOverlayStartNormalized;
  final double versoOverlayEndNormalized;
  final double laidDownWidthNormalized;
  final double curlWidthNormalized;
  final double rectoRevealWidthNormalized;
  final double bottomRevealStartNormalized;
  final double curlPivotNormalized;
  final double edgeLift;

  double get totalRectoVisibleWidthNormalized =>
      (coveredWidthNormalized * rectoCoverageNormalized)
          .clamp(0.0, 1.0)
          .toDouble();

  double get currentRevealWidthNormalized =>
      (1.0 - bottomRevealStartNormalized).clamp(0.0, 1.0).toDouble();
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
  final edgeBandProgress = Curves.easeOutCubic.transform(
    ((unrollProgress - 0.08) / 0.54).clamp(0.0, 1.0),
  );
  final edgeBandWidth =
      ((ui.lerpDouble(0.0, 0.022, edgeBandProgress) ?? 0.0) *
              (1 - settleProgress * 0.28))
          .clamp(0.0, 0.032)
          .toDouble();
  final rectoRevealProgress = Curves.easeOutCubic.transform(
    ((unrollProgress - 0.14) / 0.74).clamp(0.0, 1.0),
  );
  final rectoRevealWidth = math.min(
    curlWidth * (0.08 + rectoRevealProgress * 0.42),
    curlWidth * 0.58,
  );
  final coveredWidth = math.min(1.0, laidDownWidth + curlWidth);
  // Paper-fold geometry: when the leaf is folded along F (= coveredWidth in
  // normalized units), the lifted segment occupies screen [2F - W, F]. The
  // recto only becomes visible on the spine side once 2F > W, i.e. once the
  // fold has crossed the page midpoint. The boundary E satisfies E = 2F - W,
  // which translates to rectoCoverage = E / F = (2F - W) / F = 2 - 1/covered.
  // For covered <= 0.5 the entire leaf is still folded over, so the recto is
  // not yet exposed. Same formula react-pageflip uses for back replay.
  final rectoCoverageByFold = coveredWidth > 0.5
      ? (2.0 - 1.0 / coveredWidth).clamp(0.0, 1.0).toDouble()
      : 0.0;
  final rectoCoverageByCurl =
      (Curves.easeOutCubic.transform(
                ((settledProgress - 0.24) / 0.38).clamp(0.0, 1.0),
              ) *
              0.72)
          .clamp(0.0, 1.0)
          .toDouble();
  // Recto ownership must stay locked until the fold crosses the page midpoint.
  // Curl timing may change appearance, but it must not make the front face
  // appear before the physical fold has exposed the spine-side segment.
  final rectoCoverage = coveredWidth > 0.5
      ? math
            .max(math.max(rectoCoverageByFold, rectoCoverageByCurl), settleProgress)
            .clamp(0.0, 1.0)
            .toDouble()
      : 0.0;
  final versoOverlayStart = (coveredWidth * rectoCoverage)
      .clamp(0.0, coveredWidth)
      .toDouble();
  final versoOverlayEnd = coveredWidth;
  final versoRevealWidth = math
      .max(0.0, versoOverlayEnd - versoOverlayStart)
      .clamp(0.0, 1.0)
      .toDouble();
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
    seamXNormalized: coveredWidth,
    versoRevealWidthNormalized: versoRevealWidth,
    edgeBandWidthNormalized: edgeBandWidth,
    coveredWidthNormalized: coveredWidth,
    rectoCoverageNormalized: rectoCoverage,
    versoOverlayStartNormalized: versoOverlayStart,
    versoOverlayEndNormalized: versoOverlayEnd,
    laidDownWidthNormalized: laidDownWidth,
    curlWidthNormalized: curlWidth,
    rectoRevealWidthNormalized: rectoRevealWidth,
    bottomRevealStartNormalized: coveredWidth,
    curlPivotNormalized: curlPivotNormalized,
    edgeLift: edgeLift,
  );
}

double resolveArticlePageBackwardSeamX({
  required ArticlePageBackwardLeafFrame frame,
  required ui.Size pageSize,
}) {
  return (pageSize.width * frame.seamXNormalized)
      .clamp(0.0, pageSize.width)
      .toDouble();
}

ui.Rect resolveArticlePageBackwardBottomRevealRect({
  required ArticlePageBackwardLeafFrame frame,
  required ui.Size pageSize,
}) {
  final revealStart = (pageSize.width * frame.bottomRevealStartNormalized)
      .clamp(0.0, pageSize.width)
      .toDouble();
  return ui.Rect.fromLTWH(
    revealStart,
    0,
    math.max(0.0, pageSize.width - revealStart),
    pageSize.height,
  );
}

List<ui.Offset> resolveArticlePageBackwardFlippingClipArea({
  required ArticlePageBackwardLeafFrame frame,
  required ui.Size pageSize,
}) {
  final seamX = resolveArticlePageBackwardSeamX(
    frame: frame,
    pageSize: pageSize,
  );
  return <ui.Offset>[
    ui.Offset.zero,
    ui.Offset(seamX, 0),
    ui.Offset(seamX, pageSize.height),
    ui.Offset(0, pageSize.height),
  ];
}

List<ui.Offset> resolveArticlePageBackwardBottomClipArea({
  required ArticlePageBackwardLeafFrame frame,
  required ui.Size pageSize,
}) {
  final revealRect = resolveArticlePageBackwardBottomRevealRect(
    frame: frame,
    pageSize: pageSize,
  );
  return <ui.Offset>[
    revealRect.topLeft,
    revealRect.topRight,
    revealRect.bottomRight,
    revealRect.bottomLeft,
  ];
}

ui.Offset resolveArticlePageBackwardFlippingAnchor({
  required ArticlePageBackwardLeafFrame frame,
  required ui.Size pageSize,
  required StPageFlipCorner corner,
}) {
  return ui.Offset(0, corner == StPageFlipCorner.top ? 0 : pageSize.height);
}

ui.Offset resolveArticlePageBackwardBottomAnchor({
  required ArticlePageBackwardLeafFrame frame,
  required ui.Size pageSize,
  required StPageFlipCorner corner,
}) {
  return ui.Offset.zero;
}

double resolveArticlePageBackwardAngle({
  required ArticlePageBackwardLeafFrame frame,
  required StPageFlipCorner corner,
}) {
  return 0.0;
}

StPageFlipShadowData resolveArticlePageBackwardShadowData({
  required ArticlePageBackwardLeafFrame frame,
  required ui.Size pageSize,
  required StPageFlipCorner corner,
  double maxShadowOpacity = 1.0,
}) {
  final seamX = resolveArticlePageBackwardSeamX(
    frame: frame,
    pageSize: pageSize,
  );
  final width = math.max(
    pageSize.width * 0.08,
    pageSize.width *
        (frame.versoRevealWidthNormalized +
            frame.edgeBandWidthNormalized * 2.4),
  );
  final opacity =
      ((0.12 + frame.emergenceProgress * 0.08 + frame.unrollProgress * 0.1) *
              (1 - frame.settleProgress * 0.45) *
              maxShadowOpacity)
          .clamp(0.0, 1.0)
          .toDouble();
  return StPageFlipShadowData(
    position: ui.Offset(
      seamX,
      corner == StPageFlipCorner.top ? 0 : pageSize.height,
    ),
    angle: 0,
    width: width,
    opacity: opacity,
    direction: StPageFlipDirection.back,
    progress: frame.seamXNormalized * 100,
  );
}

StPageFlipDirection resolvePageFlipRenderDirection({
  required StPageFlipDirection direction,
  required StPageFlipOrientation orientation,
  ReverseFlipPose? reversePose,
}) {
  return direction;
}

ui.Offset resolveBackwardReplayLocalPagePoint({
  required ui.Offset localPagePoint,
  required ui.Size pageSize,
}) {
  return resolveBackwardReplayCanonicalPoint(
    localPagePoint: localPagePoint,
    pageWidth: pageSize.width,
    pageHeight: pageSize.height,
  );
}

double resolveBackwardReplayProgress(double progress) {
  return (1.0 - progress).clamp(0.0, 1.0).toDouble();
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
  if (direction == StPageFlipDirection.back) {
    return _resolveBackwardReplayTimeline(
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

StPageFlipTimeline _resolveBackwardReplayTimeline({
  required double progress,
  required ui.Offset localPagePoint,
  required ui.Size pageSize,
  required StPageFlipCurlAngleBand angleBand,
}) {
  final replayProgress = resolveBackwardReplayProgress(progress);
  final replayLocalPoint = resolveBackwardReplayLocalPagePoint(
    localPagePoint: localPagePoint,
    pageSize: pageSize,
  );
  final replayTimeline = _resolveForwardTimeline(
    progress: replayProgress,
    localPagePoint: replayLocalPoint,
    pageSize: pageSize,
    angleBand: angleBand,
  );
  return StPageFlipTimeline(
    mirrored: true,
    curlAngleBand: replayTimeline.curlAngleBand,
    basePivot: replayTimeline.basePivot,
    diagonalExtent: replayTimeline.diagonalExtent,
    leadingRadius: replayTimeline.leadingRadius,
    trailingRadius: replayTimeline.trailingRadius,
    sheetShift: replayTimeline.sheetShift,
    perspective: replayTimeline.perspective,
    rollProgress: replayTimeline.rollProgress,
    cylinderProgress: replayTimeline.cylinderProgress,
    unfoldProgress: replayTimeline.unfoldProgress,
    heightLiftBias: replayTimeline.heightLiftBias,
    cylinderRadiusNormalized: replayTimeline.cylinderRadiusNormalized,
    unrollWidthNormalized: replayTimeline.unrollWidthNormalized,
    bottomGapNormalized: replayTimeline.bottomGapNormalized,
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
  final diagonalExtent =
      ui.lerpDouble(
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
  final radiusBase =
      ui.lerpDouble(
        math.max(curlWidth / math.pi, switch (angleBand) {
          StPageFlipCurlAngleBand.shallow => pageSize.width * 0.078,
          StPageFlipCurlAngleBand.mid => pageSize.width * 0.075,
          StPageFlipCurlAngleBand.steep => pageSize.width * 0.072,
        }),
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
            pageSize.width * 0.022,
            Curves.easeOut.transform(progress),
          ) ??
          0.0);
  return StPageFlipTimeline(
    mirrored: false,
    curlAngleBand: angleBand,
    basePivot: localDragX,
    diagonalExtent: diagonalExtent,
    leadingRadius:
        radiusBase *
        switch (angleBand) {
          StPageFlipCurlAngleBand.shallow => 1.08,
          StPageFlipCurlAngleBand.mid => 1.07,
          StPageFlipCurlAngleBand.steep => 1.06,
        },
    trailingRadius:
        radiusBase *
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
      StPageFlipCurlAngleBand.shallow => 0.018,
      StPageFlipCurlAngleBand.mid => 0.021,
      StPageFlipCurlAngleBand.steep => 0.024,
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
