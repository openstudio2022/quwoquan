part of 'curl_mesh_builder.dart';

double _resolveFoldTheta(_CurlTimeline timeline) {
  final seamThetaBias = timeline.mirrored || timeline.reversePose != null
      ? 0.04
      : switch (timeline.curlAngleBand) {
          StPageFlipCurlAngleBand.shallow => 0.045,
          StPageFlipCurlAngleBand.mid => 0.04,
          StPageFlipCurlAngleBand.steep => 0.035,
        };
  return math.pi / 2 + seamThetaBias;
}

@immutable
class _CurlMeshPoint {
  const _CurlMeshPoint({
    required this.projected,
    required this.rectoTexture,
    required this.versoTexture,
    required this.theta,
    required this.seamMetric,
    required this.depth,
  });

  const _CurlMeshPoint.empty()
    : projected = Offset.zero,
      rectoTexture = Offset.zero,
      versoTexture = Offset.zero,
      theta = 0,
      seamMetric = 0,
      depth = 0;

  final Offset projected;
  final Offset rectoTexture;
  final Offset versoTexture;
  final double theta;
  final double seamMetric;
  final double depth;
}

@immutable
class _CurlTimeline {
  const _CurlTimeline({
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
    required this.forwardAngle,
    required this.reversePose,
  });

  factory _CurlTimeline.fromPageTimeline(
    StPageFlipTimeline timeline, {
    required ReverseFlipPose? reversePose,
  }) {
    return _CurlTimeline(
      mirrored: timeline.mirrored,
      curlAngleBand: timeline.curlAngleBand,
      basePivot: timeline.basePivot,
      diagonalExtent: timeline.diagonalExtent,
      leadingRadius: timeline.leadingRadius,
      trailingRadius: timeline.trailingRadius,
      sheetShift: timeline.sheetShift,
      perspective: timeline.perspective,
      rollProgress: timeline.rollProgress,
      cylinderProgress: timeline.cylinderProgress,
      unfoldProgress: timeline.unfoldProgress,
      heightLiftBias: timeline.heightLiftBias,
      forwardAngle: null,
      reversePose: reversePose,
    );
  }

  factory _CurlTimeline.fromRenderFrame(StPageFlipRenderFrame renderFrame) {
    return _CurlTimeline(
      mirrored: renderFrame.timeline.mirrored,
      curlAngleBand: renderFrame.timeline.curlAngleBand,
      basePivot: renderFrame.timeline.basePivot,
      diagonalExtent: renderFrame.timeline.diagonalExtent,
      leadingRadius: renderFrame.timeline.leadingRadius,
      trailingRadius: renderFrame.timeline.trailingRadius,
      sheetShift: renderFrame.timeline.sheetShift,
      perspective: renderFrame.timeline.perspective,
      rollProgress: renderFrame.timeline.rollProgress,
      cylinderProgress: renderFrame.timeline.cylinderProgress,
      unfoldProgress: renderFrame.timeline.unfoldProgress,
      heightLiftBias: renderFrame.timeline.heightLiftBias,
      forwardAngle: renderFrame.direction == StPageFlipDirection.forward
          ? renderFrame.angle
          : null,
      reversePose: renderFrame.reversePose,
    );
  }

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
  final double? forwardAngle;
  final ReverseFlipPose? reversePose;
}

abstract class _CurlProjection {
  _CurlMeshPoint project({
    required double localX,
    required double localY,
    required double rowPivot,
    required double rowRadius,
    required double seamX,
  });
}

class _ForwardCurlProjection implements _CurlProjection {
  const _ForwardCurlProjection({
    required this.pageRect,
    required this.pageSize,
    required this.corner,
    required this.timeline,
    required this.foldTheta,
  });

  final Rect pageRect;
  final Size pageSize;
  final StPageFlipCorner corner;
  final _CurlTimeline timeline;
  final double foldTheta;

  @override
  _CurlMeshPoint project({
    required double localX,
    required double localY,
    required double rowPivot,
    required double rowRadius,
    required double seamX,
  }) {
    final rowCurlDistance = math.max(0.0, localX - rowPivot);
    final theta = math.min(math.pi, rowCurlDistance / math.max(rowRadius, 1.0));
    final foldDepth = theta <= 0 ? 0.0 : (1 - math.cos(foldTheta)) * rowRadius;
    final frontDepth = theta <= foldTheta
        ? theta <= 0
              ? 0.0
              : (1 - math.cos(theta)) * rowRadius
        : foldDepth;
    final rigidAngleT = timeline.forwardAngle == null
        ? 0.0
        : (timeline.forwardAngle!.abs() / math.pi).clamp(0.0, 1.0).toDouble();
    final backTravelMultiplier = ui.lerpDouble(1.18, 1.42, rigidAngleT) ?? 1.25;
    final backTravel = theta <= foldTheta
        ? 0.0
        : ((theta - foldTheta) / math.max(math.pi - foldTheta, 0.0001))
                  .clamp(0.0, 1.0)
                  .toDouble() *
              rowRadius *
              backTravelMultiplier;
    final curledX = theta <= foldTheta
        ? rowPivot - frontDepth
        : (rowPivot - foldDepth) - backTravel;
    final cornerFactor = corner == StPageFlipCorner.top
        ? 1 - (localY / math.max(pageSize.height, 1.0))
        : localY / math.max(pageSize.height, 1.0);
    final displayDepth = theta <= foldTheta ? frontDepth : foldDepth;
    final curlHeightOffset =
        (1 - cornerFactor) *
        displayDepth *
        (corner == StPageFlipCorner.top
            ? -timeline.heightLiftBias
            : timeline.heightLiftBias);
    final curlInfluence = (theta <= 0 ? 0.0 : (theta / math.pi))
        .clamp(0.0, 1.0)
        .toDouble();
    final effectiveX = timeline.mirrored ? pageSize.width - curledX : curledX;
    final rectoTexX = timeline.mirrored ? pageSize.width - localX : localX;
    final versoTexX = timeline.mirrored ? localX : pageSize.width - localX;
    return _CurlMeshPoint(
      projected: Offset(
        pageRect.left + effectiveX + timeline.sheetShift * curlInfluence,
        pageRect.top + localY + curlHeightOffset,
      ),
      rectoTexture: Offset(rectoTexX, localY),
      versoTexture: Offset(versoTexX, localY),
      theta: theta,
      seamMetric: localX - seamX,
      depth: displayDepth,
    );
  }
}

class _ReversePoseCurlProjection implements _CurlProjection {
  const _ReversePoseCurlProjection({
    required this.pageRect,
    required this.pageSize,
    required this.corner,
    required this.timeline,
    required this.foldTheta,
  });

  final Rect pageRect;
  final Size pageSize;
  final StPageFlipCorner corner;
  final _CurlTimeline timeline;
  final double foldTheta;

  @override
  _CurlMeshPoint project({
    required double localX,
    required double localY,
    required double rowPivot,
    required double rowRadius,
    required double seamX,
  }) {
    final reversePose = timeline.reversePose!;
    final coveredWidth = reversePose.coveredWidth
        .clamp(0.0, pageSize.width)
        .toDouble();
    final flatWidth = reversePose.unrollWidth
        .clamp(0.0, coveredWidth)
        .toDouble();
    final visibleCurlWidth = math.max(1.0, coveredWidth - flatWidth);
    final cylinderRadius = math.max(
      reversePose.cylinderRadius,
      visibleCurlWidth / math.pi,
    );
    double theta;
    double visualX;
    double depth;
    if (localX <= flatWidth) {
      theta = 0.0;
      visualX = localX;
      depth = 0.0;
    } else if (localX <= coveredWidth) {
      final bandT = ((localX - flatWidth) / visibleCurlWidth)
          .clamp(0.0, 1.0)
          .toDouble();
      theta = bandT * math.pi;
      visualX = flatWidth + (1 - math.cos(theta)) * visibleCurlWidth * 0.5;
      depth = math.sin(theta) * cylinderRadius;
    } else {
      theta = math.pi;
      visualX = coveredWidth;
      depth = 0.0;
    }
    final cornerFactor = corner == StPageFlipCorner.top
        ? 1 - (localY / math.max(pageSize.height, 1.0))
        : localY / math.max(pageSize.height, 1.0);
    final liftPx =
        pageSize.height *
        reversePose.lift *
        0.16 *
        (theta <= 0 ? 0.0 : math.sin(theta));
    final curlHeightOffset =
        reversePose.cornerBiasY * (1 - cornerFactor) * liftPx;
    final worldX = pageRect.left + visualX;
    final worldY = pageRect.top + localY + curlHeightOffset;
    final projectionCenterX = pageRect.left + flatWidth;
    final projectionCenterY = pageRect.top + localY;
    final scale = depth <= 0
        ? 1.0
        : timeline.perspective / (timeline.perspective + depth * 0.35);
    return _CurlMeshPoint(
      projected: Offset(
        projectionCenterX + (worldX - projectionCenterX) * scale,
        projectionCenterY + (worldY - projectionCenterY) * scale,
      ),
      rectoTexture: Offset(localX, localY),
      versoTexture: Offset(pageSize.width - localX, localY),
      theta: theta,
      seamMetric: theta - foldTheta,
      depth: depth,
    );
  }
}

class _BackwardLeafCurlProjection implements _CurlProjection {
  const _BackwardLeafCurlProjection({
    required this.pageRect,
    required this.pageSize,
    required this.timeline,
    required this.backwardLeafFrame,
  });

  final Rect pageRect;
  final Size pageSize;
  final _CurlTimeline timeline;
  final ArticlePageBackwardLeafFrame backwardLeafFrame;

  @override
  _CurlMeshPoint project({
    required double localX,
    required double localY,
    required double rowPivot,
    required double rowRadius,
    required double seamX,
  }) {
    final coveredWidth =
        (backwardLeafFrame.coveredWidthNormalized * pageSize.width)
            .clamp(0.0, pageSize.width)
            .toDouble();
    final flatWidth =
        (backwardLeafFrame.laidDownWidthNormalized * pageSize.width)
            .clamp(0.0, coveredWidth)
            .toDouble();
    final visibleCurlWidth = math.max(1.0, coveredWidth - flatWidth).toDouble();
    final rectoRevealWidth =
        (backwardLeafFrame.rectoRevealWidthNormalized * pageSize.width)
            .clamp(0.0, visibleCurlWidth)
            .toDouble();
    final edgeBandWidth =
        (backwardLeafFrame.edgeBandWidthNormalized * pageSize.width)
            .clamp(0.0, math.max(0.0, visibleCurlWidth - rectoRevealWidth))
            .toDouble();
    final seamSplitWidth = (rectoRevealWidth + edgeBandWidth * 0.5)
        .clamp(visibleCurlWidth * 0.08, visibleCurlWidth * 0.92)
        .toDouble();
    final seamTheta = (seamSplitWidth / visibleCurlWidth * math.pi)
        .clamp(math.pi * 0.08, math.pi * 0.92)
        .toDouble();
    final cylinderRadius = math.max(
      visibleCurlWidth / math.pi,
      pageSize.width * 0.028,
    );

    double theta;
    double visualX;
    double depth;
    if (localX <= flatWidth) {
      theta = 0.0;
      visualX = localX;
      depth = 0.0;
    } else if (localX <= coveredWidth) {
      final bandT = ((localX - flatWidth) / visibleCurlWidth)
          .clamp(0.0, 1.0)
          .toDouble();
      theta = bandT * math.pi;
      visualX = flatWidth + (1 - math.cos(theta)) * visibleCurlWidth * 0.5;
      depth = math.sin(theta) * cylinderRadius;
    } else {
      theta = math.pi;
      visualX = coveredWidth;
      depth = 0.0;
    }

    return _CurlMeshPoint(
      projected: Offset(pageRect.left + visualX, pageRect.top + localY),
      rectoTexture: Offset(localX, localY),
      versoTexture: Offset(pageSize.width - localX, localY),
      theta: theta,
      seamMetric: theta - seamTheta,
      depth: depth,
    );
  }
}
