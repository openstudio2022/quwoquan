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
  // Backward flip now mirrors forward — no separate reverse light model.
  // The reverse* variables are kept at 0 so the forward light path applies
  // symmetrically to both directions.
  const reverseRoll = 0.0;
  const reverseCylinder = 0.0;
  const reverseUnfold = 0.0;
  const reverseRadius = 0.0;
  const reverseUnrollWidthFactor = 0.0;
  const reverseBottomGap = 0.0;
  final tunnelShadowStrength =
      (0.22 +
              settledProgress * 0.16 +
              settledLift * 0.14 +
              reverseRoll * 0.12 +
              reverseCylinder * 0.16 +
              reverseRadius * 0.18 +
              reverseBottomGap * 0.14 -
              reverseUnfold * 0.06 -
              reverseUnrollWidthFactor * 0.05)
          .clamp(0.0, 1.0)
          .toDouble();
  final edgeHighlightStrength =
      (0.14 +
              settledLift * 0.12 +
              settledProgress * 0.06 +
              reverseCylinder * 0.08 +
              reverseRadius * 0.06 +
              reverseUnfold * 0.16 +
              reverseUnrollWidthFactor * 0.2)
          .clamp(0.0, 1.0)
          .toDouble();
  final bottomShadowStrength =
      (0.17 +
              settledProgress * 0.13 +
              settledLift * 0.08 +
              reverseRoll * 0.05 +
              reverseCylinder * 0.08 +
              reverseBottomGap * 0.26 +
              reverseRadius * 0.09 -
              reverseUnfold * 0.04)
          .clamp(0.0, 1.0)
          .toDouble();
  final backfaceOcclusionStrength =
      (0.08 +
              settledProgress * 0.04 +
              settledLift * 0.03 +
              reverseRoll * 0.03 +
              reverseCylinder * 0.05 +
              reverseRadius * 0.08 +
              reverseBottomGap * 0.05 -
              reverseUnrollWidthFactor * 0.02 -
              reverseUnfold * 0.04)
          .clamp(0.06, 0.28)
          .toDouble();
  final backfaceTintStrength =
      (0.09 +
              settledProgress * 0.042 +
              settledLift * 0.032 +
              reverseRoll * 0.032 +
              reverseRadius * 0.066 +
              reverseBottomGap * 0.035 -
              reverseUnrollWidthFactor * 0.018 -
              reverseUnfold * 0.028)
          .clamp(0.08, 0.24)
          .toDouble();
  final spineAmbientStrength =
      (0.08 +
              settledProgress * 0.14 +
              (1 - settledFold) * 0.08 +
              reverseRoll * 0.08 +
              reverseRadius * 0.06)
          .clamp(0.0, 1.0)
          .toDouble();
  return ArticlePageCurlLightState(
    direction: direction,
    corner: corner,
    foldXNormalized: settledFold,
    curlLift: settledLift,
    rollProgress: settledRoll,
    cylinderProgress: cylinderProgress.clamp(0.0, 1.0).toDouble(),
    unfoldProgress: unfoldProgress.clamp(0.0, 1.0).toDouble(),
    tunnelShadowStrength: tunnelShadowStrength,
    edgeHighlightStrength: edgeHighlightStrength,
    bottomShadowStrength: bottomShadowStrength,
    backfaceTintStrength: backfaceTintStrength,
    backfaceOcclusionStrength: backfaceOcclusionStrength,
    spineAmbientStrength: spineAmbientStrength,
  );
}
