// Copyright 2013 The Flutter Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package io.flutter.plugins.videoplayer;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

/**
 * Callbacks representing events invoked by {@link VideoPlayer}.
 *
 * <p>In the actual plugin, this will always be {@link VideoPlayerEventCallbacks}, which creates the
 * expected events to send back through the plugin channel. In tests methods can be overridden in
 * order to assert results.
 *
 * <p>See {@link androidx.media3.common.Player.Listener} for details.
 */
public interface VideoPlayerCallbacks {
  void onInitialized(int width, int height, long durationInMs, int rotationCorrectionInDegrees);

  void onPlaybackStateChanged(@NonNull PlatformPlaybackState state);

  void onError(@NonNull String code, @Nullable String message, @Nullable Object details);

  void onIsPlayingStateUpdate(boolean isPlaying);

  void onAudioTrackChanged(@Nullable String selectedTrackId);

  /** Reports the renderer configuration without exposing device identifiers. */
  void onPlaybackDiagnostics(
      @NonNull String rendererMode,
      @NonNull String decoderQueueMode,
      boolean decoderFallbackEnabled);

  /** Emitted once when ExoPlayer renders the first video frame. */
  void onRenderedFirstFrame(long ttffMs);

  /**
   * Emitted when a seek has both discontinuity and a subsequent rendered frame.
   *
   * @param targetPositionMs requested seek target
   * @param settledPositionMs position observed when the settle frame rendered
   * @param settleMs elapsed time from the seek request to that frame
   */
  void onSeekSettled(long targetPositionMs, long settledPositionMs, long settleMs);

  /** Reports an actual renderer dropped-frame batch. */
  void onDroppedVideoFrames(int droppedFrames, long elapsedMs);

  /** Reports an actual audio output underrun. */
  void onAudioUnderrun(int bufferSize, long bufferSizeMs, long elapsedSinceLastFeedMs);

  /** Reports processed-frame samples for dropped-frame-ratio aggregation. */
  void onVideoFrameProcessing(int processedFrames);
}
