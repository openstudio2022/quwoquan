import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/media/media_playback_failure.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/components/media/shared/viewer/immersive_media_failure_content.dart';

/// 播放失败覆盖层：复用同源封面，且只展示由失败恢复策略允许的重试操作。
class VideoPlaybackFailureOverlay extends StatelessWidget {
  const VideoPlaybackFailureOverlay({
    super.key,
    required this.failure,
    this.thumbnailReference,
    this.retrying = false,
    this.onRetry,
  });

  final MediaPlaybackFailure failure;
  final MediaDeliveryReference? thumbnailReference;
  final bool retrying;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final copy = failure.copy;
    final message = copy.message?.trim() ?? '';
    final thumbnailUrl = thumbnailReference?.url ?? '';
    final showRetry = failure.isRetryable && onRetry != null;
    return Container(
      width: double.infinity,
      height: double.infinity,
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
          ColoredBox(color: AppColors.black.withValues(alpha: 0.56)),
          Center(
            child: ImmersiveMediaFailureContent(
              key: const ValueKey<String>('video-player-error'),
              presentation: MediaFailurePresentation(
                title: copy.title,
                message: message.isEmpty ? null : message,
              ),
              retrying: retrying,
              onRetry: showRetry ? onRetry : null,
              retryKey: const ValueKey<String>('video-player-retry'),
            ),
          ),
        ],
      ),
    );
  }
}
