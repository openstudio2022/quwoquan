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
      expect(
        AppResourceCacheProfile.compact.usesCompactScrollMediaPolicy,
        true,
      );
      expect(
        AppResourceCacheProfile.compact.feedCacheExtentForViewport(800),
        400,
      );
      expect(
        AppResourceCacheProfile.regular.feedCacheExtentForViewport(800),
        800,
      );
    });

    test('implementation has bounded video and media queue cleanup hooks', () {
      final root = _repoRoot();
      final worksCanvas = File(
        '$root/quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_canvas.dart',
      ).readAsStringSync();
      // 相邻页只允许 Flutter 预布局；真正的 controller/session 仍由
      // isCurrent + _KeepAliveStage 双门约束为 N+1 有界集合。
      expect(worksCanvas, contains('allowImplicitScrolling: true'));
      expect(worksCanvas, contains('final keepAlive = shouldInitialize'));
      expect(worksCanvas, contains('_KeepAliveStage('));

      final mediaDownloadCache = File(
        '$root/quwoquan_app/lib/cloud/media/media_download_cache.dart',
      ).readAsStringSync();
      expect(mediaDownloadCache, contains('inflightDownloadCount'));
      expect(mediaDownloadCache, contains('cancelQueuedPrefetches'));
    });

    test('implementation uses bounded layout and decode policies', () {
      final root = _repoRoot();
      final imageWidget = File(
        '$root/quwoquan_app/lib/core/widgets/app_cached_network_image.dart',
      ).readAsStringSync();
      expect(imageWidget, contains('appImageDecodeMaxPhysicalExtent = 2048'));
      expect(imageWidget, contains('LayoutBuilder('));
      expect(imageWidget, contains('_effectiveLogicalExtent'));

      final feedScroll = File(
        '$root/quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_scroll.dart',
      ).readAsStringSync();
      expect(feedScroll, contains('scrollCacheExtent: cacheExtent'));
      expect(feedScroll, contains('ScrollCacheExtent.viewport'));
      expect(feedScroll, contains('feedCacheExtentViewportMultiplier'));

      final mediaGrid = File(
        '$root/quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_media_grid.dart',
      ).readAsStringSync();
      expect(mediaGrid, isNot(contains('GridView.builder(')));
      expect(mediaGrid, contains('class _HomeMomentGridTile'));
      expect(mediaGrid, contains('Positioned('));
    });

    test('embedded profile and homepage grids avoid shrinkWrap masonry', () {
      final root = _repoRoot();
      final profileWorks = File(
        '$root/quwoquan_app/lib/ui/user/widgets/profile_works_tab.dart',
      ).readAsStringSync();
      final homepageDetail = File(
        '$root/quwoquan_app/lib/ui/entity/widgets/homepage_detail_shell.dart',
      ).readAsStringSync();
      final circleCreations = File(
        '$root/quwoquan_app/lib/ui/circle/widgets/section_creations_state_helpers.dart',
      ).readAsStringSync();

      expect(profileWorks, isNot(contains('MasonryGridView.count')));
      expect(homepageDetail, isNot(contains('MasonryGridView.count')));
      expect(circleCreations, contains('GridView.builder('));
      expect(circleCreations, contains('shrinkWrap: false'));
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
