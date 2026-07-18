import 'package:chewie/chewie.dart';
import 'package:flutter/widgets.dart';
import 'package:video_player/video_player.dart';

import 'package:quwoquan_app/components/media/video/player/video_playback_session.dart';
import 'package:quwoquan_app/core/platform/video_player_controller_factory.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// Inline feed playback chrome. Commands remain owned by [VideoPlaybackSession].
class InlineFeedPlaybackOverlay extends StatelessWidget {
  const InlineFeedPlaybackOverlay({required this.session, super.key});

  final VideoPlaybackSession session;

  static String _formatDuration(Duration duration) {
    final totalSeconds = duration.inSeconds.clamp(0, 359999);
    final minutes = totalSeconds ~/ 60;
    final seconds = totalSeconds % 60;
    return '$minutes:${seconds.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: AnimatedBuilder(
        animation: session,
        builder: (context, _) {
          final snapshot = session.snapshot;
          if (!snapshot.isInitialized || snapshot.duration <= Duration.zero) {
            return const SizedBox.shrink();
          }
          final expanded = snapshot.isScrubbing || !snapshot.isPlaying;
          final trackHeight = expanded
              ? AppSpacing.xs
              : AppSpacing.xs / AppSpacing.two;
          return Stack(
            fit: StackFit.expand,
            children: [
              Positioned(
                top: AppSpacing.intraGroupSm,
                right: AppSpacing.intraGroupSm,
                child: AnimatedOpacity(
                  duration: const Duration(milliseconds: 180),
                  opacity:
                      snapshot.controlsVisibility ==
                          VideoPlaybackControlsVisibility.hidden
                      ? 0
                      : 1,
                  child: Text(
                    _formatDuration(snapshot.duration),
                    key: const ValueKey<String>(
                      'home-video-transient-duration',
                    ),
                    style: TextStyle(
                      color: AppColors.white.withValues(alpha: 0.96),
                      fontSize: AppTypography.xxs,
                      fontWeight: AppTypography.semiBold,
                      shadows: <Shadow>[
                        Shadow(
                          color: AppColors.black.withValues(alpha: 0.38),
                          blurRadius: AppSpacing.xs,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              Positioned(
                left: AppSpacing.intraGroupSm,
                right: AppSpacing.intraGroupSm,
                bottom: AppSpacing.intraGroupSm,
                child: _InlinePlaybackTrack(
                  progress: snapshot.progress,
                  height: trackHeight,
                  expanded: expanded,
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _InlinePlaybackTrack extends StatelessWidget {
  const _InlinePlaybackTrack({
    required this.progress,
    required this.height,
    required this.expanded,
  });

  final double progress;
  final double height;
  final bool expanded;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      child: SizedBox(
        height: height,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.white.withValues(alpha: expanded ? 0.46 : 0.30),
          ),
          child: FractionallySizedBox(
            alignment: Alignment.centerLeft,
            widthFactor: progress.clamp(0.0, 1.0),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.white.withValues(alpha: expanded ? 1 : 0.86),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

final class PlayableVideoSource {
  const PlayableVideoSource._({
    required this.label,
    required this.createController,
  });

  factory PlayableVideoSource.cachedFile(String path) {
    return PlayableVideoSource._(
      label: 'cache',
      createController: () =>
          AppVideoPlayerControllerFactory.localFilePath(path),
    );
  }

  factory PlayableVideoSource.network(Uri uri) {
    return PlayableVideoSource._(
      label: 'network',
      createController: () => AppVideoPlayerControllerFactory.networkUri(uri),
    );
  }

  final String label;
  final VideoPlayerController Function() createController;
}

/// 视频播放器控制器管理（按 url 释放单个控制器）。
class VideoPlayerManager {
  static final Map<String, VideoPlayerController> _controllers = {};
  static final Map<String, ChewieController> _chewieControllers = {};

  /// 释放控制器
  static void disposeController(String videoUrl) {
    _chewieControllers[videoUrl]?.dispose();
    _controllers[videoUrl]?.dispose();
    _chewieControllers.remove(videoUrl);
    _controllers.remove(videoUrl);
  }
}
