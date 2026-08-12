// Copyright 2013 The Flutter Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package io.flutter.plugins.videoplayer;

import static org.junit.Assert.assertNotNull;
import static org.mockito.Mockito.*;

import android.content.Context;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.test.core.app.ApplicationProvider;
import io.flutter.plugins.videoplayer.platformview.PlatformVideoView;
import java.lang.reflect.Field;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;

/** Unit tests for {@link PlatformVideoViewTest}. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = 35)
public class PlatformVideoViewTest {
  @Test
  public void bindsOnlyAfterFrameworkSurfaceIsCreatedAndValid() throws Exception {
    final Context context = ApplicationProvider.getApplicationContext();
    final ExoPlayer exoPlayer = spy(new ExoPlayer.Builder(context).build());

    final PlatformVideoView view = new PlatformVideoView(context, exoPlayer);
    final SurfaceView surfaceView = surfaceViewOf(view);
    assertNotNull(surfaceView);
    verify(exoPlayer, never()).setVideoSurfaceView(any(SurfaceView.class));

    final SurfaceHolder holder = mock(SurfaceHolder.class);
    final Surface surface = mock(Surface.class);
    when(holder.getSurface()).thenReturn(surface);
    when(surface.isValid()).thenReturn(true);
    surfaceCallbackOf(view).surfaceCreated(holder);

    verify(exoPlayer).setVideoSurface(surface);

    exoPlayer.release();
  }

  @Test
  public void ignoresInvalidSurfaceAndClearsOnlyDestroyedSurface() throws Exception {
    final Context context = ApplicationProvider.getApplicationContext();
    final ExoPlayer exoPlayer = spy(new ExoPlayer.Builder(context).build());
    final PlatformVideoView view = new PlatformVideoView(context, exoPlayer);
    final SurfaceHolder.Callback callback = surfaceCallbackOf(view);
    final SurfaceHolder holder = mock(SurfaceHolder.class);
    final Surface surface = mock(Surface.class);
    when(holder.getSurface()).thenReturn(surface);
    when(surface.isValid()).thenReturn(false);

    callback.surfaceCreated(holder);
    verify(exoPlayer, never()).setVideoSurface(surface);

    callback.surfaceDestroyed(holder);
    verify(exoPlayer).clearVideoSurface(surface);
    verify(exoPlayer, never()).setVideoSurface(null);

    exoPlayer.release();
  }

  @Test
  public void disposeDetachesFrameworkOwnedSurfaceAndIsIdempotent() throws Exception {
    final Context context = ApplicationProvider.getApplicationContext();
    final ExoPlayer exoPlayer = spy(new ExoPlayer.Builder(context).build());
    final PlatformVideoView view = new PlatformVideoView(context, exoPlayer);

    view.dispose();
    view.dispose();

    verify(exoPlayer, times(1)).clearVideoSurface(nullable(Surface.class));
    verify(exoPlayer, never()).clearVideoSurfaceView(any(SurfaceView.class));
    verify(exoPlayer, never()).setVideoSurface(null);

    exoPlayer.release();
  }

  private static SurfaceView surfaceViewOf(PlatformVideoView view) throws Exception {
    final Field field = PlatformVideoView.class.getDeclaredField("surfaceView");
    field.setAccessible(true);
    return (SurfaceView) field.get(view);
  }

  private static SurfaceHolder.Callback surfaceCallbackOf(PlatformVideoView view)
      throws Exception {
    final Field field = PlatformVideoView.class.getDeclaredField("surfaceCallback");
    field.setAccessible(true);
    return (SurfaceHolder.Callback) field.get(view);
  }
}
