// spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-001

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/runtime/platform/video_player_controller_factory.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_support.dart';
import 'package:video_player/video_player.dart';

void main() {
  group('preferredVideoPlaybackViewType', () {
    test(
      'Android prefers platform view to avoid ImageReader MediaCodec failures',
      () {
        expect(
          preferredVideoPlaybackViewType(AppPlatform.android),
          VideoViewType.platformView,
        );
      },
    );

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

    test('explicit renderer overrides the Android platform-view default', () {
      final controllerHandle = AppVideoPlayerControllerFactory.localFilePath(
        '/tmp/qwq_immersive_video.mp4',
        viewType: VideoViewType.textureView,
      );
      addTearDown(controllerHandle.controller.dispose);

      expect(controllerHandle.controller.viewType, VideoViewType.textureView);
    });

    test('cached and network sources preserve an explicit renderer', () {
      final cached = PlayableVideoSource.cachedFile(
        '/tmp/qwq_immersive_video.mp4',
        viewType: VideoViewType.textureView,
      ).createController();
      final network = PlayableVideoSource.network(
        Uri.parse('https://cdn.alpha.quwoquan.com/video.mp4'),
        viewType: VideoViewType.textureView,
      ).createController();
      addTearDown(cached.controller.dispose);
      addTearDown(network.controller.dispose);

      expect(cached.controller.viewType, VideoViewType.textureView);
      expect(network.controller.viewType, VideoViewType.textureView);
    });

    test(
      'Android platform view binds only valid live surfaces and reattaches on visibility',
      () {
        final source = _readAppFile(
          'vendor/plugins/video_player_android/android/src/main/java/'
          'io/flutter/plugins/videoplayer/platformview/PlatformVideoView.java',
        );

        expect(source, contains('setupSurfaceWithCallback(exoPlayer);'));
        expect(source, contains('if (surface.isValid())'));
        expect(source, contains('exoPlayer.setVideoSurface(surface);'));
        expect(
          source,
          contains('exoPlayer.clearVideoSurface(holder.getSurface());'),
        );
        expect(source, contains('visibility == View.VISIBLE && isShown()'));
        expect(
          source,
          isNot(contains('exoPlayer.setVideoSurfaceView(surfaceView);')),
        );
        expect(source, isNot(contains('getSurface().release()')));
      },
    );
  });
}

String _readAppFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct.readAsStringSync();
  }
  return File('quwoquan_app/$relativePath').readAsStringSync();
}
