import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class ArticlePageCurlLightConfig {
  const ArticlePageCurlLightConfig({
    required this.shadowColor,
    required this.highlightColor,
    required this.paperTintColor,
    required this.ambientOcclusionColor,
  });

  final Color shadowColor;
  final Color highlightColor;
  final Color paperTintColor;
  final Color ambientOcclusionColor;
}

@immutable
class ArticlePageCurlLightState {
  const ArticlePageCurlLightState({
    required this.direction,
    required this.corner,
    required this.foldXNormalized,
    required this.curlLift,
    required this.rollProgress,
    required this.cylinderProgress,
    required this.unfoldProgress,
    required this.tunnelShadowStrength,
    required this.edgeHighlightStrength,
    required this.bottomShadowStrength,
    required this.backfaceTintStrength,
    required this.backfaceOcclusionStrength,
    required this.spineAmbientStrength,
  });

  final StPageFlipDirection direction;
  final StPageFlipCorner corner;
  final double foldXNormalized;
  final double curlLift;
  final double rollProgress;
  final double cylinderProgress;
  final double unfoldProgress;
  final double tunnelShadowStrength;
  final double edgeHighlightStrength;
  final double bottomShadowStrength;
  final double backfaceTintStrength;
  final double backfaceOcclusionStrength;
  final double spineAmbientStrength;
}

ArticlePageCurlLightState resolveArticlePageCurlLightState({
  required double progress,
  required double foldXNormalized,
  required double curlLift,
  double rollProgress = 0,
  double cylinderProgress = 0,
  double unfoldProgress = 0,
  double cylinderRadiusNormalized = 0,
  double unrollWidthNormalized = 0,
  double bottomGapNormalized = 0,
  required StPageFlipDirection direction,
  required StPageFlipCorner corner,
}) {
  final settledProgress = progress.clamp(0.0, 1.0).toDouble();
  final settledLift = curlLift.clamp(0.0, 1.0).toDouble();
  final settledFold = foldXNormalized.clamp(0.0, 1.0).toDouble();
  final settledRoll = rollProgress.clamp(0.0, 1.0).toDouble();
  final settledCylinder = cylinderProgress.clamp(0.0, 1.0).toDouble();
  final settledUnfold = unfoldProgress.clamp(0.0, 1.0).toDouble();
  final settledRadius = cylinderRadiusNormalized.clamp(0.0, 1.0).toDouble();
  final settledUnrollWidth = unrollWidthNormalized.clamp(0.0, 1.0).toDouble();
  final settledBottomGap = bottomGapNormalized.clamp(0.0, 1.0).toDouble();
  final tunnelShadowStrength =
      (0.22 +
              settledProgress * 0.16 +
              settledLift * 0.14 +
              settledRoll * 0.12 +
              settledCylinder * 0.16 +
              settledRadius * 0.18 +
              settledBottomGap * 0.14 -
              settledUnfold * 0.06 -
              settledUnrollWidth * 0.05)
          .clamp(0.0, 1.0)
          .toDouble();
  final edgeHighlightStrength =
      (0.14 +
              settledLift * 0.12 +
              settledProgress * 0.06 +
              settledCylinder * 0.08 +
              settledRadius * 0.06 +
              settledUnfold * 0.16 +
              settledUnrollWidth * 0.2)
          .clamp(0.0, 1.0)
          .toDouble();
  final bottomShadowStrength =
      (0.17 +
              settledProgress * 0.13 +
              settledLift * 0.08 +
              settledRoll * 0.05 +
              settledCylinder * 0.08 +
              settledBottomGap * 0.26 +
              settledRadius * 0.09 -
              settledUnfold * 0.04)
          .clamp(0.0, 1.0)
          .toDouble();
  final backfaceOcclusionStrength =
      (0.08 +
              settledProgress * 0.04 +
              settledLift * 0.03 +
              settledRoll * 0.03 +
              settledCylinder * 0.05 +
              settledRadius * 0.08 +
              settledBottomGap * 0.05 -
              settledUnrollWidth * 0.02 -
              settledUnfold * 0.04)
          .clamp(0.06, 0.28)
          .toDouble();
  final backfaceTintStrength =
      (0.09 +
              settledProgress * 0.042 +
              settledLift * 0.032 +
              settledRoll * 0.032 +
              settledRadius * 0.066 +
              settledBottomGap * 0.035 -
              settledUnrollWidth * 0.018 -
              settledUnfold * 0.028)
          .clamp(0.08, 0.24)
          .toDouble();
  final spineAmbientStrength =
      (0.08 +
              settledProgress * 0.14 +
              (1 - settledFold) * 0.08 +
              settledRoll * 0.08 +
              settledRadius * 0.06 +
              settledCylinder * 0.04)
          .clamp(0.0, 1.0)
          .toDouble();
  return ArticlePageCurlLightState(
    direction: direction,
    corner: corner,
    foldXNormalized: settledFold,
    curlLift: settledLift,
    rollProgress: settledRoll,
    cylinderProgress: settledCylinder,
    unfoldProgress: settledUnfold,
    tunnelShadowStrength: tunnelShadowStrength,
    edgeHighlightStrength: edgeHighlightStrength,
    bottomShadowStrength: bottomShadowStrength,
    backfaceTintStrength: backfaceTintStrength,
    backfaceOcclusionStrength: backfaceOcclusionStrength,
    spineAmbientStrength: spineAmbientStrength,
  );
}
