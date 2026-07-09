import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

class OneTapMovieNativeComposeResult {
  const OneTapMovieNativeComposeResult({
    required this.videoPath,
    required this.durationMs,
    this.coverPath = '',
  });

  final String videoPath;
  final int durationMs;
  final String coverPath;
}

abstract interface class OneTapMovieNativeBridge {
  Future<OneTapMovieNativeComposeResult> compose({
    required List<String> imagePaths,
    required int secondsPerImage,
    required int outputWidth,
    required int outputHeight,
  });
}

class MethodChannelOneTapMovieNativeBridge implements OneTapMovieNativeBridge {
  const MethodChannelOneTapMovieNativeBridge({
    this.channel = const MethodChannel('quwoquan/video_editing'),
  });

  final MethodChannel channel;

  @override
  Future<OneTapMovieNativeComposeResult> compose({
    required List<String> imagePaths,
    required int secondsPerImage,
    required int outputWidth,
    required int outputHeight,
  }) async {
    if (currentAppPlatform != AppPlatform.ios) {
      throw UnsupportedError(
        'One-tap movie composition is only available on iOS.',
      );
    }
    try {
      final response = await channel.invokeMapMethod<String, dynamic>(
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
      return OneTapMovieNativeComposeResult(
        videoPath: videoPath,
        coverPath: (response?['coverPath'] ?? '').toString(),
        durationMs:
            (response?['durationMs'] as num?)?.toInt() ??
            imagePaths.length * secondsPerImage * 1000,
      );
    } on MissingPluginException catch (error) {
      throw StateError(
        'One-tap movie native channel is not registered: $error',
      );
    }
  }
}
