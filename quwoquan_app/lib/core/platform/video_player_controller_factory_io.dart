import 'dart:io';

import 'package:video_player/video_player.dart';

VideoPlayerController createLocalFileVideoController(
  String path, {
  required VideoViewType viewType,
  required Map<String, String> httpHeaders,
  required VideoPlayerOptions videoPlayerOptions,
}) {
  return VideoPlayerController.file(
    File(path),
    httpHeaders: httpHeaders,
    viewType: viewType,
    videoPlayerOptions: videoPlayerOptions,
  );
}
