import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_mode.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_state.dart';

abstract class PageflipRoleResolver {
  const PageflipRoleResolver();

  PageflipRoleState resolve({
    required PageflipMode mode,
    required PageflipDirection direction,
    required int currentPageIndex,
    required int pageCount,
  });
}

@immutable
class PageflipSinglePageRoleResolver extends PageflipRoleResolver {
  const PageflipSinglePageRoleResolver();

  @override
  PageflipRoleState resolve({
    required PageflipMode mode,
    required PageflipDirection direction,
    required int currentPageIndex,
    required int pageCount,
  }) {
    final safeCurrent = pageCount == 0
        ? 0
        : currentPageIndex.clamp(0, pageCount - 1).toInt();
    if (pageCount == 0) {
      return const PageflipRoleState(
        currentPageIndex: 0,
        turningPageIndex: 0,
      );
    }

    if (mode == PageflipMode.spread) {
      final leftPageIndex = safeCurrent.isEven ? safeCurrent : safeCurrent - 1;
      final rightPageIndex = (leftPageIndex + 1).clamp(0, pageCount - 1).toInt();
      return PageflipRoleState(
        currentPageIndex: safeCurrent,
        turningPageIndex: safeCurrent,
        underlayPageIndex: direction == PageflipDirection.forward
            ? (safeCurrent + 1).clamp(0, pageCount - 1).toInt()
            : (safeCurrent - 1).clamp(0, pageCount - 1).toInt(),
        coveredPageIndex: safeCurrent,
        leftPageIndex: leftPageIndex,
        rightPageIndex: rightPageIndex,
      );
    }

    final underlayPageIndex = direction == PageflipDirection.forward
        ? (safeCurrent + 1).clamp(0, pageCount - 1).toInt()
        : (safeCurrent - 1).clamp(0, pageCount - 1).toInt();
    return PageflipRoleState(
      currentPageIndex: safeCurrent,
      turningPageIndex: safeCurrent,
      underlayPageIndex: underlayPageIndex,
      coveredPageIndex: safeCurrent,
    );
  }
}
