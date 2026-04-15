import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/fold_axis_state_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/page_touch_state_v2.dart';

@immutable
class LeafPoseV2 {
  const LeafPoseV2({
    required this.pageSize,
    required this.touchState,
    required this.foldAxisState,
    required this.flatLimitX,
    required this.diagonalExtent,
    required this.curlRadius,
    required this.maxTheta,
    required this.liftAmount,
    required this.heightLiftBias,
  });

  final Size pageSize;
  final PageTouchStateV2 touchState;
  final FoldAxisStateV2 foldAxisState;
  final double flatLimitX;
  final double diagonalExtent;
  final double curlRadius;
  final double maxTheta;
  final double liftAmount;
  final double heightLiftBias;

  PageflipBookIsolatedDirection get direction => touchState.direction;

  PageflipBookIsolatedCorner get corner => touchState.corner;

  double get progress => foldAxisState.progress;

  double get flatWidthNormalized {
    if (pageSize.width <= 0) {
      return 0;
    }
    return (flatLimitX / pageSize.width).clamp(0.0, 1.0).toDouble();
  }

  bool get hasCurl => progress > 0.001 && curlRadius > 0.001;

  double get foldXNormalized => flatWidthNormalized;

  double resolveCornerFactor(double localY) {
    if (pageSize.height <= 0) {
      return 0;
    }
    final normalizedY = (localY / pageSize.height).clamp(0.0, 1.0).toDouble();
    return corner == PageflipBookIsolatedCorner.bottom
        ? normalizedY
        : (1 - normalizedY);
  }

  double resolveRowPivot(double localY) {
    final cornerFactor = resolveCornerFactor(localY);
    return flatLimitX + (1 - cornerFactor) * diagonalExtent;
  }

  double thetaForPoint(double localX, double localY) {
    final rowPivot = resolveRowPivot(localY);
    final curlDistance = (localX - rowPivot)
        .clamp(0.0, double.infinity)
        .toDouble();
    if (curlDistance <= 0.0001 || curlRadius <= 0.0001) {
      return 0;
    }
    return (curlDistance / curlRadius).clamp(0.0, maxTheta).toDouble();
  }
}
