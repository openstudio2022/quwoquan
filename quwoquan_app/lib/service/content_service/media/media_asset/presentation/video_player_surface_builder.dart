import 'package:flutter/material.dart';
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
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';

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
          Positioned.fill(
            child: _thumbnail(thumbnailBinding),
          ),
          ColoredBox(color: AppColors.black.withValues(alpha: 0.22)),
          // 聚焦自动播放（autoPlay）时显示加载转圈，避免与卡片层叠出第二个
          // 「播放三角」按钮；未自动播放时仍用播放三角作为点按查看提示。
          Column(
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
      publicBuilder: (context, publicUrl) => AppCachedNetworkImage(
        imageUrl: publicUrl,
        imageUrlCandidates: <String>[publicUrl],
        cdnPreset: CdnImagePreset.cover,
        fit: BoxFit.cover,
        placeholder: const SizedBox.shrink(),
        errorWidget: const SizedBox.shrink(),
      ),
    );
  }

  static Widget buildCenteredFrame({
    required double aspectRatio,
    required Widget child,
  }) {
    return ColoredBox(
      color: AppColors.black,
      child: Center(
        child: AspectRatio(aspectRatio: aspectRatio, child: child),
      ),
    );
  }
}
