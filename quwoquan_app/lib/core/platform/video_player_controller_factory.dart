import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/platform/video_native_playback_signals.dart';
import 'package:quwoquan_app/core/platform/video_player_controller_factory_io.dart'
    if (dart.library.js_interop) 'package:quwoquan_app/core/platform/video_player_controller_factory_stub.dart';
import 'package:video_player/video_player.dart';

/// A controller plus its platform-scoped native playback evidence stream.
@immutable
final class AppVideoPlayerControllerHandle {
  const AppVideoPlayerControllerHandle({
    required this.controller,
    required this.nativePlaybackSignals,
  });

  final VideoPlayerController controller;
  final Stream<VideoNativePlaybackSignal> nativePlaybackSignals;
}

/// Video player controller boundary for local files and network URIs.
///
/// UI components should not import `dart:io` directly; cached local media files
/// are resolved by cache services and materialized into controllers here.
///
/// Android uses [VideoViewType.platformView] by default to avoid Flutter
/// TextureRegistry ImageReader-1x1 + brittle OEM MediaCodec buffer failures on
/// early/low-end stacks. Decoder fallback and sync MediaCodec queueing are the
/// default in the vendored `video_player_android` ExoPlayer factory.
class AppVideoPlayerControllerFactory {
  const AppVideoPlayerControllerFactory._();

  static VideoViewType get preferredViewType =>
      preferredVideoPlaybackViewType(currentAppPlatform);

  static AppVideoPlayerControllerHandle localFilePath(String path) {
    final sessionToken = createVideoNativePlaybackSignalToken();
    return AppVideoPlayerControllerHandle(
      controller: createLocalFileVideoController(
        path,
        viewType: preferredViewType,
        httpHeaders: videoNativePlaybackSignalRequestHeaders(sessionToken),
      ),
      nativePlaybackSignals: videoNativePlaybackSignalsForToken(sessionToken),
    );
  }

  static AppVideoPlayerControllerHandle networkUri(Uri uri) {
    final sessionToken = createVideoNativePlaybackSignalToken();
    return AppVideoPlayerControllerHandle(
      controller: VideoPlayerController.networkUrl(
        uri,
        httpHeaders: videoNativePlaybackSignalRequestHeaders(sessionToken),
        viewType: preferredViewType,
      ),
      nativePlaybackSignals: videoNativePlaybackSignalsForToken(sessionToken),
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
