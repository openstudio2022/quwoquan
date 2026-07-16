import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/platform/video_player_controller_factory_io.dart'
    if (dart.library.js_interop)
        'package:quwoquan_app/core/platform/video_player_controller_factory_stub.dart';
import 'package:video_player/video_player.dart';

/// Video player controller boundary for local files and network URIs.
///
/// UI components should not import `dart:io` directly; cached local media files
/// are resolved by cache services and materialized into controllers here.
///
/// Android uses [VideoViewType.platformView] by default to avoid Flutter
/// TextureRegistry ImageReader-1x1 + OEM MediaCodec buffer failures (Huawei
/// Hisilicon). Decoder fallback itself is enabled in the vendored
/// `video_player_android` ExoPlayer factory.
class AppVideoPlayerControllerFactory {
  const AppVideoPlayerControllerFactory._();

  static VideoViewType get preferredViewType =>
      preferredVideoPlaybackViewType(currentAppPlatform);

  static VideoPlayerController localFilePath(String path) {
    return createLocalFileVideoController(
      path,
      viewType: preferredViewType,
    );
  }

  static VideoPlayerController networkUri(Uri uri) {
    return VideoPlayerController.networkUrl(
      uri,
      viewType: preferredViewType,
    );
  }
}

VideoViewType preferredVideoPlaybackViewType(AppPlatform platform) {
  switch (platform) {
    case AppPlatform.android:
      return VideoViewType.platformView;
    case AppPlatform.ios:
    case AppPlatform.ohos:
    case AppPlatform.web:
    case AppPlatform.desktop:
      return VideoViewType.textureView;
  }
}
