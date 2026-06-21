import 'dart:io';

import 'package:video_player/video_player.dart';

/// Video player controller boundary for local files.
///
/// UI components should not import `dart:io` directly; cached local media files
/// are resolved by cache services and materialized into controllers here.
class AppVideoPlayerControllerFactory {
  const AppVideoPlayerControllerFactory._();

  static VideoPlayerController localFilePath(String path) {
    return VideoPlayerController.file(File(path));
  }

  static VideoPlayerController networkUri(Uri uri) {
    return VideoPlayerController.networkUrl(uri);
  }
}
