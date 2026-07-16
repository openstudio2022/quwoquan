import 'dart:io';

import 'package:video_player/video_player.dart';

VideoPlayerController createLocalFileVideoController(
  String path, {
  required VideoViewType viewType,
}) {
  return VideoPlayerController.file(File(path), viewType: viewType);
}
