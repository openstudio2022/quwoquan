// Copyright 2013 The Flutter Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// quwoquan fork: enable Media3 decoder fallback + sync codec queueing for OEM
// MediaCodec init failures (e.g. Huawei Hisilicon OMX.hisi + ImageReader).

package io.flutter.plugins.videoplayer;

import android.content.Context;
import androidx.annotation.NonNull;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.exoplayer.DefaultRenderersFactory;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.trackselection.DefaultTrackSelector;

/** Shared ExoPlayer construction with multi-device decoder compatibility defaults. */
public final class ExoPlayerFactory {
  private ExoPlayerFactory() {}

  // TODO: Migrate to stable API, see https://github.com/flutter/flutter/issues/147039.
  @UnstableApi
  @NonNull
  public static ExoPlayer create(@NonNull Context context, @NonNull VideoAsset asset) {
    DefaultTrackSelector trackSelector = new DefaultTrackSelector(context);
    DefaultRenderersFactory renderersFactory =
        new DefaultRenderersFactory(context)
            // Try secondary / software decoders when the primary HW decoder fails to init.
            .setEnableDecoderFallback(true)
            // Async MediaCodec adapters are brittle on some OEM stacks (Huawei Hisilicon).
            .forceDisableMediaCodecAsynchronousQueueing();
    return new ExoPlayer.Builder(context, renderersFactory)
        .setTrackSelector(trackSelector)
        .setMediaSourceFactory(asset.getMediaSourceFactory(context))
        .build();
  }
}
