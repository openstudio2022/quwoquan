# video_player_android (quwoquan fork)

Vendored from upstream `video_player_android` **2.9.6**.

## Local changes

- `ExoPlayerFactory.java`: Media3 `DefaultRenderersFactory`
  - `setEnableDecoderFallback(true)` — try secondary/software decoders when primary HW init fails
  - `forceDisableMediaCodecAsynchronousQueueing()` — **default for all Android devices** to cover early API, low-memory and brittle OEM stacks; do **not** introduce brand/model allowlists
- `TextureVideoPlayer` / `PlatformViewVideoPlayer` build ExoPlayer via `ExoPlayerFactory`
- `ExoPlayerEventListener` + pigeon events:
  - `RenderedFirstFrameEvent` — native prepare-to-frame TTFF (not controller initialize)
  - `SeekSettledEvent` — seek discontinuity + subsequent native rendered frame
  - dropped-frame, processed-frame and audio-underrun events — real Media3 analytics evidence
  - renderer/queue/fallback diagnostics — low-cardinality configuration only; never a device fingerprint
- `PlatformVideoView.dispose()` detaches ExoPlayer from the framework-owned `SurfaceView` surface without releasing that surface directly, preventing buffer-ownership races on early/low-end devices

Do not drop these defaults without re-validating Android video on the lowest supported API and low-memory physical devices in the commercial matrix.
