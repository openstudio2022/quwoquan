import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class PageTouchStateV2 {
  const PageTouchStateV2({
    required this.stagePoint,
    required this.bookPoint,
    required this.workingPagePoint,
    required this.direction,
    required this.corner,
  });

  factory PageTouchStateV2.fromStagePoint({
    required Offset stagePoint,
    required StPageFlipBoundsRect bounds,
    required PageflipBookIsolatedDirection direction,
    required PageflipBookIsolatedCorner corner,
  }) {
    final legacyDirection = direction.isForward
        ? StPageFlipDirection.forward
        : StPageFlipDirection.back;
    return PageTouchStateV2(
      stagePoint: stagePoint,
      bookPoint: convertViewportPointToBook(stagePoint, bounds),
      workingPagePoint: convertViewportPointToPage(
        stagePoint,
        bounds,
        direction: legacyDirection,
      ),
      direction: direction,
      corner: corner,
    );
  }

  factory PageTouchStateV2.fromWorkingPagePoint({
    required Offset workingPagePoint,
    required StPageFlipBoundsRect bounds,
    required PageflipBookIsolatedDirection direction,
    required PageflipBookIsolatedCorner corner,
  }) {
    final bookX = direction.isForward
        ? workingPagePoint.dx + bounds.pageWidth
        : bounds.width - workingPagePoint.dx;
    final bookPoint = Offset(bookX, workingPagePoint.dy);
    final stagePoint = Offset(
      bookPoint.dx + bounds.left,
      bookPoint.dy + bounds.top,
    );
    return PageTouchStateV2(
      stagePoint: stagePoint,
      bookPoint: bookPoint,
      workingPagePoint: workingPagePoint,
      direction: direction,
      corner: corner,
    );
  }

  final Offset stagePoint;
  final Offset bookPoint;
  final Offset workingPagePoint;
  final PageflipBookIsolatedDirection direction;
  final PageflipBookIsolatedCorner corner;

  PageTouchStateV2 copyWith({
    Offset? stagePoint,
    Offset? bookPoint,
    Offset? workingPagePoint,
    PageflipBookIsolatedDirection? direction,
    PageflipBookIsolatedCorner? corner,
  }) {
    return PageTouchStateV2(
      stagePoint: stagePoint ?? this.stagePoint,
      bookPoint: bookPoint ?? this.bookPoint,
      workingPagePoint: workingPagePoint ?? this.workingPagePoint,
      direction: direction ?? this.direction,
      corner: corner ?? this.corner,
    );
  }
}
