import 'package:flutter/material.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_viewer_layout.dart';
import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_failure_overlay.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/media_playback_failure.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart' show CdnImagePreset, appImageLoadSuccessKey;
import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';

/// 沉浸视频唯一布局结果。高度输入来自同一 layout pass 的真实子节点测量。
@immutable
class WorksVideoGeometry {
  WorksVideoGeometry({
    required Size size,
    required double aspectRatio,
    required double topInset,
    required double toolbarHeight,
    required double captionHeight,
    required double entryHeight,
    double associationHeight = 0,
    double scrubHeight = 0,
    double horizontalInset = AppSpacing.containerMd,
  }) {
    final railWidth = (size.width - horizontalInset * 2).clamp(0.0, size.width);
    final bottom = (size.height - toolbarHeight).clamp(0.0, size.height);
    toolbarRect = Rect.fromLTWH(0, bottom, size.width, size.height - bottom);
    timelineRect = Rect.fromLTWH(
      horizontalInset,
      (bottom - AppSpacing.minInteractiveSize).clamp(0.0, bottom),
      railWidth,
      AppSpacing.minInteractiveSize,
    );
    final infoBottom = timelineRect.top - AppSpacing.intraGroupXs - scrubHeight;
    captionRect = Rect.fromLTWH(
      horizontalInset,
      infoBottom - captionHeight,
      railWidth,
      captionHeight,
    );
    final associationGap = associationHeight > 0 && captionHeight > 0
        ? AppSpacing.intraGroupSm
        : 0.0;
    associationRect = Rect.fromLTWH(
      horizontalInset,
      captionRect.top - associationHeight - associationGap,
      railWidth,
      associationHeight,
    );
    informationRect = Rect.fromLTWH(
      horizontalInset,
      associationRect.top,
      railWidth,
      captionHeight + associationHeight + associationGap,
    );
    final media = ImmersiveMediaGeometry(
      size: size,
      aspectRatio: aspectRatio,
      topInset: topInset,
      bottomInset: size.height - informationRect.top,
      entryExtent: entryHeight,
    );
    stageRect = media.viewportRect;
    videoRect = media.contentRect;
    entryRect = media.entryRect;
    gradientRect = Rect.fromLTRB(
      0,
      (informationRect.top - AppSpacing.containerLg).clamp(0.0, bottom),
      size.width,
      bottom,
    );
  }

  /// 宿主以该窗口裁剪自然比例 [videoRect]，不使用 cover 再缩放。
  late final Rect stageRect;
  late final Rect videoRect;
  late final Rect entryRect;
  late final Rect informationRect;
  late final Rect associationRect;
  late final Rect captionRect;
  late final Rect timelineRect;
  late final Rect toolbarRect;
  late final Rect gradientRect;
}

/// 播放器状态表面构建器，保持占位、延迟和失败状态的像素输出一致。
final class VideoPlayerSurfaceBuilder {
  const VideoPlayerSurfaceBuilder._();

  static Widget buildPlaceholder({
    required MediaDeliveryBinding thumbnailBinding,
    required bool autoPlay,
    required bool showProgress,
    required bool showSlowHint,
  }) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: AppColors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Positioned.fill(child: _thumbnail(thumbnailBinding)),
          ColoredBox(color: AppColors.black.withValues(alpha: 0.22)),
          // 聚焦自动播放（autoPlay）时显示加载转圈，避免与卡片层叠出第二个
          // 「播放三角」按钮；未自动播放时仍用播放三角作为点按查看提示。
          Center(
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  if (autoPlay && showProgress)
                    SizedBox.square(
                      dimension: AppSpacing.iconMedium,
                      child: FittedBox(
                        child: AppRequestFeedback.inline(
                          indicatorColor: AppColors.immersiveForeground,
                        ),
                      ),
                    )
                  else if (!autoPlay)
                    Icon(
                      Icons.play_circle_outline,
                      size: (AppSpacing.avatarSize * 2).sp,
                      color: AppColors.white,
                    ),
                  if (showSlowHint) ...<Widget>[
                    SizedBox(height: AppSpacing.sm.h),
                    Text(
                      FoundationText.requestWaitSlow,
                      style: TextStyle(
                        color: AppColors.white,
                        fontSize: AppTypography.sm.sp,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  static Widget buildDeferred({
    required MediaDeliveryBinding thumbnailBinding,
  }) {
    return ColoredBox(
      color: AppColors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          _thumbnail(thumbnailBinding),
          ColoredBox(color: AppColors.black.withValues(alpha: 0.16)),
        ],
      ),
    );
  }

  static Widget buildFailure({
    required MediaPlaybackFailure failure,
    required MediaDeliveryBinding thumbnailBinding,
    required bool retrying,
    required VoidCallback? onRetry,
    required VoidCallback? onExit,
  }) {
    return VideoPlaybackFailureOverlay(
      failure: failure,
      thumbnailBinding: thumbnailBinding,
      retrying: retrying,
      onRetry: onRetry,
      onExit: onExit,
    );
  }

  /// 视频封面的 typed 交付渲染（DEC-033）。
  ///
  /// 封面缺席时不占位，与既有「无封面直接露黑底」的观感一致；私有封面经统一
  /// 分流入口换短签，公开封面维持既有候选推导与 CDN 预设。
  static Widget _thumbnail(MediaDeliveryBinding binding) {
    return mediaDeliveryImage(
      binding: binding,
      kind: MediaDeliveryKind.image,
      fit: BoxFit.cover,
      placeholder: const SizedBox.shrink(),
      errorWidget: const SizedBox.shrink(),
      absentWidget: const SizedBox.shrink(),
      publicBuilder: (context, publicUrl) => Image(
        image: publicMediaDelivery.imageProvider(
          publicUrl,
          profile: CdnImagePreset.cover,
          kind: MediaDeliveryKind.image,
        ),
        fit: BoxFit.cover,
        frameBuilder: (context, child, frame, synchronouslyLoaded) =>
            synchronouslyLoaded || frame != null
                ? KeyedSubtree(key: appImageLoadSuccessKey, child: child)
                : const SizedBox.shrink(),
        errorBuilder: (context, error, stackTrace) => const SizedBox.shrink(),
      ),
    );
  }

  static Widget buildCenteredFrame({
    required double aspectRatio,
    required Widget child,
    BoxFit fit = BoxFit.contain,
  }) {
    return ColoredBox(
      color: AppColors.black,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final source = Size(aspectRatio, 1);
          final fitted = applyBoxFit(fit, source, constraints.biggest);
          final scale = fitted.destination.width / fitted.source.width;
          return ClipRect(
            child: Center(
              child: OverflowBox(
                minWidth: source.width * scale,
                maxWidth: source.width * scale,
                minHeight: source.height * scale,
                maxHeight: source.height * scale,
                child: child,
              ),
            ),
          );
        },
      ),
    );
  }
}
