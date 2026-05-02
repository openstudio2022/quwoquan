import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart';

@immutable
class ArticleReaderHostConfig {
  const ArticleReaderHostConfig({
    required this.pages,
    required this.template,
    required this.fontPreset,
    required this.metrics,
    required this.initialPage,
    required this.coverUrl,
    this.pagePadding = EdgeInsets.zero,
    this.enablePageCurl = true,
    this.forceDegradedPager = false,
    this.showFooterPageLabel = true,
    this.paperTexture,
    this.onPageChanged,
    this.onOverflowPrevious,
    this.onOverflowNext,
    this.onFallbackResolved,
    this.onPageFlipCommitted,
    this.onPageCurlAborted,
    this.onSceneChanged,
    this.onDebugStateChanged,
    this.debugPageSurfaceBuilder,
    this.debugBackPageSurfaceBuilder,
  });

  final List<ArticlePageData> pages;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final ArticleCanvasMetrics metrics;
  final int initialPage;
  final String coverUrl;
  final EdgeInsets pagePadding;
  final bool enablePageCurl;
  final bool forceDegradedPager;
  final bool showFooterPageLabel;
  final ArticlePaperTexture? paperTexture;
  final ValueChanged<int>? onPageChanged;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;
  final ValueChanged<ArticleReaderFallbackReason>? onFallbackResolved;
  final ValueChanged<ArticleReaderPageFlipCommit>? onPageFlipCommitted;
  final ValueChanged<ArticleReaderPageCurlAbort>? onPageCurlAborted;
  final ValueChanged<StPageFlipScene>? onSceneChanged;
  final ValueChanged<ArticleReadOnlyBookDebugState>? onDebugStateChanged;
  final Widget Function(BuildContext context, int pageIndex, Size pageSize)?
  debugPageSurfaceBuilder;
  final Widget Function(BuildContext context, int pageIndex, Size pageSize)?
  debugBackPageSurfaceBuilder;
}

abstract class ArticleReaderHostAdapter {
  const ArticleReaderHostAdapter();

  ArticleReaderHostConfig resolveReaderConfig(BuildContext context);
}
