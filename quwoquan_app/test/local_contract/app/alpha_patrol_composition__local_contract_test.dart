import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:test/test.dart';

import '../../support/cloud_services/repository_mock_reexports.dart'
    show buildAlphaCloudOverrides;

void main() {
  test(
    'Alpha Patrol uses the runner composition and preserves v1 video wire',
    () async {
      final container = ProviderContainer(
        overrides: buildAlphaCloudOverrides(),
      );
      addTearDown(container.dispose);

      final reader = container.read(workBrowserContentPostDetailReaderProvider);
      final payload = await reader.getPost(postId: 'v1');
      final post = payload.post;

      expect(post, isA<VideoPostDto>());
      final video = post as VideoPostDto;
      expect(video.mediaAssetId, 'media-canary-seek-125s');
      expect(video.durationMs, 125000);
      expect(
        video.previewTrackManifestUrl,
        'media/video/s/media-canary-seek-125s/v1/preview/manifest.json',
      );
    },
  );
}
