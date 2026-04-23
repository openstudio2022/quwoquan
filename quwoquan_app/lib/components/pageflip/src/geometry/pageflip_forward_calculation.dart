import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class PageflipForwardCalculation {
  PageflipForwardCalculation({
    required StPageFlipCorner corner,
    required double pageWidth,
    required double pageHeight,
  }) : _calculation = StPageFlipCalculation(
         direction: StPageFlipDirection.forward,
         corner: corner,
         pageWidth: pageWidth,
         pageHeight: pageHeight,
       );

  final StPageFlipCalculation _calculation;

  bool calc(Offset localPagePoint) => _calculation.calc(localPagePoint);

  double getAngle() => _calculation.getAngle();
  double getProgress() => _calculation.getFlippingProgress() / 100;
  Offset getActiveCorner() => _calculation.getActiveCorner();
  Offset getBottomPagePosition() => _calculation.getBottomPagePosition();
  List<Offset> getFlippingClipArea() => _calculation.getFlippingClipArea();
  List<Offset> getBottomClipArea() => _calculation.getBottomClipArea();
}
