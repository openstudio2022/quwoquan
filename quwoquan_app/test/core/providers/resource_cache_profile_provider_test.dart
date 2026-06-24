import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

void main() {
  group('appResourceCacheProfileProvider', () {
    test('mobile and ohos stay on compact budget even on large windows', () {
      for (final profile in <PlatformCapabilities>[
        CapabilityProfile.mobile,
        CapabilityProfile.ohos,
      ]) {
        final container = ProviderContainer(
          overrides: [platformCapabilitiesProvider.overrideWithValue(profile)],
        );
        addTearDown(container.dispose);

        container
            .read(responsiveProvider.notifier)
            .updateFromSize(const Size(834, 1194));

        expect(
          container.read(appResourceCacheProfileProvider),
          same(AppResourceCacheProfile.compact),
        );
        final resourceProfile = container.read(appResourceCacheProfileProvider);
        expect(resourceProfile.maxMediaDownloadCacheSizeMb, 96);
        expect(resourceProfile.maxConcurrentMediaDownloads, 2);
        expect(resourceProfile.maxPostObjectCacheEntries, 120);
      }
    });

    test('wide-screen capability scales from regular to expanded', () {
      final container = ProviderContainer(
        overrides: [
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.desktop,
          ),
        ],
      );
      addTearDown(container.dispose);

      container
          .read(responsiveProvider.notifier)
          .updateFromSize(const Size(390, 844));
      expect(
        container.read(appResourceCacheProfileProvider),
        same(AppResourceCacheProfile.regular),
      );
      expect(
        container
            .read(appResourceCacheProfileProvider)
            .maxConcurrentMediaDownloads,
        3,
      );

      container
          .read(responsiveProvider.notifier)
          .updateFromSize(const Size(900, 900));
      expect(
        container.read(appResourceCacheProfileProvider),
        same(AppResourceCacheProfile.expanded),
      );
      expect(
        container
            .read(appResourceCacheProfileProvider)
            .maxMediaDownloadCacheSizeMb,
        384,
      );
    });
  });
}
