import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

class ImmersiveViewerStageLayoutSpec {
  const ImmersiveViewerStageLayoutSpec({
    required this.horizontalInset,
    this.maxContentWidth,
  });

  static const ImmersiveViewerStageLayoutSpec feedRail =
      ImmersiveViewerStageLayoutSpec(
        horizontalInset: AppSpacing.containerMd,
        maxContentWidth: AppSpacing.feedMaxContentWidth,
      );

  /// 图片/视频沉浸阶段：与媒体左右边界对齐，不收窄到 feedMaxContentWidth。
  static const ImmersiveViewerStageLayoutSpec mediaStage =
      ImmersiveViewerStageLayoutSpec(horizontalInset: AppSpacing.containerMd);

  /// 文章沉浸阶段：与正文 contentPadding 同源（containerLg）。
  static const ImmersiveViewerStageLayoutSpec articleStage =
      ImmersiveViewerStageLayoutSpec(horizontalInset: AppSpacing.containerLg);

  static const ImmersiveViewerStageLayoutSpec textStage =
      ImmersiveViewerStageLayoutSpec(
        horizontalInset: AppSpacing.containerMd,
        maxContentWidth: AppSpacing.feedMaxContentWidth,
      );

  final double horizontalInset;
  final double? maxContentWidth;

  double railWidthForViewport(double viewportWidth) {
    final availableWidth = math.max(0.0, viewportWidth - (horizontalInset * 2));
    final constrainedMaxWidth = maxContentWidth;
    if (constrainedMaxWidth == null) {
      return availableWidth;
    }
    return math.min(availableWidth, constrainedMaxWidth).toDouble();
  }
}

/// 沉浸式媒体浏览器的共享横向内容轨道。
///
/// 顶部工具栏、文字区与底部工具栏都通过同一套约束收口，
/// 保证手机与平板上左右对齐线一致。
class ImmersiveViewerLayout {
  const ImmersiveViewerLayout._();

  static double horizontalPadding(
    BuildContext context, {
    ImmersiveViewerStageLayoutSpec layoutSpec =
        ImmersiveViewerStageLayoutSpec.feedRail,
  }) => layoutSpec.horizontalInset;

  /// 底部 chrome（caption / 交集 / 互动栏）的横向 inset。
  ///
  /// = [layoutSpec.horizontalInset] + 圆弧机型底部安全侧向保护；
  /// 正文（文章 immersive contentPadding）与这些层必须同源，避免左右漂移。
  static double bottomChromeHorizontalPadding(
    BuildContext context, {
    ImmersiveViewerStageLayoutSpec layoutSpec =
        ImmersiveViewerStageLayoutSpec.feedRail,
  }) {
    final bottomInset = MediaQuery.viewPaddingOf(context).bottom;
    return horizontalPadding(context, layoutSpec: layoutSpec) +
        AppSpacing.appChromeBottomSafeSideInset(context, bottomInset);
  }

  static double railWidthForViewport(
    BuildContext context,
    double viewportWidth, {
    ImmersiveViewerStageLayoutSpec layoutSpec =
        ImmersiveViewerStageLayoutSpec.feedRail,
    bool includeBottomSafeSideInset = false,
  }) {
    final inset = includeBottomSafeSideInset
        ? bottomChromeHorizontalPadding(context, layoutSpec: layoutSpec)
        : horizontalPadding(context, layoutSpec: layoutSpec);
    final availableWidth = math.max(0.0, viewportWidth - (inset * 2));
    final constrainedMaxWidth = layoutSpec.maxContentWidth;
    if (constrainedMaxWidth == null) {
      return availableWidth;
    }
    return math.min(availableWidth, constrainedMaxWidth).toDouble();
  }

  static Widget alignToRail({
    required BuildContext context,
    required Widget child,
    ImmersiveViewerStageLayoutSpec layoutSpec =
        ImmersiveViewerStageLayoutSpec.feedRail,
    bool includeBottomSafeSideInset = false,
  }) {
    final maxContentWidth = layoutSpec.maxContentWidth;
    final horizontal = includeBottomSafeSideInset
        ? bottomChromeHorizontalPadding(context, layoutSpec: layoutSpec)
        : horizontalPadding(context, layoutSpec: layoutSpec);
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: horizontal),
      child: Align(
        alignment: Alignment.center,
        child: maxContentWidth == null
            ? child
            : ConstrainedBox(
                constraints: BoxConstraints(maxWidth: maxContentWidth),
                child: child,
              ),
      ),
    );
  }
}

ArticleCanvasMetricsView resolveImmersiveArticleCanvasMetricsView(
  BuildContext context,
  BoxConstraints constraints, {
  required double topPaperReservedHeight,
}) {
  final width = constraints.maxWidth.isFinite
      ? constraints.maxWidth
      : MediaQuery.sizeOf(context).width;
  final height = constraints.maxHeight.isFinite
      ? constraints.maxHeight
      : MediaQuery.sizeOf(context).height;
  final horizontalInset = ImmersiveViewerLayout.bottomChromeHorizontalPadding(
    context,
    layoutSpec: ImmersiveViewerStageLayoutSpec.articleStage,
  );
  return ArticleCanvasMetricsView(
    aspectRatio: width > 0 && height > 0 ? width / height : 0.72,
    outerPadding: ArticleEdgeInsetsView.zero,
    contentPadding: ArticleEdgeInsetsView(
      left: horizontalInset,
      top: AppSpacing.containerLg + topPaperReservedHeight,
      right: horizontalInset,
      bottom: AppSpacing.containerMd,
    ),
    headerReservedHeight: 0,
    footerReservedHeight: 0,
    wrapImageGap: width >= 430
        ? AppSpacing.containerMd
        : AppSpacing.containerSm,
    wrapImageMaxWidth: width >= 430 ? 156 : 144,
    fullWidthImageAspectRatio: 4 / 3,
    journalImageAspectRatio: 1,
    inlineImageSpacing: AppSpacing.interGroupSm,
  );
}
