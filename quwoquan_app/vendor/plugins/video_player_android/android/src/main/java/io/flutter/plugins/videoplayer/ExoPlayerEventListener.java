// Copyright 2013 The Flutter Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package io.flutter.plugins.videoplayer;

import android.os.SystemClock;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.OptIn;
import androidx.media3.common.C;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.common.Tracks;
import androidx.media3.exoplayer.analytics.AnalyticsListener;
import androidx.media3.exoplayer.ExoPlayer;

@OptIn(markerClass = UnstableApi.class)
public abstract class ExoPlayerEventListener implements Player.Listener, AnalyticsListener {
  private boolean isInitialized = false;
  private boolean hasEmittedFirstFrame = false;
  private boolean seekDiscontinuitySeen = false;
  private long prepareStartedAtElapsedRealtimeMs = SystemClock.elapsedRealtime();
  @Nullable private Long pendingSeekTargetMs;
  @Nullable private Long pendingSeekStartedAtElapsedRealtimeMs;
  protected final ExoPlayer exoPlayer;
  protected final VideoPlayerCallbacks events;

  protected enum RotationDegrees {
    ROTATE_0(0),
    ROTATE_90(90),
    ROTATE_180(180),
    ROTATE_270(270);

    private final int degrees;

    RotationDegrees(int degrees) {
      this.degrees = degrees;
    }

    public static RotationDegrees fromDegrees(int degrees) {
      for (RotationDegrees rotationDegrees : RotationDegrees.values()) {
        if (rotationDegrees.degrees == degrees) {
          return rotationDegrees;
        }
      }
      throw new IllegalArgumentException("Invalid rotation degrees specified: " + degrees);
    }

    public int getDegrees() {
      return this.degrees;
    }
  }

  public ExoPlayerEventListener(
      @NonNull ExoPlayer exoPlayer, @NonNull VideoPlayerCallbacks events) {
    this.exoPlayer = exoPlayer;
    this.events = events;
  }

  protected abstract void sendInitialized();

  /** Marks that Dart requested a seek; settle requires discontinuity + rendered frame. */
  public void markSeekRequested(long positionMs) {
    pendingSeekTargetMs = positionMs;
    pendingSeekStartedAtElapsedRealtimeMs = SystemClock.elapsedRealtime();
    seekDiscontinuitySeen = false;
  }

  /** Starts the native TTFF interval immediately before ExoPlayer is prepared. */
  public void markPrepareStarted() {
    prepareStartedAtElapsedRealtimeMs = SystemClock.elapsedRealtime();
  }

  @Override
  public void onPlaybackStateChanged(final int playbackState) {
    PlatformPlaybackState platformState = PlatformPlaybackState.UNKNOWN;
    switch (playbackState) {
      case Player.STATE_BUFFERING:
        platformState = PlatformPlaybackState.BUFFERING;
        break;
      case Player.STATE_READY:
        platformState = PlatformPlaybackState.READY;
        if (!isInitialized) {
          isInitialized = true;
          sendInitialized();
        }
        break;
      case Player.STATE_ENDED:
        platformState = PlatformPlaybackState.ENDED;
        break;
      case Player.STATE_IDLE:
        platformState = PlatformPlaybackState.IDLE;
        break;
    }
    events.onPlaybackStateChanged(platformState);
  }

  @Override
  public void onPositionDiscontinuity(
      @NonNull Player.PositionInfo oldPosition,
      @NonNull Player.PositionInfo newPosition,
      int reason) {
    if (reason == Player.DISCONTINUITY_REASON_SEEK && pendingSeekTargetMs != null) {
      seekDiscontinuitySeen = true;
    }
  }

  @Override
  public void onRenderedFirstFrame(
      AnalyticsListener.EventTime eventTime, Object output, long renderTimeMs) {
    handleRenderedFrame(renderTimeMs);
  }

  @Override
  public void onRenderedFirstFrame() {
    handleRenderedFrame(SystemClock.elapsedRealtime());
  }

  private void handleRenderedFrame(long renderedAtElapsedRealtimeMs) {
    if (!hasEmittedFirstFrame) {
      hasEmittedFirstFrame = true;
      events.onRenderedFirstFrame(
          Math.max(0L, renderedAtElapsedRealtimeMs - prepareStartedAtElapsedRealtimeMs));
    }
    if (pendingSeekTargetMs != null
        && pendingSeekStartedAtElapsedRealtimeMs != null
        && seekDiscontinuitySeen) {
      long target = pendingSeekTargetMs;
      long settled = exoPlayer.getCurrentPosition();
      long settleMs =
          Math.max(0L, renderedAtElapsedRealtimeMs - pendingSeekStartedAtElapsedRealtimeMs);
      pendingSeekTargetMs = null;
      pendingSeekStartedAtElapsedRealtimeMs = null;
      seekDiscontinuitySeen = false;
      events.onSeekSettled(target, settled, settleMs);
    }
  }

  @Override
  public void onDroppedVideoFrames(
      AnalyticsListener.EventTime eventTime, int droppedFrames, long elapsedMs) {
    if (droppedFrames > 0) {
      events.onDroppedVideoFrames(droppedFrames, elapsedMs);
    }
  }

  @Override
  public void onAudioUnderrun(
      AnalyticsListener.EventTime eventTime,
      int bufferSize,
      long bufferSizeMs,
      long elapsedSinceLastFeedMs) {
    events.onAudioUnderrun(bufferSize, bufferSizeMs, elapsedSinceLastFeedMs);
  }

  @Override
  public void onVideoFrameProcessingOffset(
      AnalyticsListener.EventTime eventTime, long totalProcessingOffsetUs, int frameCount) {
    if (frameCount > 0) {
      events.onVideoFrameProcessing(frameCount);
    }
  }

  @Override
  public void onPlayerError(@NonNull final PlaybackException error) {
    if (error.errorCode == PlaybackException.ERROR_CODE_BEHIND_LIVE_WINDOW) {
      // See
      // https://exoplayer.dev/live-streaming.html#behindlivewindowexception-and-error_code_behind_live_window
      exoPlayer.seekToDefaultPosition();
      exoPlayer.prepare();
    } else {
      pendingSeekTargetMs = null;
      pendingSeekStartedAtElapsedRealtimeMs = null;
      seekDiscontinuitySeen = false;
      events.onError("VideoError", "Video player had error " + error, null);
    }
  }

  @Override
  public void onIsPlayingChanged(boolean isPlaying) {
    events.onIsPlayingStateUpdate(isPlaying);
  }

  @Override
  public void onTracksChanged(@NonNull Tracks tracks) {
    // Find the currently selected audio track and notify
    String selectedTrackId = findSelectedAudioTrackId(tracks);
    events.onAudioTrackChanged(selectedTrackId);
  }

  /**
   * Finds the ID of the currently selected audio track.
   *
   * @param tracks The current tracks
   * @return The track ID in format "groupIndex_trackIndex", or null if no audio track is selected
   */
  @Nullable
  private String findSelectedAudioTrackId(@NonNull Tracks tracks) {
    int groupIndex = 0;
    for (Tracks.Group group : tracks.getGroups()) {
      if (group.getType() == C.TRACK_TYPE_AUDIO && group.isSelected()) {
        // Find the selected track within this group
        for (int i = 0; i < group.length; i++) {
          if (group.isTrackSelected(i)) {
            return groupIndex + "_" + i;
          }
        }
      }
      groupIndex++;
    }
    return null;
  }
}
