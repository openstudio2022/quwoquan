import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/runtime/platform/video_native_playback_signals.dart';
import 'package:quwoquan_app/runtime/platform/video_player_controller_factory_io.dart'
    if (dart.library.js_interop) 'package:quwoquan_app/runtime/platform/video_player_controller_factory_stub.dart';
import 'package:video_player/video_player.dart';

/// A controller plus its platform-scoped native playback evidence stream.
@immutable
final class AppVideoPlayerControllerHandle {
  const AppVideoPlayerControllerHandle({
    required this.controller,
    required this.nativePlaybackSignals,
    required this.seekSettleEvidenceCapability,
  });

  final VideoPlayerController controller;
  final Stream<VideoNativePlaybackSignal> nativePlaybackSignals;
  final VideoSeekSettleEvidenceCapability seekSettleEvidenceCapability;
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

  // VideoPlayerWidget / VideoPlaybackSession owns the single app-lifecycle
  // pause/resume truth. Opting out of video_player's private observer also lets
  // a controller whose native create failed be abandoned without retaining a
  // permanent WidgetsBinding observer through the plugin's incomplete future.
  static final VideoPlayerOptions _ownedLifecycleOptions = VideoPlayerOptions(
    allowBackgroundPlayback: true,
  );

  static VideoViewType get preferredViewType =>
      preferredVideoPlaybackViewType(currentAppPlatform);

  static AppVideoPlayerControllerHandle localFilePath(
    String path, {
    VideoViewType? viewType,
  }) {
    final sessionToken = createVideoNativePlaybackSignalToken();
    return AppVideoPlayerControllerHandle(
      controller: createLocalFileVideoController(
        path,
        viewType: viewType ?? preferredViewType,
        httpHeaders: videoNativePlaybackSignalRequestHeaders(sessionToken),
        videoPlayerOptions: _ownedLifecycleOptions,
      ),
      nativePlaybackSignals: videoNativePlaybackSignalsForToken(sessionToken),
      seekSettleEvidenceCapability: _seekSettleEvidenceCapability,
    );
  }

  /// Creates the short-lived controller used only to prove that a local file
  /// can initialize. It intentionally preserves the plugin's default options
  /// and does not allocate a native playback telemetry token.
  static VideoPlayerController localFileReadinessProbe(String path) =>
      createLocalFileVideoReadinessProbeController(path);

  static AppVideoPlayerControllerHandle networkUri(
    Uri uri, {
    VideoFormat? formatHint,
    VideoViewType? viewType,
  }) {
    final sessionToken = createVideoNativePlaybackSignalToken();
    return AppVideoPlayerControllerHandle(
      controller: VideoPlayerController.networkUrl(
        uri,
        formatHint: formatHint,
        httpHeaders: videoNativePlaybackSignalRequestHeaders(sessionToken),
        viewType: viewType ?? preferredViewType,
        videoPlayerOptions: _ownedLifecycleOptions,
      ),
      nativePlaybackSignals: videoNativePlaybackSignalsForToken(sessionToken),
      seekSettleEvidenceCapability: _seekSettleEvidenceCapability,
    );
  }

  static VideoSeekSettleEvidenceCapability get _seekSettleEvidenceCapability {
    return currentAppPlatform == AppPlatform.android
        ? VideoSeekSettleEvidenceCapability.nativeRenderedFrame
        : VideoSeekSettleEvidenceCapability.positionReadbackOnly;
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
