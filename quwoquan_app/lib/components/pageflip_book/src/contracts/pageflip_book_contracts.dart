import 'package:flutter/foundation.dart';

enum PageflipBookDisplayMode { single, spread }

enum PageflipBookOrientation { portrait, landscape }

enum PageflipBookDirection { forward, backward }

enum PageflipBookCorner { top, bottom }

enum PageflipBookState { read, foldCorner, userFold, flipping }

@immutable
class PageflipBookWindow {
  const PageflipBookWindow({
    required this.displayMode,
    required this.orientation,
    required this.currentPageIndex,
    this.leftPageIndex,
    this.rightPageIndex,
  });

  final PageflipBookDisplayMode displayMode;
  final PageflipBookOrientation orientation;
  final int currentPageIndex;
  final int? leftPageIndex;
  final int? rightPageIndex;

  bool get isSpread => displayMode == PageflipBookDisplayMode.spread;

  List<int> get visiblePageIndices {
    final indices = <int>[];

    void addUnique(int? index) {
      if (index == null || indices.contains(index)) {
        return;
      }
      indices.add(index);
    }

    addUnique(leftPageIndex);
    addUnique(rightPageIndex);
    if (indices.isEmpty) {
      addUnique(currentPageIndex);
    }
    return List<int>.unmodifiable(indices);
  }
}
