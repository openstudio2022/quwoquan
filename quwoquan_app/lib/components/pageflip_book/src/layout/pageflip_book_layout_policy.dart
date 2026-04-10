import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book_config.dart';
import 'package:quwoquan_app/components/pageflip_book/src/contracts/pageflip_book_contracts.dart';

@immutable
class PageflipBookLayoutPolicy {
  const PageflipBookLayoutPolicy();

  PageflipBookOrientation resolveOrientation(Size viewportSize) {
    if (viewportSize.width >= viewportSize.height) {
      return PageflipBookOrientation.landscape;
    }
    return PageflipBookOrientation.portrait;
  }

  PageflipBookDisplayMode resolveDisplayMode({
    required PageflipBookConfig config,
    required PageflipBookOrientation orientation,
  }) {
    final configuredMode = config.displayModeForOrientation(orientation);
    if (configuredMode == PageflipBookDisplayMode.spread &&
        config.pageCount < 2) {
      return PageflipBookDisplayMode.single;
    }
    return configuredMode;
  }
}
