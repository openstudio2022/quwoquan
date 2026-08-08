import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/design_system/gestures/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/works_article_events.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/works_viewer_article.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_viewer_layout.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer_paging.dart';

/// Typed composition binding for embedding the Post article presentation in
/// the Media work browser without either object importing the other's private
/// presentation tree.
Widget buildWorksViewerArticle({
  required ContentPostViewData post,
  required ContentArticleRender article,
  required String timeLine,
  required ArticlePaperTexture paperTexture,
  required bool enablePageCurl,
  required ValueChanged<int> onPageChanged,
  required ValueChanged<int> onResolvedPageCountChanged,
  required double topChromeSafeInset,
  required bool reserveContentIntersection,
  ValueChanged<String>? onFallbackResolved,
  ValueChanged<WorksArticlePageFlipEvent>? onPageFlipCommitted,
  ValueChanged<WorksArticlePageCurlAbortEvent>? onPageCurlAborted,
  ValueChanged<ArticleInlineSpan>? onEntityTap,
  ImmersiveGestureIntentController? gestureIntentController,
  int initialPage = 0,
  VoidCallback? onOverflowPrevious,
  VoidCallback? onOverflowNext,
}) {
  return PostWorksViewerArticle(
    post: post,
    article: article,
    timeLine: timeLine,
    paperTexture: paperTexture,
    enablePageCurl: enablePageCurl,
    onPageChanged: onPageChanged,
    onResolvedPageCountChanged: onResolvedPageCountChanged,
    topChromeSafeInset: topChromeSafeInset,
    reserveContentIntersection: reserveContentIntersection,
    resolveBottomClearance: (context, includeIntersection) =>
        WorksImmersiveContentLayout.overlayBottomClearance(
          context,
          includeIntersection: includeIntersection,
          gap: AppSpacing.containerMd,
        ),
    resolveMetrics: (context, constraints, topPaperReservedHeight) =>
        resolveImmersiveArticleCanvasMetricsView(
          context,
          constraints,
          topPaperReservedHeight: topPaperReservedHeight,
        ),
    onFallbackResolved: onFallbackResolved,
    onPageFlipCommitted: onPageFlipCommitted,
    onPageCurlAborted: onPageCurlAborted,
    onEntityTap: onEntityTap,
    gestureIntentController: gestureIntentController,
    initialPage: initialPage,
    onOverflowPrevious: onOverflowPrevious,
    onOverflowNext: onOverflowNext,
  );
}
