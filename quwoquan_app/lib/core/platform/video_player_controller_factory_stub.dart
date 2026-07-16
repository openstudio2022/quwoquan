import 'package:video_player/video_player.dart';

VideoPlayerController createLocalFileVideoController(
  String path, {
  required VideoViewType viewType,
}) {
  // Web has no local file controllers; callers must gate on capabilities.
  throw UnsupportedError(
    'AppVideoPlayerControllerFactory.localFilePath is unavailable on web',
  );
}
