import 'package:flutter/foundation.dart';

import 'package:quwoquan_app/runtime/platform/video_native_playback_signals_stub.dart'
    if (dart.library.io) 'package:quwoquan_app/runtime/platform/video_native_playback_signals_android.dart'
    as impl;

/// Cross-cutting native playback evidence consumed by [VideoPlaybackSession].
@immutable
class VideoNativePlaybackSignal {
  const VideoNativePlaybackSignal({
    required this.kind,
    this.ttffMs,
    this.targetPositionMs,
    this.settledPositionMs,
    this.settleMs,
    this.droppedFrames,
    this.processedFrames,
    this.rendererMode,
    this.decoderQueueMode,
    this.decoderFallbackEnabled,
  });

  final VideoNativePlaybackSignalKind kind;
  final int? ttffMs;
  final int? targetPositionMs;
  final int? settledPositionMs;
  final int? settleMs;
  final int? droppedFrames;
  final int? processedFrames;
  final String? rendererMode;
  final String? decoderQueueMode;
  final bool? decoderFallbackEnabled;
}

enum VideoNativePlaybackSignalKind {
  playbackDiagnostics,
  renderedFirstFrame,
  seekSettled,
  droppedVideoFrames,
  audioUnderrun,
  videoFrameProcessing,
}

/// 当前平台能为 seek 提供的最强 settle 证据。
///
/// [positionReadbackOnly] 只能证明 controller 回读位置，不能声称画面
/// 已渲染。
enum VideoSeekSettleEvidenceCapability {
  nativeRenderedFrame,
  positionReadbackOnly,
}

int _nextNativePlaybackSignalToken = 1;

/// Creates an opaque controller token without exposing a platform player ID.
String createVideoNativePlaybackSignalToken() {
  final sequence = _nextNativePlaybackSignalToken++;
  return 'vp-${DateTime.now().toUtc().microsecondsSinceEpoch}-$sequence';
}

/// Returns headers understood only by the Android platform adapter.
///
/// The adapter removes them before constructing a media request.
Map<String, String> videoNativePlaybackSignalRequestHeaders(
  String sessionToken,
) {
  return impl.videoNativePlaybackSignalRequestHeadersImpl(sessionToken);
}

/// Filters native first-frame / seek-settle signals for [sessionToken].
///
/// Non-Android platforms simply never emit; callers must not invent settle.
Stream<VideoNativePlaybackSignal> videoNativePlaybackSignalsForToken(
  String sessionToken,
) {
  return impl
      .videoNativePlaybackSignalsForTokenImpl(sessionToken)
      .cast<VideoNativePlaybackSignal>();
}
