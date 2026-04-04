import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class StPageFlipSpreadModel {
  StPageFlipSpreadModel({
    required this.pageCount,
    this.showCover = false,
  }) : assert(pageCount >= 0),
       _portraitSpread = List<StPageFlipSpread>.generate(
         pageCount,
         (int index) => StPageFlipSpread(<int>[index]),
         growable: false,
       ),
       _landscapeSpread = _buildLandscapeSpread(pageCount, showCover),
       _hardPages = _buildHardPages(pageCount, showCover);

  final int pageCount;
  final bool showCover;
  final List<StPageFlipSpread> _portraitSpread;
  final List<StPageFlipSpread> _landscapeSpread;
  final Set<int> _hardPages;

  List<StPageFlipSpread> spreadsFor(StPageFlipOrientation orientation) {
    return orientation == StPageFlipOrientation.landscape
        ? _landscapeSpread
        : _portraitSpread;
  }

  int spreadCountFor(StPageFlipOrientation orientation) {
    return spreadsFor(orientation).length;
  }

  int? getSpreadIndexByPage(
    int pageIndex,
    StPageFlipOrientation orientation,
  ) {
    final spreads = spreadsFor(orientation);
    for (var index = 0; index < spreads.length; index += 1) {
      final spread = spreads[index];
      if (spread.pages.contains(pageIndex)) {
        return index;
      }
    }
    return null;
  }

  StPageFlipVisibleSpread visibleSpreadForIndex(
    int spreadIndex,
    StPageFlipOrientation orientation,
  ) {
    final spreads = spreadsFor(orientation);
    if (spreads.isEmpty) {
      return const StPageFlipVisibleSpread(currentPageIndex: 0);
    }
    final safeIndex = spreadIndex.clamp(0, spreads.length - 1).toInt();
    final spread = spreads[safeIndex];
    if (spread.pages.length == 2) {
      return StPageFlipVisibleSpread(
        currentPageIndex: spread.pages.first,
        leftPageIndex: spread.pages.first,
        rightPageIndex: spread.pages.last,
      );
    }
    final singleIndex = spread.pages.first;
    if (orientation == StPageFlipOrientation.landscape) {
      if (singleIndex == pageCount - 1) {
        return StPageFlipVisibleSpread(
          currentPageIndex: singleIndex,
          leftPageIndex: singleIndex,
        );
      }
      return StPageFlipVisibleSpread(
        currentPageIndex: singleIndex,
        rightPageIndex: singleIndex,
      );
    }
    return StPageFlipVisibleSpread(
      currentPageIndex: singleIndex,
      rightPageIndex: singleIndex,
    );
  }

  int? getFlippingPageIndex({
    required StPageFlipDirection direction,
    required int currentSpreadIndex,
    required StPageFlipOrientation orientation,
  }) {
    if (pageCount == 0) {
      return null;
    }
    if (orientation == StPageFlipOrientation.portrait) {
      return direction == StPageFlipDirection.forward
          ? currentSpreadIndex.clamp(0, pageCount - 1).toInt()
          : (currentSpreadIndex - 1 >= 0 ? currentSpreadIndex - 1 : null);
    }

    final spreads = spreadsFor(orientation);
    final targetSpreadIndex = direction == StPageFlipDirection.forward
        ? currentSpreadIndex + 1
        : currentSpreadIndex - 1;
    if (targetSpreadIndex < 0 || targetSpreadIndex >= spreads.length) {
      return null;
    }
    final spread = spreads[targetSpreadIndex];
    if (spread.pages.length == 1) {
      return spread.pages.first;
    }
    return direction == StPageFlipDirection.forward
        ? spread.pages.first
        : spread.pages.last;
  }

  int? getBottomPageIndex({
    required StPageFlipDirection direction,
    required int currentSpreadIndex,
    required StPageFlipOrientation orientation,
  }) {
    if (pageCount == 0) {
      return null;
    }
    if (orientation == StPageFlipOrientation.portrait) {
      if (direction == StPageFlipDirection.forward) {
        final target = currentSpreadIndex + 1;
        return target >= 0 && target < pageCount ? target : null;
      }
      // 回翻时「底页」必须是当前正在阅读的这一页（卷曲下的那一面），
      // 不能与 flippingPage（即将露出的上一页）相同；此前误用 spreadIndex-1 导致双层同页、观感像闪切。
      return currentSpreadIndex >= 0 && currentSpreadIndex < pageCount
          ? currentSpreadIndex
          : null;
    }

    // 横屏回翻：底页为当前对开里仍在正面的那一页（通常右页），不能指向目标 spread。
    if (direction == StPageFlipDirection.back) {
      final vis = visibleSpreadForIndex(currentSpreadIndex, orientation);
      return vis.rightPageIndex ?? vis.leftPageIndex;
    }

    final spreads = spreadsFor(orientation);
    final targetSpreadIndex = currentSpreadIndex + 1;
    if (targetSpreadIndex < 0 || targetSpreadIndex >= spreads.length) {
      return null;
    }
    final spread = spreads[targetSpreadIndex];
    if (spread.pages.length == 1) {
      return spread.pages.first;
    }
    return spread.pages.last;
  }

  bool usesTemporaryCopyForFlipping({
    required StPageFlipDirection direction,
    required StPageFlipOrientation orientation,
  }) {
    return orientation == StPageFlipOrientation.portrait &&
        direction == StPageFlipDirection.forward;
  }

  StPageFlipDensity densityForPage(int index) {
    return _hardPages.contains(index)
        ? StPageFlipDensity.hard
        : StPageFlipDensity.soft;
  }

  static List<StPageFlipSpread> _buildLandscapeSpread(
    int pageCount,
    bool showCover,
  ) {
    final spreads = <StPageFlipSpread>[];
    var start = 0;
    if (pageCount == 0) {
      return spreads;
    }
    if (showCover) {
      spreads.add(const StPageFlipSpread(<int>[0]));
      start = 1;
    }
    for (var index = start; index < pageCount; index += 2) {
      if (index < pageCount - 1) {
        spreads.add(StPageFlipSpread(<int>[index, index + 1]));
      } else {
        spreads.add(StPageFlipSpread(<int>[index]));
      }
    }
    return List<StPageFlipSpread>.unmodifiable(spreads);
  }

  static Set<int> _buildHardPages(int pageCount, bool showCover) {
    final hardPages = <int>{};
    if (pageCount == 0) {
      return hardPages;
    }
    if (showCover) {
      hardPages.add(0);
    }
    final landscapeSpread = _buildLandscapeSpread(pageCount, showCover);
    if (landscapeSpread.isNotEmpty && landscapeSpread.last.pages.length == 1) {
      hardPages.add(landscapeSpread.last.pages.first);
    }
    return hardPages;
  }
}
