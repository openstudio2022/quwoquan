import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

/// 图片、视频及翻页材质共用的纯几何；矩形均为宿主视口坐标。
///
/// [viewportRect] 只负责裁剪，[contentRect] 保持完整自然比例。入口高度由
/// 同次布局的真实热区（含间距）传入，隐藏控件时不得释放该空间。
@immutable
class ImmersiveMediaGeometry {
  ImmersiveMediaGeometry({
    required Size size,
    required double aspectRatio,
    required double topInset,
    required double bottomInset,
    double entryExtent = 0,
    bool fullscreen = false,
  }) {
    if (!size.width.isFinite || !size.height.isFinite || size.isEmpty) {
      viewportRect = contentRect = entryRect = Rect.zero;
      return;
    }
    final fullRect = Offset.zero & size;
    final top = topInset.isFinite ? topInset.clamp(0.0, size.height) : 0.0;
    final bottom = bottomInset.isFinite
        ? (size.height - bottomInset).clamp(0.0, size.height)
        : size.height;
    final hasRatio = aspectRatio.isFinite && aspectRatio > 0;
    final naturalHeight = hasRatio ? size.width / aspectRatio : 0.0;
    if (!hasRatio || !naturalHeight.isFinite) {
      // 未知尺寸保留中性舞台，不用猜测比例制造全屏入口。
      viewportRect = fullscreen
          ? fullRect
          : Rect.fromLTRB(0, math.min(top, bottom), size.width, bottom);
      contentRect = entryRect = Rect.zero;
      return;
    }
    if (fullscreen) {
      viewportRect = fullRect;
      final scale = math.min(1.0, size.height / naturalHeight);
      final contentSize = Size(size.width * scale, naturalHeight * scale);
      contentRect = Alignment.center.inscribe(contentSize, fullRect);
      entryRect = Rect.zero;
      return;
    }
    final entry =
        aspectRatio > 1 && size.height > size.width && entryExtent.isFinite
        ? entryExtent.clamp(0.0, bottom)
        : 0.0;
    final contentBottom = bottom - entry;
    final ordinaryHeight = contentBottom - top;
    if (naturalHeight <= ordinaryHeight) {
      final slack = ordinaryHeight - naturalHeight;
      viewportRect = Rect.fromLTWH(
        0,
        top + slack * AppSpacing.immersiveLandscapeVideoTopSlackFraction,
        size.width,
        naturalHeight,
      );
    } else if (naturalHeight < contentBottom) {
      viewportRect = Rect.fromLTRB(0, top, size.width, contentBottom);
    } else if (naturalHeight < size.height) {
      viewportRect = Rect.fromLTWH(0, 0, size.width, contentBottom);
    } else {
      viewportRect = fullRect;
    }
    contentRect = Rect.fromLTWH(
      0,
      viewportRect.center.dy - naturalHeight / 2,
      size.width,
      naturalHeight,
    );
    entryRect = entry > 0 && viewportRect.bottom + entry <= bottom
        ? Rect.fromLTWH(0, viewportRect.bottom, size.width, entry)
        : Rect.zero;
  }

  late final Rect viewportRect;
  late final Rect contentRect;
  late final Rect entryRect;
}

/// 局部横向全屏的单一三轨几何快照。外部按钮槽相对安全视口固定，
/// 媒体在中间舞台内 contain；所有媒体内 chrome 只消费 [visibleMediaRect]。
@immutable
class ImmersiveLandscapeGeometry {
  ImmersiveLandscapeGeometry({
    required Size size,
    required EdgeInsets safeInsets,
    required double aspectRatio,
    double controlSlotWidth = AppSpacing.minInteractiveSize,
    double slotGap = AppSpacing.intraGroupXs,
  }) {
    final fullRect = Offset.zero & size;
    final safeLeft = safeInsets.left.clamp(0.0, size.width);
    final safeRight = (size.width - safeInsets.right).clamp(
      safeLeft,
      size.width,
    );
    final safeTop = safeInsets.top.clamp(0.0, size.height);
    final safeBottom = (size.height - safeInsets.bottom).clamp(
      safeTop,
      size.height,
    );
    safeViewportRect = Rect.fromLTRB(safeLeft, safeTop, safeRight, safeBottom);

    final slot = math.max(AppSpacing.minInteractiveSize, controlSlotWidth);
    final gap = math.max(0.0, slotGap);
    leftControlSlot = Rect.fromLTWH(
      safeLeft,
      safeTop,
      slot,
      safeBottom - safeTop,
    );
    rightControlSlot = Rect.fromLTWH(
      math.max(safeLeft, safeRight - slot),
      safeTop,
      math.min(slot, safeRight - safeLeft),
      safeBottom - safeTop,
    );
    mediaStageRect = Rect.fromLTRB(
      math.min(safeRight, leftControlSlot.right + gap),
      safeTop,
      math.max(safeLeft, rightControlSlot.left - gap),
      safeBottom,
    );
    if (mediaStageRect.right < mediaStageRect.left) {
      mediaStageRect = Rect.fromLTWH(
        mediaStageRect.center.dx,
        safeTop,
        0,
        safeBottom - safeTop,
      );
    }

    final validRatio = aspectRatio.isFinite && aspectRatio > 0;
    if (!validRatio || mediaStageRect.isEmpty) {
      visibleMediaRect = Rect.zero;
    } else {
      final stageRatio = mediaStageRect.width / mediaStageRect.height;
      final mediaSize = aspectRatio >= stageRatio
          ? Size(mediaStageRect.width, mediaStageRect.width / aspectRatio)
          : Size(mediaStageRect.height * aspectRatio, mediaStageRect.height);
      visibleMediaRect = Alignment.center.inscribe(mediaSize, mediaStageRect);
    }
    mediaInnerRail = Rect.fromLTRB(
      visibleMediaRect.left,
      fullRect.top,
      visibleMediaRect.right,
      fullRect.bottom,
    );
  }

  late final Rect safeViewportRect;
  late final Rect leftControlSlot;
  late final Rect mediaStageRect;
  late final Rect rightControlSlot;
  late final Rect visibleMediaRect;
  late final Rect mediaInnerRail;
}

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

  /// 全页唯一横向对齐轨道（REQ-019）：顶栏、caption、交集句、底部工具栏与
  /// 文章正文共用本 inset，底部 chrome 不叠加额外侧向收窄；机型底部安全区
  /// 的保护只以垂直方向表达（见 `AppSpacing.immersiveBottomChromeLift`）。
  static double horizontalPadding(
    BuildContext context, {
    ImmersiveViewerStageLayoutSpec layoutSpec =
        ImmersiveViewerStageLayoutSpec.feedRail,
  }) => layoutSpec.horizontalInset;

  static double railWidthForViewport(
    BuildContext context,
    double viewportWidth, {
    ImmersiveViewerStageLayoutSpec layoutSpec =
        ImmersiveViewerStageLayoutSpec.feedRail,
  }) {
    final inset = horizontalPadding(context, layoutSpec: layoutSpec);
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
  }) {
    final maxContentWidth = layoutSpec.maxContentWidth;
    final horizontal = horizontalPadding(context, layoutSpec: layoutSpec);
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
  final horizontalInset = ImmersiveViewerLayout.horizontalPadding(
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
    wrapImageGap: width >= AppSpacing.articleWrapImageBreakpoint
        ? AppSpacing.containerMd
        : AppSpacing.containerSm,
    wrapImageMaxWidth: width >= AppSpacing.articleWrapImageBreakpoint
        ? AppSpacing.articleWrapImageMaxWidthWide
        : AppSpacing.articleWrapImageMaxWidthCompact,
    fullWidthImageAspectRatio: 4 / 3,
    journalImageAspectRatio: 1,
    inlineImageSpacing: AppSpacing.interGroupSm,
  );
}
