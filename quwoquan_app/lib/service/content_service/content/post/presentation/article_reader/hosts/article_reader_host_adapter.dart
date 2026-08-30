import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_asset.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/design_system/pageflip/controller.dart';
import 'package:quwoquan_app/design_system/gestures/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/host/article_read_only_book_deck.dart';

@immutable
class ArticleReaderHostConfig {
  const ArticleReaderHostConfig({
    required this.pages,
    required this.template,
    required this.fontPreset,
    required this.metrics,
    required this.initialPage,
    required this.coverUrl,
    required this.enablePageCurl,
    this.pagePadding = EdgeInsets.zero,
    this.forceDegradedPager = false,
    this.headerLabel,
    this.showFooterPageLabel = true,
    this.paperTexture,
    this.presentationStyle = ArticleReadOnlyBookDeckPresentationStyle.book,
    this.onPageChanged,
    this.onOverflowPrevious,
    this.onOverflowNext,
    this.onFallbackResolved,
    this.onPageFlipCommitted,
    this.onPageCurlAborted,
    this.onSceneChanged,
    this.onDebugStateChanged,
    this.onEntityTap,
    this.onImageTap,
    this.gestureIntentController,
    this.debugPageSurfaceBuilder,
    this.debugBackPageSurfaceBuilder,
  });

  final List<ArticlePageData> pages;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final ArticleCanvasMetricsView metrics;
  final int initialPage;
  final String coverUrl;
  final EdgeInsets pagePadding;
  final bool enablePageCurl;
  final bool forceDegradedPager;
  final String? headerLabel;
  final bool showFooterPageLabel;
  final ArticlePaperTexture? paperTexture;
  final ArticleReadOnlyBookDeckPresentationStyle presentationStyle;
  final ValueChanged<int>? onPageChanged;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;
  final ValueChanged<ArticleReaderFallbackReason>? onFallbackResolved;
  final ValueChanged<ArticleReaderPageFlipCommit>? onPageFlipCommitted;
  final ValueChanged<ArticleReaderPageCurlAbort>? onPageCurlAborted;
  final ValueChanged<StPageFlipScene>? onSceneChanged;
  final ValueChanged<ArticleReadOnlyBookDebugState>? onDebugStateChanged;
  final ValueChanged<ArticleInlineSpan>? onEntityTap;
  final ValueChanged<ArticleDocumentAsset>? onImageTap;
  final ImmersiveGestureIntentController? gestureIntentController;
  final Widget Function(BuildContext context, int pageIndex, Size pageSize)?
  debugPageSurfaceBuilder;
  final Widget Function(BuildContext context, int pageIndex, Size pageSize)?
  debugBackPageSurfaceBuilder;
}

abstract class ArticleReaderHostAdapter {
  const ArticleReaderHostAdapter();

  ArticleReaderHostConfig resolveReaderConfig(BuildContext context);
}
