import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_asset.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/works_article_events.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_paged_canvas.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/hosts/article_reader_host_adapter.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/hosts/immersive_browser_reader_adapter.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/host/article_read_only_book_deck.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/host/article_reader_flip_host.dart';
import 'package:quwoquan_app/design_system/gestures/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

typedef WorksArticleBottomClearanceResolver = double Function(
  BuildContext context,
  bool includeIntersection,
);

typedef WorksArticleMetricsResolver = ArticleCanvasMetricsView Function(
  BuildContext context,
  BoxConstraints constraints,
  double topPaperReservedHeight,
);

/// Composition root for embedding the Post article reader in Media Work Browser.
///
/// The concrete Post presentation adapters remain private to this runtime
/// boundary; Media receives only public article values and runtime-owned events.
final class PostWorksViewerArticle extends StatelessWidget {
  const PostWorksViewerArticle({
    super.key,
    required this.post,
    required this.article,
    required this.timeLine,
    required this.paperTexture,
    required this.enablePageCurl,
    required this.onPageChanged,
    required this.onResolvedPageCountChanged,
    required this.topChromeSafeInset,
    required this.reserveContentIntersection,
    required this.resolveBottomClearance,
    required this.resolveMetrics,
    this.onFallbackResolved,
    this.onPageFlipCommitted,
    this.onPageCurlAborted,
    this.onEntityTap,
    this.onImageTap,
    this.gestureIntentController,
    this.initialPage = 0,
    this.onOverflowPrevious,
    this.onOverflowNext,
  });

  final ContentPostViewData post;
  final ContentArticleRender article;
  final String timeLine;
  final ArticlePaperTexture paperTexture;
  final bool enablePageCurl;
  final ValueChanged<int> onPageChanged;
  final ValueChanged<int> onResolvedPageCountChanged;
  final double topChromeSafeInset;
  final bool reserveContentIntersection;
  final WorksArticleBottomClearanceResolver resolveBottomClearance;
  final WorksArticleMetricsResolver resolveMetrics;
  final ValueChanged<String>? onFallbackResolved;
  final ValueChanged<WorksArticlePageFlipEvent>? onPageFlipCommitted;
  final ValueChanged<WorksArticlePageCurlAbortEvent>? onPageCurlAborted;
  final ValueChanged<ArticleInlineSpan>? onEntityTap;
  final ValueChanged<ArticleDocumentAsset>? onImageTap;
  final ImmersiveGestureIntentController? gestureIntentController;
  final int initialPage;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  Widget build(BuildContext context) {
    final topPaperReservedHeight =
        topChromeSafeInset +
        AppSpacing.appChromeTopBarHeight(context) +
        AppSpacing.intraGroupSm;
    final palette = resolveArticlePaperPalette(context, paperTexture);
    return CupertinoTheme(
      data: CupertinoTheme.of(context).copyWith(brightness: Brightness.dark),
      child: Stack(
        fit: StackFit.expand,
        children: [
          ColoredBox(color: palette.paperColor),
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            bottom: resolveBottomClearance(context, reserveContentIntersection),
            child: LayoutBuilder(
              builder: (context, constraints) {
                // 几何单源（GWT-015）：先解析渲染 metrics，分页消费同一几何。
                // 渲染 pagePadding 为 zero（immersive edge-to-edge），
                // 分页 stage 宽度即内容区全宽，禁止另走 0.72 纸比推导。
                final immersiveMetrics = resolveMetrics(
                  context,
                  constraints,
                  topPaperReservedHeight,
                );
                final pages = resolvePaginatedArticlePages(
                  context: context,
                  constraints: constraints,
                  document: article.document,
                  template: article.template,
                  fontPreset: article.fontPreset,
                  fallbackPages: article.pages,
                  variant: ArticleCanvasVariant.immersive,
                  paperTexture: paperTexture,
                  canvasMetrics: ArticleCanvasMetrics.fromView(
                    immersiveMetrics,
                  ),
                  stageWidth: constraints.maxWidth.isFinite
                      ? constraints.maxWidth
                      : null,
                );
                onResolvedPageCountChanged(pages.length.clamp(1, 99).toInt());
                final maxIndex = pages.isEmpty ? 0 : pages.length - 1;
                final safeInitialPage = pages.isEmpty
                    ? 0
                    : initialPage.clamp(0, maxIndex).toInt();
                return ArticleReaderFlipHost(
                  adapter: ImmersiveBrowserReaderAdapter(
                    ArticleReaderHostConfig(
                      pages: pages,
                      template: article.template,
                      fontPreset: article.fontPreset,
                      metrics: immersiveMetrics,
                      coverUrl: post.primaryImageUrl,
                      initialPage: safeInitialPage,
                      enablePageCurl: enablePageCurl,
                      pagePadding: EdgeInsets.zero,
                      headerLabel: timeLine,
                      showFooterPageLabel: false,
                      paperTexture: paperTexture,
                      presentationStyle:
                          ArticleReadOnlyBookDeckPresentationStyle.immersive,
                      onPageChanged: onPageChanged,
                      onOverflowPrevious: onOverflowPrevious,
                      onOverflowNext: onOverflowNext,
                      onFallbackResolved: (reason) =>
                          onFallbackResolved?.call(_fallbackReasonName(reason)),
                      onPageFlipCommitted: (event) => onPageFlipCommitted?.call(
                        WorksArticlePageFlipEvent(
                          fromPage: event.fromPage,
                          toPage: event.toPage,
                          durationMs: event.durationMs,
                          mechanism: event.mechanism,
                        ),
                      ),
                      onPageCurlAborted: (event) => onPageCurlAborted?.call(
                        WorksArticlePageCurlAbortEvent(
                          corner: event.corner,
                          progress: event.progress,
                          direction: event.direction,
                        ),
                      ),
                      onEntityTap: onEntityTap,
                      onImageTap: onImageTap,
                      gestureIntentController: gestureIntentController,
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  static String _fallbackReasonName(ArticleReaderFallbackReason reason) {
    return switch (reason) {
      ArticleReaderFallbackReason.forcedDegradedPager =>
        'forced_degraded_pager',
      ArticleReaderFallbackReason.pageCurlDisabled => 'page_curl_disabled',
      ArticleReaderFallbackReason.accessibilityDisableAnimations =>
        'accessibility_disable_animations',
      ArticleReaderFallbackReason.longDocument => 'long_document',
    };
  }
}
