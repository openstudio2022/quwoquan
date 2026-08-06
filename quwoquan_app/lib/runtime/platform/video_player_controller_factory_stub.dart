import 'package:video_player/video_player.dart';

VideoPlayerController createLocalFileVideoController(
  String path, {
  required VideoViewType viewType,
  required Map<String, String> httpHeaders,
  required VideoPlayerOptions videoPlayerOptions,
}) {
  // Web has no local file controllers; callers must gate on capabilities.
  throw UnsupportedError(
    'AppVideoPlayerControllerFactory.localFilePath is unavailable on web',
  );
}

VideoPlayerController createLocalFileVideoReadinessProbeController(
  String path,
) {
  throw UnsupportedError('local video readiness probes are unavailable on web');
}
