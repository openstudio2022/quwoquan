import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

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

  static const ImmersiveViewerStageLayoutSpec articleStage =
      ImmersiveViewerStageLayoutSpec(horizontalInset: AppSpacing.intraGroupSm);

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

  static double railWidthForViewport(
    BuildContext context,
    double viewportWidth, {
    ImmersiveViewerStageLayoutSpec layoutSpec =
        ImmersiveViewerStageLayoutSpec.feedRail,
  }) => layoutSpec.railWidthForViewport(viewportWidth);

  static Widget alignToRail({
    required BuildContext context,
    required Widget child,
    ImmersiveViewerStageLayoutSpec layoutSpec =
        ImmersiveViewerStageLayoutSpec.feedRail,
  }) {
    final maxContentWidth = layoutSpec.maxContentWidth;
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: horizontalPadding(context, layoutSpec: layoutSpec),
      ),
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
