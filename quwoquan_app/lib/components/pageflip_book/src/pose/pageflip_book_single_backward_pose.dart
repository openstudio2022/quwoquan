import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book/src/contracts/pageflip_book_contracts.dart';

enum PageflipBookSingleBackwardPosePhase { emerge, unroll, settle }

@immutable
class PageflipBookSingleBackwardPose {
  const PageflipBookSingleBackwardPose({
    required this.phase,
    required this.dragPoint,
    required this.startPoint,
    required this.corner,
    required this.dragProgress,
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

  final PageflipBookSingleBackwardPosePhase phase;
  final Offset dragPoint;
  final Offset startPoint;
  final PageflipBookCorner corner;
  final double dragProgress;
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
}
