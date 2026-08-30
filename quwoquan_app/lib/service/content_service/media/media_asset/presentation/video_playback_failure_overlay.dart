import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/media_playback_failure.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_media_failure_content.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/runtime/errors/app_user_recovery.dart';

/// 播放失败覆盖层：复用同源封面，且只展示由失败恢复策略允许的重试操作。
class VideoPlaybackFailureOverlay extends StatelessWidget {
  const VideoPlaybackFailureOverlay({
    super.key,
    required this.failure,
    required this.thumbnailBinding,
    this.retrying = false,
    this.onRetry,
    this.onExit,
  });

  final MediaPlaybackFailure failure;
  final MediaDeliveryBinding thumbnailBinding;
  final bool retrying;
  final VoidCallback? onRetry;
  final VoidCallback? onExit;

  @override
  Widget build(BuildContext context) {
    final copy = failure.copy;
    final message = copy.message?.trim() ?? '';
    final recoveryCopy = AppUserRecoveryContract.copyFor(
      failure.userRecoveryGroup,
    );
    final action = failure.isRetryable ? onRetry : onExit;
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: AppColors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          mediaDeliveryImage(
            binding: thumbnailBinding,
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
              onRetry: action,
              retryKey: const ValueKey<String>('video-player-retry'),
              actionLabel: recoveryCopy.action.label,
            ),
          ),
        ],
      ),
    );
  }
}
