import 'dart:ui';

import 'package:flutter/foundation.dart';

enum StPageFlipOrientation { portrait, landscape }

enum StPageFlipDirection { forward, back }

extension StPageFlipDirectionX on StPageFlipDirection {
  bool get isForward => this == StPageFlipDirection.forward;
}

enum StPageFlipCorner { top, bottom }

enum StPageFlipState { read, foldCorner, userFold, flipping }

enum StPageFlipDensity { soft, hard }

@immutable
class StPageFlipBoundsRect {
  const StPageFlipBoundsRect({
    required this.left,
    required this.top,
    required this.width,
    required this.height,
    required this.pageWidth,
  });

  final double left;
  final double top;
  final double width;
  final double height;
  final double pageWidth;

  Rect get rect => Rect.fromLTWH(left, top, width, height);
}

@immutable
class StPageFlipLayout {
  const StPageFlipLayout({
    required this.orientation,
    required this.bounds,
  });

  final StPageFlipOrientation orientation;
  final StPageFlipBoundsRect bounds;
}

@immutable
class StPageFlipRectPoints {
  const StPageFlipRectPoints({
    required this.topLeft,
    required this.topRight,
    required this.bottomLeft,
    required this.bottomRight,
  });

  final Offset topLeft;
  final Offset topRight;
  final Offset bottomLeft;
  final Offset bottomRight;

  List<Offset> get asList => <Offset>[
    topLeft,
    topRight,
    bottomRight,
    bottomLeft,
  ];
}

@immutable
class StPageFlipSpread {
  const StPageFlipSpread(this.pages);

  final List<int> pages;

  bool get isDoublePage => pages.length == 2;
}

@immutable
class StPageFlipVisibleSpread {
  const StPageFlipVisibleSpread({
    required this.currentPageIndex,
    this.leftPageIndex,
    this.rightPageIndex,
  });

  final int currentPageIndex;
  final int? leftPageIndex;
  final int? rightPageIndex;
}

@immutable
class StPageFlipShadowData {
  const StPageFlipShadowData({
    required this.position,
    required this.angle,
    required this.width,
    required this.opacity,
    required this.direction,
    required this.progress,
  });

  final Offset position;
  final double angle;
  final double width;
  final double opacity;
  final StPageFlipDirection direction;
  final double progress;
}
