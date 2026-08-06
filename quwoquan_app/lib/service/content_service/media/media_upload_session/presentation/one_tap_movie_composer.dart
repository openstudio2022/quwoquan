import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/runtime/platform/one_tap_movie_native_bridge.dart';

class OneTapMovieComposeResult {
  const OneTapMovieComposeResult({
    required this.videoPath,
    required this.durationMs,
    this.coverPath = '',
    this.effectId = 'original',
  });

  final String videoPath;
  final int durationMs;
  final String coverPath;
  final String effectId;
}

abstract class OneTapMovieComposer {
  Future<OneTapMovieComposeResult> compose({
    required List<CreateMediaItem> images,
  });
}

class MethodChannelOneTapMovieComposer implements OneTapMovieComposer {
  const MethodChannelOneTapMovieComposer({
    this._nativeBridge = const MethodChannelOneTapMovieNativeBridge(),
  });

  static const int secondsPerImage = 3;
  static const int outputWidth = 1080;
  static const int outputHeight = 1920;

  final OneTapMovieNativeBridge _nativeBridge;

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
    final response = await _nativeBridge.compose(
      imagePaths: imagePaths,
      secondsPerImage: secondsPerImage,
      outputWidth: outputWidth,
      outputHeight: outputHeight,
    );
    return OneTapMovieComposeResult(
      videoPath: response.videoPath,
      coverPath: response.coverPath,
      durationMs: response.durationMs,
    );
  }
}
