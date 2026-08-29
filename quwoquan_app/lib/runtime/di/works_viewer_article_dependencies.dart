import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/gestures/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_asset.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/works_article_events.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/works_viewer_article.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_canvas.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_viewer_layout.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer_paging.dart';

const ValueKey<String> worksArticleImageViewerSurfaceKey = ValueKey<String>(
  'works-article-image-viewer-surface',
);
const ValueKey<String> worksArticleImageViewerCloseKey = ValueKey<String>(
  'works-article-image-viewer-close',
);

/// 文章正文只上报 typed 图片意图；跨 Post/Media 的具体全屏组装仅存在于 runtime/di。
Future<bool> presentWorksArticleImageViewer({
  required BuildContext context,
  required ArticleDocumentData document,
  required ArticleDocumentAsset initialAsset,
  ValueChanged<String>? onOpened,
  ValueChanged<String>? onClosed,
  ValueChanged<ImageBookMediaLoadEvent>? onMediaLoad,
}) async {
  if (!initialAsset.hasImage) {
    return false;
  }
  final articleAssets = document.assets;
  final initialIndex = articleAssets.indexWhere(
    (asset) => asset.id == initialAsset.id,
  );
  if (initialIndex < 0) {
    return false;
  }

  var currentIndex = initialIndex;
  onOpened?.call(articleAssets[currentIndex].id);
  await showAppFloatingModal<void>(
    context: context,
    barrierDismissible: false,
    builder: (modalContext) {
      return ColoredBox(
        key: worksArticleImageViewerSurfaceKey,
        color: AppColors.worksBackground,
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            ImageBookCanvas(
              // 交付形态取自 articleAssetManifest 的逐项声明（DEC-033）：
              // 私有资产没有公开 URL，绑定必须带资产身份，否则全屏图书在
              // research 相位整本打不开。不从 URL 形态反推。
              deliveries: articleAssets
                  .map(
                    (asset) => MediaDeliveryBinding(
                      assetId: asset.id.trim(),
                      accessMode: articleAssetAccessMode(asset.accessMode),
                      publicUrl: asset.imageUrl.trim(),
                    ),
                  )
                  .toList(growable: false),
              initialIndex: initialIndex,
              onImageChanged: (index) => currentIndex = index,
              onMediaLoad: onMediaLoad,
            ),
            SafeArea(
              child: Align(
                alignment: Alignment.topLeft,
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.containerMd),
                  child: AppNavigationBarIconButton(
                    key: worksArticleImageViewerCloseKey,
                    icon: CupertinoIcons.chevron_left,
                    surface: AppChromeSurface.immersive,
                    onPressed: () => Navigator.of(modalContext).pop(),
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    },
  );
  onClosed?.call(articleAssets[currentIndex].id);
  return true;
}

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
  ValueChanged<ArticleDocumentAsset>? onImageTap,
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
    onImageTap: onImageTap,
    gestureIntentController: gestureIntentController,
    initialPage: initialPage,
    onOverflowPrevious: onOverflowPrevious,
    onOverflowNext: onOverflowNext,
  );
}
