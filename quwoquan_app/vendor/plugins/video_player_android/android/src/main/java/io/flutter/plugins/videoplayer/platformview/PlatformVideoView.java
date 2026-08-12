// Copyright 2013 The Flutter Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package io.flutter.plugins.videoplayer.platformview;

import android.content.Context;
import android.os.Build;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.OptIn;
import androidx.annotation.VisibleForTesting;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.exoplayer.ExoPlayer;
import io.flutter.plugin.platform.PlatformView;

/**
 * A class used to create a native video view that can be embedded in a Flutter app. It wraps an
 * {@link ExoPlayer} instance and displays its video content.
 */
public final class PlatformVideoView implements PlatformView {
  @NonNull private final SurfaceView surfaceView;
  @NonNull private final ExoPlayer exoPlayer;
  @Nullable private SurfaceHolder.Callback surfaceCallback;
  private boolean disposed = false;

  /**
   * Constructs a new PlatformVideoView.
   *
   * @param context The context in which the view is running.
   * @param exoPlayer The ExoPlayer instance used to play the video.
   */
  @OptIn(markerClass = UnstableApi.class)
  public PlatformVideoView(@NonNull Context context, @NonNull ExoPlayer exoPlayer) {
    this.exoPlayer = exoPlayer;
    surfaceView = new VideoSurfaceView(context, exoPlayer);

    setupSurfaceWithCallback(exoPlayer);
    if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.N_MR1) {
      // Avoid blank space instead of a video on Android versions below 8 by adjusting video's
      // z-layer within the Android view hierarchy:
      surfaceView.setZOrderMediaOverlay(true);
    }
  }

  private void setupSurfaceWithCallback(@NonNull ExoPlayer exoPlayer) {
    surfaceCallback =
        new SurfaceHolder.Callback() {
          @Override
          public void surfaceCreated(@NonNull SurfaceHolder holder) {
            if (disposed) {
              return;
            }
            bindPlayerToSurface(exoPlayer, holder.getSurface());
            forceFirstFrameForAndroid9(exoPlayer);
          }

          @Override
          public void surfaceChanged(
              @NonNull SurfaceHolder holder, int format, int width, int height) {
            // No implementation needed.
          }

          @Override
          public void surfaceDestroyed(@NonNull SurfaceHolder holder) {
            if (!disposed) {
              // Do not clear a newer surface installed during a visibility transition.
              exoPlayer.clearVideoSurface(holder.getSurface());
            }
          }
        };
    surfaceView.getHolder().addCallback(surfaceCallback);
  }

  /** Binds only a live framework-owned surface to the decoder. */
  @VisibleForTesting
  static void bindPlayerToSurface(@NonNull ExoPlayer exoPlayer, @NonNull Surface surface) {
    if (surface.isValid()) {
      exoPlayer.setVideoSurface(surface);
    }
  }

  /** Forces Android 9 to flush a paused decoder after a surface handoff. */
  @VisibleForTesting
  static void forceFirstFrameForAndroid9(@NonNull ExoPlayer exoPlayer) {
    if (Build.VERSION.SDK_INT == Build.VERSION_CODES.P && !exoPlayer.getPlayWhenReady()) {
      long position = exoPlayer.getCurrentPosition();
      exoPlayer.seekTo(position == 0 ? 1 : position);
    }
  }

  /**
   * Re-attaches the current surface after a route or platform-view visibility transition.
   *
   * <p>Platform views can become visible without receiving a new {@code surfaceCreated} callback.
   * Binding here prevents a stale decoder surface from advancing playback behind a black frame.
   */
  private final class VideoSurfaceView extends SurfaceView {
    @NonNull private final ExoPlayer player;

    VideoSurfaceView(@NonNull Context context, @NonNull ExoPlayer player) {
      super(context);
      this.player = player;
    }

    @Override
    protected void onVisibilityChanged(@NonNull View changedView, int visibility) {
      super.onVisibilityChanged(changedView, visibility);
      if (!disposed && visibility == View.VISIBLE && isShown()) {
        bindPlayerToSurface(player, getHolder().getSurface());
      }
    }
  }

  /**
   * Returns the view associated with this PlatformView.
   *
   * @return The SurfaceView used to display the video.
   */
  @NonNull
  @Override
  public View getView() {
    return surfaceView;
  }

  /**
   * Detaches the player before the framework-owned surface is destroyed.
   *
   * <p>Order matters on early/low-end devices: clearing the player surface first avoids
   * "client returned a buffer it does not own" races during dispose/seek teardown. The
   * SurfaceView owns its Surface, so this class must never release it directly.
   */
  @Override
  public void dispose() {
    if (disposed) {
      return;
    }
    disposed = true;
    if (surfaceCallback != null) {
      surfaceView.getHolder().removeCallback(surfaceCallback);
      surfaceCallback = null;
    }
    exoPlayer.clearVideoSurface(surfaceView.getHolder().getSurface());
  }
}
