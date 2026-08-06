import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/runtime/platform/video_player_controller_factory.dart';
import 'package:video_player/video_player.dart';

void main() {
  group('preferredVideoPlaybackViewType', () {
    test('Android prefers platform view to avoid ImageReader MediaCodec failures', () {
      expect(
        preferredVideoPlaybackViewType(AppPlatform.android),
        VideoViewType.platformView,
      );
    });

    test('non-Android platforms keep texture view', () {
      expect(
        preferredVideoPlaybackViewType(AppPlatform.ios),
        VideoViewType.textureView,
      );
      expect(
        preferredVideoPlaybackViewType(AppPlatform.web),
        VideoViewType.textureView,
      );
    });
  });
}
