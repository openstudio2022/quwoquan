import 'package:quwoquan_app/ui/content/article_reader/pageflip/modes/article_reader_mode_strategy.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';

class SpreadDoublePageModeStrategy extends ArticleReaderModeStrategy {
  const SpreadDoublePageModeStrategy();

  @override
  ArticleReaderFlipMode get mode => ArticleReaderFlipMode.spreadDoublePage;

  @override
  ArticleReaderModeLayout resolveLayout({
    required StPageFlipScene scene,
    required Set<int> dynamicallyRenderedPages,
  }) {
    // Reserved for the future two-page spread rollout. Keeping this strategy
    // explicit prevents spread-specific role/window rules from leaking into
    // forward and backward pipelines.
    return ArticleReaderModeLayout(
      mode: mode,
      layout: scene.layout,
      pageRect: resolveArticleReaderScenePageRect(scene),
      staticSuppressionPages: dynamicallyRenderedPages,
      rolePolicy: ArticleReaderPageRolePolicy.futureSpreadPair,
      windowPolicy: ArticleReaderPageWindowPolicy.futureSpreadWindow,
      staticSuppressionPolicy:
          ArticleReaderStaticSuppressionPolicy.dynamicallyRenderedPages,
      windowPageIndices: <int>{
        if (scene.visibleSpread.leftPageIndex != null)
          scene.visibleSpread.leftPageIndex!,
        if (scene.visibleSpread.rightPageIndex != null)
          scene.visibleSpread.rightPageIndex!,
      },
    );
  }
}
