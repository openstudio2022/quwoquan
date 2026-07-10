import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

import '../../../support/sqflite_ffi_test_support.dart';

Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: CupertinoApp(
      home: CupertinoPageScaffold(child: Center(child: child)),
    ),
  );
}

class _CapturingAnalyticsService extends AnalyticsService {
  _CapturingAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}

class _FakePathProviderPlatform extends PathProviderPlatform {
  _FakePathProviderPlatform(this.root);

  final Directory root;

  String _path(String name) {
    final directory = Directory('${root.path}/$name')
      ..createSync(recursive: true);
    return directory.path;
  }

  @override
  Future<String?> getTemporaryPath() async => _path('tmp');

  @override
  Future<String?> getApplicationSupportPath() async => _path('support');

  @override
  Future<String?> getApplicationDocumentsPath() async => _path('documents');

  @override
  Future<String?> getApplicationCachePath() async => _path('cache');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory cacheTestRoot;
  late PathProviderPlatform previousPathProvider;

  setUpAll(() {
    ensureSqfliteFfiInitialized();
    previousPathProvider = PathProviderPlatform.instance;
    cacheTestRoot = Directory.systemTemp.createTempSync(
      'qwq-app-image-cache-test-',
    );
    PathProviderPlatform.instance = _FakePathProviderPlatform(cacheTestRoot);
  });

  tearDownAll(() {
    PathProviderPlatform.instance = previousPathProvider;
    if (cacheTestRoot.existsSync()) {
      cacheTestRoot.deleteSync(recursive: true);
    }
  });

  group('AppCachedNetworkImage', () {
    test('maps CDN presets to bounded cache tiers', () {
      expect(
        AppImageCacheController.cacheTierForPreset(CdnImagePreset.avatar),
        AppImageCacheTier.avatar,
      );
      expect(
        AppImageCacheController.cacheTierForPreset(CdnImagePreset.thumbnail),
        AppImageCacheTier.preview,
      );
      expect(
        AppImageCacheController.cacheTierForPreset(CdnImagePreset.cover),
        AppImageCacheTier.preview,
      );
      expect(
        AppImageCacheController.cacheTierForPreset(CdnImagePreset.inline),
        AppImageCacheTier.ephemeral,
      );
      expect(
        AppImageCacheController.cacheTierForPreset(CdnImagePreset.full),
        AppImageCacheTier.ephemeral,
      );
    });

    test('applies adaptive Flutter ImageCache profile', () {
      final imageCache = PaintingBinding.instance.imageCache;
      final previousSize = imageCache.maximumSize;
      final previousBytes = imageCache.maximumSizeBytes;
      addTearDown(() {
        imageCache.maximumSize = previousSize;
        imageCache.maximumSizeBytes = previousBytes;
      });

      AppImageCacheController.applyResourceProfile(
        AppResourceCacheProfile.compact,
      );

      expect(imageCache.maximumSize, 300);
      expect(imageCache.maximumSizeBytes, 64 * 1024 * 1024);
    });

    test('uses image-aware cache managers for disk resize surfaces', () {
      for (final preset in CdnImagePreset.values) {
        expect(
          AppImageCacheController.cacheManagerForPreset(preset),
          isA<ImageCacheManager>(),
          reason:
              'CachedNetworkImage requires ImageCacheManager when '
              'maxWidthDiskCache/maxHeightDiskCache are set.',
        );
      }
    });

    testWidgets('sets bounded disk resize only through image cache managers', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const AppCachedNetworkImage(
            imageUrl: 'media/avatar/s/mock/user/current/v1/avatar.png',
            width: 64,
            height: 64,
            cdnPreset: CdnImagePreset.avatar,
          ),
        ),
      );

      final image = tester.widget<CachedNetworkImage>(
        find.byType(CachedNetworkImage),
      );
      final physicalExtent = (64 * tester.view.devicePixelRatio).round();
      expect(image.cacheManager, isA<ImageCacheManager>());
      expect(image.maxWidthDiskCache, physicalExtent);
      expect(image.maxHeightDiskCache, physicalExtent);
    });

    testWidgets(
      'derives memory decode size from layout and caps large images',
      (tester) async {
        await tester.binding.setSurfaceSize(const Size(3200, 2600));
        addTearDown(() => tester.binding.setSurfaceSize(null));

        await tester.pumpWidget(
          _wrap(
            const SizedBox(
              width: 3000,
              height: 2500,
              child: AppCachedNetworkImage(
                imageUrl: 'media/image/s/archived-image/post/p1/v1/cover.png',
                cdnPreset: CdnImagePreset.cover,
              ),
            ),
          ),
        );

        final image = tester.widget<CachedNetworkImage>(
          find.byType(CachedNetworkImage),
        );
        expect(image.memCacheWidth, appImageDecodeMaxPhysicalExtent);
        expect(image.memCacheHeight, appImageDecodeMaxPhysicalExtent);
        expect(image.maxWidthDiskCache, appImageDecodeMaxPhysicalExtent);
        expect(image.maxHeightDiskCache, appImageDecodeMaxPhysicalExtent);
      },
    );

    testWidgets('auto resolves raw background media object keys', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const AppCachedNetworkImage(
            imageUrl:
                'media/background/s/archived-avatar/user/fixture_user_current/v1/background.png',
          ),
        ),
      );

      final image = tester.widget<CachedNetworkImage>(
        find.byType(CachedNetworkImage),
      );
      expect(
        image.imageUrl,
        'https://localhost:17100/media/background/s/archived-avatar/user/fixture_user_current/v1/background.png',
      );
    });

    testWidgets('auto rewrites archived mock seed images before load', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          const AppCachedNetworkImage(
            imageUrl:
                'media/image/s/mock/seed/p_1501785888041-af3ef285b470/v1/image.jpg',
          ),
        ),
      );

      final image = tester.widget<CachedNetworkImage>(
        find.byType(CachedNetworkImage),
      );
      expect(
        image.imageUrl,
        startsWith(
          'https://localhost:17100/media/image/s/archived-image/post/fixture_',
        ),
      );
      expect(image.imageUrl, isNot(contains('/mock/seed/')));
    });

    testWidgets(
      'empty image candidates show local failure and emit media state',
      (tester) async {
        final analytics = _CapturingAnalyticsService();
        var failedCount = 0;

        await tester.pumpWidget(
          _wrap(
            AppCachedNetworkImage(
              imageUrl: '',
              onLoadFailed: (_) => failedCount += 1,
            ),
            overrides: [analyticsProvider.overrideWithValue(analytics)],
          ),
        );
        await tester.pump();

        expect(find.text(UITextConstants.imageLoadFailed), findsOneWidget);
        expect(failedCount, 1);
        expect(analytics.events, hasLength(1));
        final event = analytics.events.single;
        expect(event.eventName, 'media_load_state');
        expect(event.properties['mediaType'], 'image');
        expect(event.properties['result'], 'failure');
        expect(event.properties['copyKey'], 'imageLoadFailed');
        expect(event.properties['candidatesTried'], 0);
      },
    );
  });
}
