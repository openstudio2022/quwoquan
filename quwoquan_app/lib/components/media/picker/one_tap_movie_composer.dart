import 'dart:io';

import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

class OneTapMovieComposeResult {
  const OneTapMovieComposeResult({
    required this.videoPath,
    required this.durationMs,
    this.coverPath = '',
  });

  final String videoPath;
  final int durationMs;
  final String coverPath;
}

abstract class OneTapMovieComposer {
  Future<OneTapMovieComposeResult> compose({
    required List<CreateMediaItem> images,
  });
}

class MethodChannelOneTapMovieComposer implements OneTapMovieComposer {
  const MethodChannelOneTapMovieComposer()
    : _channel = const MethodChannel('quwoquan/video_editing');

  static const int secondsPerImage = 3;
  static const int outputWidth = 1080;
  static const int outputHeight = 1920;

  final MethodChannel _channel;

  @override
  Future<OneTapMovieComposeResult> compose({
    required List<CreateMediaItem> images,
  }) async {
    final imagePaths = images
        .where((item) => item.isImage)
        .map((item) => item.path.trim())
        .where((path) => path.isNotEmpty)
        .toList(growable: false);
    if (imagePaths.isEmpty) {
      throw ArgumentError.value(imagePaths, 'images', 'No images selected.');
    }
    if (!Platform.isIOS) {
      throw UnsupportedError(
        'One-tap movie composition is only available on iOS.',
      );
    }
    try {
      final response = await _channel.invokeMapMethod<String, dynamic>(
        'composeOneTapMovie',
        <String, dynamic>{
          'imagePaths': imagePaths,
          'secondsPerImage': secondsPerImage,
          'outputWidth': outputWidth,
          'outputHeight': outputHeight,
        },
      );
      final videoPath = (response?['videoPath'] ?? '').toString().trim();
      if (videoPath.isEmpty) {
        throw StateError(
          'One-tap movie composer returned an empty video path.',
        );
      }
      return OneTapMovieComposeResult(
        videoPath: videoPath,
        coverPath: (response?['coverPath'] ?? '').toString(),
        durationMs:
            (response?['durationMs'] as num?)?.toInt() ??
            imagePaths.length * secondsPerImage * 1000,
      );
    } on MissingPluginException {
      throw UnsupportedError('One-tap movie composition is not available.');
    }
  }
}
