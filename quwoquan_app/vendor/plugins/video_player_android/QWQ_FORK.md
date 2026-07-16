# video_player_android (quwoquan fork)

Vendored from upstream `video_player_android` **2.9.6**.

## Local changes

- `ExoPlayerFactory.java`: Media3 `DefaultRenderersFactory`
  - `setEnableDecoderFallback(true)` — try secondary/software decoders when primary HW init fails (Huawei Hisilicon / MediaTek / etc.)
  - `forceDisableMediaCodecAsynchronousQueueing()` — avoid brittle async MediaCodec adapters on OEM stacks
- `TextureVideoPlayer` / `PlatformViewVideoPlayer` build ExoPlayer via `ExoPlayerFactory`

Do not drop this override without re-validating Android video on Huawei Kirin devices (ELS-AN00 class).
