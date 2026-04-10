import 'package:flutter/foundation.dart';

enum PageflipBookSingleBackwardSoftPhase { emerge, unroll, settle }

@immutable
class PageflipBookSingleBackwardSoftFrame {
  const PageflipBookSingleBackwardSoftFrame({
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
    required this.liftDirection,
    required this.shadowAxisNormalized,
    required this.commitProgress,
  });

  final PageflipBookSingleBackwardSoftPhase phase;
  final double emergenceProgress;
  final double unrollProgress;
  final double settleProgress;
  final double coveredWidthNormalized;
  final double laidDownWidthNormalized;
  final double curlWidthNormalized;
  final double rectoRevealWidthNormalized;
  final double curlPivotNormalized;
  final double edgeLift;
  final double liftDirection;
  final double shadowAxisNormalized;
  final double commitProgress;

  bool get hasLaidDownSurface => laidDownWidthNormalized > 0;

  bool get hasCurlSurface => curlWidthNormalized > 0;

  double get exposedCurrentWidthNormalized =>
      (1 - coveredWidthNormalized).clamp(0.0, 1.0).toDouble();
}
