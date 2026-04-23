import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/reverse_curl_calculation.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class PageflipReverseCalculation {
  PageflipReverseCalculation({
    required StPageFlipCorner corner,
    required double pageWidth,
    required double pageHeight,
  }) : _calculation = ReverseCurlCalculation(
         corner: corner,
         pageWidth: pageWidth,
         pageHeight: pageHeight,
       );

  final ReverseCurlCalculation _calculation;

  bool calc(Offset localPagePoint) => _calculation.calc(localPagePoint);

  ReverseFlipPose? get pose => _calculation.pose;
  double getAngle() => _calculation.getAngle();
  double getProgress() => _calculation.getFlippingProgress() / 100;
  Offset getActiveCorner() => _calculation.getActiveCorner();
  Offset getBottomPagePosition() => _calculation.getBottomPagePosition();
  List<Offset> getFlippingClipArea() => _calculation.getFlippingClipArea();
  List<Offset> getBottomClipArea() => _calculation.getBottomClipArea();
}
