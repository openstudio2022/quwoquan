import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book_config.dart';
import 'package:quwoquan_app/components/pageflip_book/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book/src/layout/pageflip_book_layout_policy.dart';
import 'package:quwoquan_app/components/pageflip_book/src/scene/pageflip_book_scene_contract.dart';
import 'package:quwoquan_app/components/pageflip_book/src/snapshot/pageflip_book_snapshot_contract.dart';

@immutable
class PageflipBookFacade {
  const PageflipBookFacade({
    required this.config,
    this.layoutPolicy = const PageflipBookLayoutPolicy(),
  });

  final PageflipBookConfig config;
  final PageflipBookLayoutPolicy layoutPolicy;

  PageflipBookOrientation resolveOrientation(Size viewportSize) {
    return layoutPolicy.resolveOrientation(viewportSize);
  }

  PageflipBookDisplayMode resolveDisplayModeForViewport(Size viewportSize) {
    final orientation = resolveOrientation(viewportSize);
    return layoutPolicy.resolveDisplayMode(
      config: config,
      orientation: orientation,
    );
  }

  PageflipBookWindow resolveWindow({
    required int currentPageIndex,
    required PageflipBookOrientation orientation,
  }) {
    final displayMode = layoutPolicy.resolveDisplayMode(
      config: config,
      orientation: orientation,
    );
    final safePage = config.pageCount == 0
        ? 0
        : currentPageIndex.clamp(0, config.pageCount - 1).toInt();
    if (config.pageCount == 0) {
      return PageflipBookWindow(
        displayMode: displayMode,
        orientation: orientation,
        currentPageIndex: 0,
      );
    }
    if (displayMode == PageflipBookDisplayMode.single) {
      return PageflipBookWindow(
        displayMode: displayMode,
        orientation: orientation,
        currentPageIndex: safePage,
        rightPageIndex: safePage,
      );
    }

    final spreads = _buildSpreadPages();
    final spread = spreads.firstWhere(
      (candidate) => candidate.contains(safePage),
      orElse: () => spreads.first,
    );
    if (spread.length == 1) {
      final singleIndex = spread.first;
      final isTailPage = singleIndex == config.pageCount - 1;
      return PageflipBookWindow(
        displayMode: displayMode,
        orientation: orientation,
        currentPageIndex: safePage,
        leftPageIndex: isTailPage ? singleIndex : null,
        rightPageIndex: isTailPage ? null : singleIndex,
      );
    }
    return PageflipBookWindow(
      displayMode: displayMode,
      orientation: orientation,
      currentPageIndex: safePage,
      leftPageIndex: spread.first,
      rightPageIndex: spread.last,
    );
  }

  PageflipBookSceneDescriptor resolveScene({
    required int currentPageIndex,
    required PageflipBookOrientation orientation,
    PageflipBookState state = PageflipBookState.read,
    PageflipBookDirection? direction,
    PageflipBookCorner? corner,
    int? turningPageIndex,
    int? coveredPageIndex,
    int? underPageIndex,
  }) {
    final window = resolveWindow(
      currentPageIndex: currentPageIndex,
      orientation: orientation,
    );
    return PageflipBookSceneDescriptor(
      window: window,
      state: state,
      direction: direction,
      corner: corner,
      surfaceBinding: resolveSurfaceBinding(
        window: window,
        direction: direction,
        turningPageIndex: turningPageIndex,
        coveredPageIndex: coveredPageIndex,
        underPageIndex: underPageIndex,
      ),
      sheetBinding: resolveSheetBinding(
        window: window,
        direction: direction,
        turningPageIndex: turningPageIndex,
        coveredPageIndex: coveredPageIndex,
        underPageIndex: underPageIndex,
      ),
    );
  }

  PageflipBookSurfaceRoleBinding? resolveSurfaceBinding({
    required PageflipBookWindow window,
    PageflipBookDirection? direction,
    int? turningPageIndex,
    int? coveredPageIndex,
    int? underPageIndex,
  }) {
    final roles = <PageflipBookSurfaceRole, int>{};

    if (window.leftPageIndex != null) {
      roles[PageflipBookSurfaceRole.staticLeft] = window.leftPageIndex!;
    }
    if (window.rightPageIndex != null) {
      roles[PageflipBookSurfaceRole.staticRight] = window.rightPageIndex!;
    }
    if (direction == null) {
      return roles.isEmpty ? null : PageflipBookSurfaceRoleBinding(roles: roles);
    }

    final resolvedCoveredPageIndex = coveredPageIndex ?? window.currentPageIndex;
    roles[PageflipBookSurfaceRole.coveredCurrent] = resolvedCoveredPageIndex;
    if (turningPageIndex != null) {
      roles[PageflipBookSurfaceRole.turningFront] = turningPageIndex;
      roles[PageflipBookSurfaceRole.turningBack] =
          direction == PageflipBookDirection.forward
          ? (underPageIndex ?? turningPageIndex)
          : resolvedCoveredPageIndex;
    }
    if (direction == PageflipBookDirection.forward && underPageIndex != null) {
      roles[PageflipBookSurfaceRole.nextUnder] = underPageIndex;
    } else if (direction == PageflipBookDirection.backward) {
      roles[PageflipBookSurfaceRole.nextUnder] = resolvedCoveredPageIndex;
    }
    return roles.isEmpty ? null : PageflipBookSurfaceRoleBinding(roles: roles);
  }

  PageflipBookSheetBinding? resolveSheetBinding({
    required PageflipBookWindow window,
    PageflipBookDirection? direction,
    int? turningPageIndex,
    int? coveredPageIndex,
    int? underPageIndex,
  }) {
    if (direction == null || turningPageIndex == null) {
      return null;
    }
    if (direction == PageflipBookDirection.forward) {
      final bottomPageIndex = underPageIndex;
      if (bottomPageIndex == null) {
        return null;
      }
      return PageflipBookSheetBinding(
        direction: direction,
        rectoPageIndex: turningPageIndex,
        versoPageIndex: bottomPageIndex,
        bottomPageIndex: bottomPageIndex,
      );
    }
    final resolvedCoveredPageIndex = coveredPageIndex ?? window.currentPageIndex;
    return PageflipBookSheetBinding(
      direction: direction,
      rectoPageIndex: turningPageIndex,
      versoPageIndex: resolvedCoveredPageIndex,
      bottomPageIndex: resolvedCoveredPageIndex,
    );
  }

  PageflipBookTextureSessionContract createTextureSession({
    required PageflipBookSurfaceRoleBinding binding,
    PageflipBookSheetBinding? sheetBinding,
    bool preferHighFidelity = false,
  }) {
    return PageflipBookTextureSessionContract(
      binding: binding,
      sheetBinding: sheetBinding,
      preferHighFidelity: preferHighFidelity,
    );
  }

  List<List<int>> _buildSpreadPages() {
    if (config.pageCount == 0) {
      return const <List<int>>[];
    }
    final spreads = <List<int>>[];
    var start = 0;
    if (config.showCover) {
      spreads.add(const <int>[0]);
      start = 1;
    }
    for (var index = start; index < config.pageCount; index += 2) {
      if (index < config.pageCount - 1) {
        spreads.add(<int>[index, index + 1]);
      } else {
        spreads.add(<int>[index]);
      }
    }
    return List<List<int>>.unmodifiable(spreads);
  }
}
