import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/foundation.dart';

@immutable
class PageflipReleaseDecision {
  const PageflipReleaseDecision({
    required this.commitsTurn,
    required this.directionalVelocityDx,
    required this.directionalDistanceDx,
    required this.settleDuration,
  });

  final bool commitsTurn;
  final double directionalVelocityDx;
  final double directionalDistanceDx;
  final Duration settleDuration;
}

PageflipReleaseDecision resolvePageflipReleaseDecision({
  required bool isForwardDirection,
  required double progress,
  required double pageWidth,
  required double velocityDx,
  Offset? dragStart,
  Offset? dragLatest,
  DateTime? dragStartedAt,
  bool usesMirroredBackwardReplay = false,
}) {
  final directionSign = isForwardDirection ? -1.0 : 1.0;
  final safeVelocityDx = velocityDx.isFinite ? velocityDx : 0.0;
  final directionalVelocityDx = safeVelocityDx * directionSign;
  final directionalDistanceDx = dragStart != null && dragLatest != null
      ? (dragLatest.dx - dragStart.dx) * directionSign
      : 0.0;
  final dragRatio = pageWidth <= 0
      ? 0.0
      : (directionalDistanceDx / pageWidth).clamp(0.0, 1.0).toDouble();
  final elapsedMs = dragStartedAt == null
      ? 0
      : DateTime.now().difference(dragStartedAt).inMilliseconds;
  final crossedMidpoint = progress >
      (usesMirroredBackwardReplay
          ? 1.0
          : (isForwardDirection ? 0.44 : 1.0));
  final sustainedPull = dragRatio > (usesMirroredBackwardReplay ? 0.3 : 0.24);
  final deliberateCornerLift =
      progress > (usesMirroredBackwardReplay ? 0.18 : 0.14) &&
      dragRatio > (usesMirroredBackwardReplay ? 0.12 : 0.08);
  final deliberateDrag =
      progress > (usesMirroredBackwardReplay ? 0.26 : 0.2) &&
      dragRatio > (usesMirroredBackwardReplay ? 0.2 : 0.16);
  final decisiveVelocity =
      directionalVelocityDx > (usesMirroredBackwardReplay ? 340 : 260);
  final quickLift =
      !usesMirroredBackwardReplay &&
      elapsedMs > 0 &&
      elapsedMs < 420 &&
      dragRatio > 0.06 &&
      progress > 0.12;
  final assistedSnap =
      !usesMirroredBackwardReplay &&
      deliberateCornerLift &&
      directionalVelocityDx > 120;
  final commitsTurn =
      crossedMidpoint ||
      sustainedPull ||
      deliberateDrag ||
      decisiveVelocity ||
      quickLift ||
      assistedSnap;
  final remainingProgress = commitsTurn ? (1 - progress) : progress;
  final travelPx = math.max(pageWidth * remainingProgress, pageWidth * 0.12);
  final speedPxPerSecond = math.max(directionalVelocityDx.abs(), pageWidth * 1.8);
  final settleDuration = Duration(
    milliseconds: (travelPx / speedPxPerSecond * 1000)
        .round()
        .clamp(180, 420),
  );
  return PageflipReleaseDecision(
    commitsTurn: commitsTurn,
    directionalVelocityDx: directionalVelocityDx,
    directionalDistanceDx: directionalDistanceDx,
    settleDuration: settleDuration,
  );
}
