import 'package:flutter/foundation.dart';

enum CreateMediaType {
  image,
  video,
  gif,
}

enum CreateMediaSource {
  album,
  camera,
}

enum MediaPickerCategory {
  all,
  video,
  photo,
  live,
  fullscreen,
}

enum MediaPickerEntryMode {
  image,
  video,
}

@immutable
class CreateMediaItem {
  const CreateMediaItem({
    required this.id,
    required this.path,
    required this.type,
    required this.source,
    this.width = 0,
    this.height = 0,
    this.durationMs = 0,
    this.createdAtMs = 0,
  });

  final String id;
  final String path;
  final CreateMediaType type;
  final CreateMediaSource source;
  final int width;
  final int height;
  final int durationMs;
  final int createdAtMs;

  bool get isVideo => type == CreateMediaType.video;
  bool get isImage => !isVideo;
  bool get isGif => type == CreateMediaType.gif;

  bool get isFullscreenImage {
    if (!isImage || width <= 0 || height <= 0) return false;
    final ratio = height / width;
    return ratio >= 1.9;
  }
}

@immutable
class CreateMediaPickerResult {
  const CreateMediaPickerResult({
    required this.items,
    this.openOneTapMovie = false,
  });

  final List<CreateMediaItem> items;
  final bool openOneTapMovie;
}
