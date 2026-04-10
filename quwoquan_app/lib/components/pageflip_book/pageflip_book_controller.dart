import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book_config.dart';
import 'package:quwoquan_app/components/pageflip_book/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book/src/core/pageflip_book_facade.dart';
import 'package:quwoquan_app/components/pageflip_book/src/layout/pageflip_book_layout_policy.dart';
import 'package:quwoquan_app/components/pageflip_book/src/scene/pageflip_book_scene_contract.dart';
import 'package:quwoquan_app/components/pageflip_book/src/snapshot/pageflip_book_snapshot_contract.dart';

@immutable
class PageflipBookController {
  const PageflipBookController({
    required this.config,
    this.layoutPolicy = const PageflipBookLayoutPolicy(),
  });

  final PageflipBookConfig config;
  final PageflipBookLayoutPolicy layoutPolicy;

  PageflipBookFacade get _facade =>
      PageflipBookFacade(config: config, layoutPolicy: layoutPolicy);

  PageflipBookOrientation resolveOrientation(Size viewportSize) {
    return _facade.resolveOrientation(viewportSize);
  }

  PageflipBookDisplayMode resolveDisplayMode(Size viewportSize) {
    return _facade.resolveDisplayModeForViewport(viewportSize);
  }

  bool resolvesToSinglePortrait(Size viewportSize) {
    return resolveOrientation(viewportSize) ==
            PageflipBookOrientation.portrait &&
        resolveDisplayMode(viewportSize) == PageflipBookDisplayMode.single;
  }

  PageflipBookWindow resolveWindow({
    required int currentPageIndex,
    required Size viewportSize,
  }) {
    return _facade.resolveWindow(
      currentPageIndex: currentPageIndex,
      orientation: resolveOrientation(viewportSize),
    );
  }

  PageflipBookSceneDescriptor resolveScene({
    required int currentPageIndex,
    required Size viewportSize,
    PageflipBookState state = PageflipBookState.read,
    PageflipBookDirection? direction,
    PageflipBookCorner? corner,
    int? turningPageIndex,
    int? coveredPageIndex,
    int? underPageIndex,
  }) {
    return _facade.resolveScene(
      currentPageIndex: currentPageIndex,
      orientation: resolveOrientation(viewportSize),
      state: state,
      direction: direction,
      corner: corner,
      turningPageIndex: turningPageIndex,
      coveredPageIndex: coveredPageIndex,
      underPageIndex: underPageIndex,
    );
  }

  PageflipBookTextureSessionContract createTextureSession({
    required PageflipBookSurfaceRoleBinding binding,
    PageflipBookSheetBinding? sheetBinding,
    bool preferHighFidelity = false,
  }) {
    return _facade.createTextureSession(
      binding: binding,
      sheetBinding: sheetBinding,
      preferHighFidelity: preferHighFidelity,
    );
  }
}
