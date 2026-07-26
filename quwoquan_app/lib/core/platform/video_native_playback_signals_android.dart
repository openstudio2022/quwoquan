import 'package:flutter/foundation.dart';
import 'package:video_player_android/video_player_android.dart';

import 'package:quwoquan_app/core/platform/video_native_playback_signals.dart';

/// I/O bridge that activates vendored Android signals only on Android.
Map<String, String> videoNativePlaybackSignalRequestHeadersImpl(
  String sessionToken,
) {
  if (defaultTargetPlatform != TargetPlatform.android) {
    return const <String, String>{};
  }
  return <String, String>{
    AndroidVideoPlayer.nativePlaybackSignalTokenHeader: sessionToken,
  };
}

Stream<Object> videoNativePlaybackSignalsForTokenImpl(String sessionToken) {
  if (defaultTargetPlatform != TargetPlatform.android) {
    return const Stream<Object>.empty();
  }
  return AndroidVideoPlayer.nativePlaybackSignalsFor(sessionToken).map(
    (signal) => VideoNativePlaybackSignal(
      kind: switch (signal.kind) {
        AndroidVideoNativePlaybackSignalKind.playbackDiagnostics =>
          VideoNativePlaybackSignalKind.playbackDiagnostics,
        AndroidVideoNativePlaybackSignalKind.renderedFirstFrame =>
          VideoNativePlaybackSignalKind.renderedFirstFrame,
        AndroidVideoNativePlaybackSignalKind.seekSettled =>
          VideoNativePlaybackSignalKind.seekSettled,
        AndroidVideoNativePlaybackSignalKind.droppedVideoFrames =>
          VideoNativePlaybackSignalKind.droppedVideoFrames,
        AndroidVideoNativePlaybackSignalKind.audioUnderrun =>
          VideoNativePlaybackSignalKind.audioUnderrun,
        AndroidVideoNativePlaybackSignalKind.videoFrameProcessing =>
          VideoNativePlaybackSignalKind.videoFrameProcessing,
      },
      ttffMs: signal.ttffMs,
      targetPositionMs: signal.targetPositionMs,
      settledPositionMs: signal.settledPositionMs,
      settleMs: signal.settleMs,
      droppedFrames: signal.droppedFrames,
      processedFrames: signal.processedFrames,
      rendererMode: signal.rendererMode,
      decoderQueueMode: signal.decoderQueueMode,
      decoderFallbackEnabled: signal.decoderFallbackEnabled,
    ),
  );
}
