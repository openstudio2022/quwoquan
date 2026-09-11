import 'package:chewie/chewie.dart';
import 'package:video_player/video_player.dart';

export 'package:quwoquan_app/runtime/platform/media/public_media_delivery_port.dart'
    show PlayableVideoSource;

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
