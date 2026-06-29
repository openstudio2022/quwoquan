import 'package:flutter/foundation.dart';

enum CreateMediaType { image, video, gif }

enum CreateMediaSource { album, camera, generated }

enum MediaPickerCategory { all, video, photo, live, fullscreen }

enum MediaPickerEntryMode { image, video, mixed }

enum CreateEntryMediaResolution { empty, imageBatch, video }

CreateEntryMediaResolution resolveCreateEntryMediaResolution(
  Iterable<CreateMediaItem> items,
) {
  for (final item in items) {
    if (item.isVideo) {
      return CreateEntryMediaResolution.video;
    }
    if (item.isImage) {
      return CreateEntryMediaResolution.imageBatch;
    }
  }
  return CreateEntryMediaResolution.empty;
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

  CreateMediaItem copyWith({
    String? id,
    String? path,
    CreateMediaType? type,
    CreateMediaSource? source,
    int? width,
    int? height,
    int? durationMs,
    int? createdAtMs,
  }) {
    return CreateMediaItem(
      id: id ?? this.id,
      path: path ?? this.path,
      type: type ?? this.type,
      source: source ?? this.source,
      width: width ?? this.width,
      height: height ?? this.height,
      durationMs: durationMs ?? this.durationMs,
      createdAtMs: createdAtMs ?? this.createdAtMs,
    );
  }
}

@immutable
class CreateMediaPickerResult {
  const CreateMediaPickerResult({
    required this.items,
    this.openOneTapMovie = false,
    this.lockedSingleMedia = false,
    this.oneTapMovieEffectId = '',
  });

  final List<CreateMediaItem> items;
  final bool openOneTapMovie;
  final bool lockedSingleMedia;
  final String oneTapMovieEffectId;
}
