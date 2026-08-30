import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_flow_layout_engine.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/templates/article_reader_template_theme.dart';

/// [canvasMetrics] / [stageWidth]：宿主已解析的画布几何单源（GWT-015）。
/// 沉浸阅读等「渲染几何 != 0.72 纸比」的宿主必须传入渲染消费的同一几何，
/// 分页不得在此再造第二套纸比或 stage 宽度。缺席时按 variant 自行解析
/// （预览/编辑器等纸比场景）。
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
  ArticleCanvasMetrics? canvasMetrics,
  double? stageWidth,
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
  final documentHasImages = document.assets.any((asset) => asset.hasImage);
  final preferStructuredFallbackPages =
      !documentHasImages &&
      fallbackPages
          .skip(1)
          .any(
            (page) =>
                page.title.trim().isNotEmpty || page.body.trim().isNotEmpty,
          );
  if (preferStructuredFallbackPages) {
    return fallbackPages;
  }
  final metrics =
      canvasMetrics ??
      resolveArticleCanvasMetrics(context, constraints, variant: variant);
  final typography = paperTexture != null
      ? resolveArticleTypographyForPaper(context, paperTexture, fontPreset)
      : resolveArticleTypography(context, template, fontPreset);
  final resolvedStageWidth =
      stageWidth ??
      resolveArticlePaperStageWidth(
        context,
        constraints,
        stagePadding: articleReaderStagePagePadding(),
        allowLandscapeSpread: variant != ArticleCanvasVariant.editor,
      );
  final viewportSliceHeight =
      contentHeightOverride ??
      metrics.contentSizeForStageWidth(resolvedStageWidth).height;
  final pages = ArticleFlowLayoutEngine.buildPageSlicesForViewport(
    document: document,
    metrics: metrics,
    stageWidth: resolvedStageWidth,
    titleStyle: typography.titleStyle,
    bodyStyle: typography.bodyStyle,
    viewportSliceHeight: viewportSliceHeight,
  );
  if (pages.isNotEmpty) {
    return pages;
  }
  return fallbackPages;
}
