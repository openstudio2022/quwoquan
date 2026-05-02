import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/hosts/article_reader_host_adapter.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart';

class ArticleReaderFlipHost extends StatelessWidget {
  const ArticleReaderFlipHost({super.key, required this.adapter});

  final ArticleReaderHostAdapter adapter;

  @override
  Widget build(BuildContext context) {
    final config = adapter.resolveReaderConfig(context);
    return ArticleReadOnlyBookDeck(
      pages: config.pages,
      template: config.template,
      fontPreset: config.fontPreset,
      metrics: config.metrics,
      coverUrl: config.coverUrl,
      initialPage: config.initialPage,
      pagePadding: config.pagePadding,
      enablePageCurl: config.enablePageCurl,
      forceDegradedPager: config.forceDegradedPager,
      onPageChanged: config.onPageChanged,
      onOverflowPrevious: config.onOverflowPrevious,
      onOverflowNext: config.onOverflowNext,
      onFallbackResolved: config.onFallbackResolved,
      onPageFlipCommitted: config.onPageFlipCommitted,
      onPageCurlAborted: config.onPageCurlAborted,
      onSceneChanged: config.onSceneChanged,
      onDebugStateChanged: config.onDebugStateChanged,
      showFooterPageLabel: config.showFooterPageLabel,
      paperTexture: config.paperTexture,
      debugPageSurfaceBuilder: config.debugPageSurfaceBuilder,
      debugBackPageSurfaceBuilder: config.debugBackPageSurfaceBuilder,
    );
  }
}
