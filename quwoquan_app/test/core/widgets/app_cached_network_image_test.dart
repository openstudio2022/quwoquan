import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

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
        'http://127.0.0.1:17100/media/background/s/archived-avatar/user/fixture_user_current/v1/background.png',
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
          'http://127.0.0.1:17100/media/image/s/archived-image/post/fixture_',
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
