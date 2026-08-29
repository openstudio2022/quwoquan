import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/hosts/article_reader_host_adapter.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/host/article_read_only_book_deck.dart';

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
      metrics: ArticleCanvasMetrics.fromView(config.metrics),
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
      onEntityTap: config.onEntityTap,
      onImageTap: config.onImageTap,
      gestureIntentController: config.gestureIntentController,
      headerLabel: config.headerLabel,
      showFooterPageLabel: config.showFooterPageLabel,
      paperTexture: config.paperTexture,
      presentationStyle: config.presentationStyle,
      debugPageSurfaceBuilder: config.debugPageSurfaceBuilder,
      debugBackPageSurfaceBuilder: config.debugBackPageSurfaceBuilder,
    );
  }
}
