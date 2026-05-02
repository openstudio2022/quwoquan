import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

enum ArticleReaderFlipMode { singlePage, spreadDoublePage }

enum ArticleReaderPageRolePolicy { singleVisiblePage, futureSpreadPair }

enum ArticleReaderPageWindowPolicy {
  currentWithAdjacentPages,
  futureSpreadWindow,
}

enum ArticleReaderStaticSuppressionPolicy { dynamicallyRenderedPages }

@immutable
class ArticleReaderModeLayout {
  const ArticleReaderModeLayout({
    required this.mode,
    required this.layout,
    required this.pageRect,
    required this.staticSuppressionPages,
    required this.rolePolicy,
    required this.windowPolicy,
    required this.staticSuppressionPolicy,
    required this.windowPageIndices,
  });

  final ArticleReaderFlipMode mode;
  final StPageFlipLayout layout;
  final Rect pageRect;
  final Set<int> staticSuppressionPages;
  final ArticleReaderPageRolePolicy rolePolicy;
  final ArticleReaderPageWindowPolicy windowPolicy;
  final ArticleReaderStaticSuppressionPolicy staticSuppressionPolicy;
  final Set<int> windowPageIndices;
}

abstract class ArticleReaderModeStrategy {
  const ArticleReaderModeStrategy();

  ArticleReaderFlipMode get mode;

  ArticleReaderModeLayout resolveLayout({
    required StPageFlipScene scene,
    required Set<int> dynamicallyRenderedPages,
  });
}

Rect resolveArticleReaderScenePageRect(StPageFlipScene scene) {
  return resolveBookPageRect(scene.layout, isRightPage: true);
}
