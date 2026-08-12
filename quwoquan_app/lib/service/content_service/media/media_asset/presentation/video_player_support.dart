import 'package:chewie/chewie.dart';
import 'package:video_player/video_player.dart';

import 'package:quwoquan_app/runtime/platform/video_player_controller_factory.dart';

final class PlayableVideoSource {
  const PlayableVideoSource._({
    required this.label,
    required this.createController,
  });

  factory PlayableVideoSource.cachedFile(
    String path, {
    VideoViewType? viewType,
  }) {
    return PlayableVideoSource._(
      label: 'cache',
      createController: () => AppVideoPlayerControllerFactory.localFilePath(
        path,
        viewType: viewType,
      ),
    );
  }

  factory PlayableVideoSource.network(
    Uri uri, {
    VideoFormat? formatHint,
    VideoViewType? viewType,
  }) {
    return PlayableVideoSource._(
      label: 'network',
      createController: () => AppVideoPlayerControllerFactory.networkUri(
        uri,
        formatHint: formatHint,
        viewType: viewType,
      ),
    );
  }

  final String label;
  final AppVideoPlayerControllerHandle Function() createController;
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
