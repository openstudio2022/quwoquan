import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/trackers/feed_performance_observability.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

void main() {
  group('home feed long-scroll performance acceptance', () {
    test('declares the resource plateau metrics required by device UAT', () {
      expect(
        FeedPerformanceMetricNames.frameJankRatio,
        'home_feed_frame_jank_ratio',
      );
      expect(
        FeedPerformanceMetricNames.imageCacheBytes,
        'home_feed_image_cache_bytes',
      );
      expect(
        FeedPerformanceMetricNames.activeVideoControllerCount,
        'home_feed_active_video_controller_count',
      );
      expect(
        FeedPerformanceMetricNames.mediaDownloadQueue,
        'home_feed_media_download_queue',
      );
      expect(
        FeedPerformanceMetricNames.postCacheHitSource,
        'home_feed_post_cache_hit_source',
      );
    });

    test('compact profile is strict enough for low-memory long-scroll UAT', () {
      expect(
        AppResourceCacheProfile.compact.maxImageCacheBytes,
        64 * 1024 * 1024,
      );
      expect(AppResourceCacheProfile.compact.maxMediaDownloadCacheSizeMb, 96);
      expect(AppResourceCacheProfile.compact.maxConcurrentMediaDownloads, 2);
      expect(AppResourceCacheProfile.compact.maxPostObjectCacheEntries, 120);
    });

    test('implementation has bounded video and media queue cleanup hooks', () {
      final root = _repoRoot();
      final worksCanvas = File(
        '$root/quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_canvas.dart',
      ).readAsStringSync();
      expect(worksCanvas, contains('_pruneControllerRegistry'));
      expect(worksCanvas, contains('keepAlive: keepAlive'));
      expect(worksCanvas, contains('widget.keepAlive'));

      final mediaDownloadCache = File(
        '$root/quwoquan_app/lib/cloud/media/media_download_cache.dart',
      ).readAsStringSync();
      expect(mediaDownloadCache, contains('inflightDownloadCount'));
      expect(mediaDownloadCache, contains('cancelQueuedPrefetches'));
    });
  });
}

String _repoRoot() {
  final direct = Directory.current;
  if (File('${direct.path}/quwoquan_app/pubspec.yaml').existsSync()) {
    return direct.path;
  }
  return direct.parent.path;
}
