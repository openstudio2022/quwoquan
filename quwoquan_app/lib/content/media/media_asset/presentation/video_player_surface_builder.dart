import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/content/media/media_asset/presentation/video_playback_failure_overlay.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/media/media_playback_failure.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 播放器状态表面构建器，保持占位、延迟和失败状态的像素输出一致。
final class VideoPlayerSurfaceBuilder {
  const VideoPlayerSurfaceBuilder._();

  static Widget buildPlaceholder({
    required MediaDeliveryReference? thumbnailReference,
    required bool autoPlay,
    required bool showProgress,
    required bool showSlowHint,
  }) {
    final thumbnailUrl = thumbnailReference?.url ?? '';
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: AppColors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (thumbnailUrl.isNotEmpty)
            Positioned.fill(
              child: AppCachedNetworkImage(
                imageUrl: thumbnailUrl,
                imageUrlCandidates: <String>[thumbnailUrl],
                cdnPreset: CdnImagePreset.cover,
                fit: BoxFit.cover,
                placeholder: const SizedBox.shrink(),
                errorWidget: const SizedBox.shrink(),
              ),
            ),
          ColoredBox(color: AppColors.black.withValues(alpha: 0.22)),
          // 聚焦自动播放（autoPlay）时显示加载转圈，避免与卡片层叠出第二个
          // 「播放三角」按钮；未自动播放时仍用播放三角作为点按查看提示。
          Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (autoPlay && showProgress)
                CupertinoActivityIndicator(
                  color: AppColors.white,
                  radius: AppSpacing.iconMedium / 2,
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
    required MediaDeliveryReference? thumbnailReference,
  }) {
    final thumbnailUrl = thumbnailReference?.url ?? '';
    return ColoredBox(
      color: AppColors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (thumbnailUrl.isNotEmpty)
            AppCachedNetworkImage(
              imageUrl: thumbnailUrl,
              imageUrlCandidates: <String>[thumbnailUrl],
              cdnPreset: CdnImagePreset.cover,
              fit: BoxFit.cover,
              placeholder: const SizedBox.shrink(),
              errorWidget: const SizedBox.shrink(),
            ),
          ColoredBox(color: AppColors.black.withValues(alpha: 0.16)),
        ],
      ),
    );
  }

  static Widget buildFailure({
    required MediaPlaybackFailure failure,
    required MediaDeliveryReference? thumbnailReference,
    required bool retrying,
    required VoidCallback? onRetry,
    required VoidCallback? onExit,
  }) {
    return VideoPlaybackFailureOverlay(
      failure: failure,
      thumbnailReference: thumbnailReference,
      retrying: retrying,
      onRetry: onRetry,
      onExit: onExit,
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
