import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/media/app_image_cache_controller.dart';
import 'package:quwoquan_app/runtime/config/app_video_runtime_budget.dart';

void main() {
  group('home feed resource budgets', () {
    test('compact profile stays within low-memory candidate budgets', () {
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

    test('player and typed resource telemetry share one controller limit', () {
      expect(AppVideoRuntimeBudget.maxConcurrentControllers, 2);
    });
  });
}
