import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book/src/contracts/pageflip_book_contracts.dart';

@immutable
class PageflipBookConfig {
  const PageflipBookConfig({
    required this.pageCount,
    this.showCover = false,
    this.initialPage = 0,
    this.portraitDisplayMode = PageflipBookDisplayMode.single,
    this.landscapeDisplayMode = PageflipBookDisplayMode.spread,
    this.enablePageCurl = true,
    this.flippingTimeMs = 1000,
    this.maxShadowOpacity = 1.0,
  }) : assert(pageCount >= 0);

  final int pageCount;
  final bool showCover;
  final int initialPage;
  final PageflipBookDisplayMode portraitDisplayMode;
  final PageflipBookDisplayMode landscapeDisplayMode;
  final bool enablePageCurl;
  final int flippingTimeMs;
  final double maxShadowOpacity;

  PageflipBookDisplayMode displayModeForOrientation(
    PageflipBookOrientation orientation,
  ) {
    return orientation == PageflipBookOrientation.portrait
        ? portraitDisplayMode
        : landscapeDisplayMode;
  }
}
