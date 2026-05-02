import 'package:quwoquan_app/ui/content/article_reader/pageflip/modes/article_reader_mode_strategy.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';

class SinglePageModeStrategy extends ArticleReaderModeStrategy {
  const SinglePageModeStrategy();

  @override
  ArticleReaderFlipMode get mode => ArticleReaderFlipMode.singlePage;

  @override
  ArticleReaderModeLayout resolveLayout({
    required StPageFlipScene scene,
    required Set<int> dynamicallyRenderedPages,
  }) {
    final currentPageIndex = scene.currentPageIndex;
    return ArticleReaderModeLayout(
      mode: mode,
      layout: scene.layout,
      pageRect: resolveArticleReaderScenePageRect(scene),
      staticSuppressionPages: dynamicallyRenderedPages,
      rolePolicy: ArticleReaderPageRolePolicy.singleVisiblePage,
      windowPolicy: ArticleReaderPageWindowPolicy.currentWithAdjacentPages,
      staticSuppressionPolicy:
          ArticleReaderStaticSuppressionPolicy.dynamicallyRenderedPages,
      windowPageIndices: <int>{
        currentPageIndex - 1,
        currentPageIndex,
        currentPageIndex + 1,
      },
    );
  }
}
