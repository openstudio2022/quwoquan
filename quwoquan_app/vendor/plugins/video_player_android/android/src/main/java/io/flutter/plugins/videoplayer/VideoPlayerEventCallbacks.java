// Copyright 2013 The Flutter Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package io.flutter.plugins.videoplayer;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.VisibleForTesting;
import io.flutter.plugin.common.BinaryMessenger;

final class VideoPlayerEventCallbacks implements VideoPlayerCallbacks {
  private final QueuingEventSink eventSink;

  static VideoPlayerEventCallbacks bindTo(
      @NonNull BinaryMessenger binaryMessenger, @NonNull String identifier) {
    QueuingEventSink eventSink = new QueuingEventSink();
    VideoEventsStreamHandler.Companion.register(
        binaryMessenger,
        new VideoEventsStreamHandler() {
          @Override
          public void onListen(
              Object arguments, @NonNull PigeonEventSink<PlatformVideoEvent> events) {
            eventSink.setDelegate(events);
          }

          @Override
          public void onCancel(Object arguments) {
            eventSink.setDelegate(null);
          }
        },
        identifier);
    return VideoPlayerEventCallbacks.withSink(eventSink);
  }

  @VisibleForTesting
  static VideoPlayerEventCallbacks withSink(QueuingEventSink eventSink) {
    return new VideoPlayerEventCallbacks(eventSink);
  }

  private VideoPlayerEventCallbacks(QueuingEventSink eventSink) {
    this.eventSink = eventSink;
  }

  @Override
  public void onInitialized(
      int width, int height, long durationInMs, int rotationCorrectionInDegrees) {
    eventSink.success(
        new InitializationEvent(durationInMs, width, height, rotationCorrectionInDegrees));
  }

  @Override
  public void onPlaybackStateChanged(@NonNull PlatformPlaybackState state) {
    eventSink.success(new PlaybackStateChangeEvent(state));
  }

  @Override
  public void onError(@NonNull String code, @Nullable String message, @Nullable Object details) {
    eventSink.error(code, message, details);
  }

  @Override
  public void onIsPlayingStateUpdate(boolean isPlaying) {
    eventSink.success(new IsPlayingStateEvent(isPlaying));
  }

  @Override
  public void onAudioTrackChanged(@Nullable String selectedTrackId) {
    eventSink.success(new AudioTrackChangedEvent(selectedTrackId));
  }

  @Override
  public void onPlaybackDiagnostics(
      @NonNull String rendererMode,
      @NonNull String decoderQueueMode,
      boolean decoderFallbackEnabled) {
    eventSink.success(
        new PlaybackDiagnosticsEvent(
            rendererMode, decoderQueueMode, decoderFallbackEnabled));
  }

  @Override
  public void onRenderedFirstFrame(long ttffMs) {
    eventSink.success(new RenderedFirstFrameEvent(ttffMs));
  }

  @Override
  public void onSeekSettled(long targetPositionMs, long settledPositionMs, long settleMs) {
    eventSink.success(new SeekSettledEvent(targetPositionMs, settledPositionMs, settleMs));
  }

  @Override
  public void onDroppedVideoFrames(int droppedFrames, long elapsedMs) {
    eventSink.success(new DroppedVideoFramesEvent((long) droppedFrames, elapsedMs));
  }

  @Override
  public void onAudioUnderrun(
      int bufferSize, long bufferSizeMs, long elapsedSinceLastFeedMs) {
    eventSink.success(
        new AudioUnderrunEvent(
            (long) bufferSize, bufferSizeMs, elapsedSinceLastFeedMs));
  }

  @Override
  public void onVideoFrameProcessing(int processedFrames) {
    eventSink.success(new VideoFrameProcessingEvent((long) processedFrames));
  }
}
