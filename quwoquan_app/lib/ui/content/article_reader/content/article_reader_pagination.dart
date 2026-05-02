import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_flow_layout_engine.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_theme.dart';

List<ArticlePageData> resolvePaginatedArticlePages({
  required BuildContext context,
  required BoxConstraints constraints,
  required ArticleDocumentData document,
  required ArticleTemplatePreset template,
  required ArticleFontPreset fontPreset,
  List<ArticlePageData> fallbackPages = const <ArticlePageData>[],
  ArticleCanvasVariant variant = ArticleCanvasVariant.preview,
  double? contentHeightOverride,
  ArticlePaperTexture? paperTexture,
}) {
  final visibleTitle = document.titleStyle == ArticleDocumentTitleStyle.none
      ? ''
      : document.title.trim();
  if (visibleTitle.isEmpty &&
      document.body.trim().isEmpty &&
      document.assets.isEmpty &&
      fallbackPages.isNotEmpty) {
    return fallbackPages;
  }
  final preferStructuredFallbackPages = fallbackPages
      .skip(1)
      .any(
        (page) => page.title.trim().isNotEmpty || page.body.trim().isNotEmpty,
      );
  if (preferStructuredFallbackPages) {
    return fallbackPages;
  }
  final metrics = resolveArticleCanvasMetrics(
    context,
    constraints,
    variant: variant,
  );
  final typography = paperTexture != null
      ? resolveArticleTypographyForPaper(context, paperTexture, fontPreset)
      : resolveArticleTypography(context, template, fontPreset);
  final stagePadding = articleReaderStagePagePadding();
  final stageWidth = resolveArticlePaperStageWidth(
    context,
    constraints,
    stagePadding: stagePadding,
    allowLandscapeSpread: variant != ArticleCanvasVariant.editor,
  );
  final viewportSliceHeight =
      contentHeightOverride ??
      metrics.contentSizeForStageWidth(stageWidth).height;
  final pages = ArticleFlowLayoutEngine.buildPageSlicesForViewport(
    document: document,
    metrics: metrics,
    stageWidth: stageWidth,
    titleStyle: typography.titleStyle,
    bodyStyle: typography.bodyStyle,
    viewportSliceHeight: viewportSliceHeight,
  );
  if (pages.isNotEmpty) {
    return pages;
  }
  return fallbackPages;
}
