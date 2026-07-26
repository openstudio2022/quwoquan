// Copyright 2013 The Flutter Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// quwoquan fork: Media3 decoder fallback + synchronous MediaCodec queueing as
// the default for ALL Android devices (early API, low-memory, software decoder
// and brittle OEM stacks). Do not introduce brand/model allowlists.

package io.flutter.plugins.videoplayer;

import android.content.Context;
import androidx.annotation.NonNull;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.exoplayer.DefaultRenderersFactory;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.trackselection.DefaultTrackSelector;

/** Shared ExoPlayer construction with broad early/low-end device defaults. */
public final class ExoPlayerFactory {
  /** Stable, low-cardinality value emitted in playback diagnostics. */
  public static final String DECODER_QUEUE_MODE_SYNCHRONOUS = "synchronous";

  /** Decoder fallback is enabled for every Android player, not a device subset. */
  public static final boolean DECODER_FALLBACK_ENABLED = true;

  private ExoPlayerFactory() {}

  // TODO: Migrate to stable API, see https://github.com/flutter/flutter/issues/147039.
  @UnstableApi
  @NonNull
  public static ExoPlayer create(@NonNull Context context, @NonNull VideoAsset asset) {
    DefaultTrackSelector trackSelector = new DefaultTrackSelector(context);
    DefaultRenderersFactory renderersFactory =
        new DefaultRenderersFactory(context)
            // Prefer a working secondary/software decoder over hard failing init.
            .setEnableDecoderFallback(DECODER_FALLBACK_ENABLED)
            // Sync MediaCodec queueing is the safer default across early/low-end
            // and OEM stacks; do not gate this behind brand/model branches.
            .forceDisableMediaCodecAsynchronousQueueing();
    return new ExoPlayer.Builder(context, renderersFactory)
        .setTrackSelector(trackSelector)
        .setMediaSourceFactory(asset.getMediaSourceFactory(context))
        .build();
  }
}
