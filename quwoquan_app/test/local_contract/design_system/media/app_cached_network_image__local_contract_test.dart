import 'dart:io';
import 'dart:typed_data';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/transport/media/cdn_media_url_processor.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';

import '../../../support/runtime/observability/recording_app_telemetry_recorder.dart';
import '../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';

// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/spec.md#gwt-002.t3

final MediaEndpointConfig _testMediaEndpointConfig = MediaEndpointConfig(
  avatarBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/avatar',
  imageBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/image',
  videoBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/video',
  attachmentBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/image',
);

Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: [
      mediaEndpointConfigProvider.overrideWithValue(_testMediaEndpointConfig),
      ...overrides,
    ],
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

final Uint8List _transparentImage = Uint8List.fromList(<int>[
  0x89,
  0x50,
  0x4E,
  0x47,
  0x0D,
  0x0A,
  0x1A,
  0x0A,
  0x00,
  0x00,
  0x00,
  0x0D,
  0x49,
  0x48,
  0x44,
  0x52,
  0x00,
  0x00,
  0x00,
  0x01,
  0x00,
  0x00,
  0x00,
  0x01,
  0x08,
  0x06,
  0x00,
  0x00,
  0x00,
  0x1F,
  0x15,
  0xC4,
  0x89,
  0x00,
  0x00,
  0x00,
  0x0A,
  0x49,
  0x44,
  0x41,
  0x54,
  0x78,
  0x9C,
  0x62,
  0x00,
  0x00,
  0x00,
  0x02,
  0x00,
  0x01,
  0xE5,
  0x27,
  0xDE,
  0xFC,
  0x00,
  0x00,
  0x00,
  0x00,
  0x49,
  0x45,
  0x4E,
  0x44,
  0xAE,
  0x42,
  0x60,
  0x82,
]);

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
    try {
      if (cacheTestRoot.existsSync()) {
        cacheTestRoot.deleteSync(recursive: true);
      }
    } on FileSystemException catch (error) {
      if (error.osError?.errorCode != 2) {
        rethrow;
      }
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

    test('evictAvatar 只驱逐原 URL 的登录头像缓存', () async {
      const target = 'media/avatar/s/mock/user/current/v1/avatar.png';
      const untouched = 'media/avatar/s/mock/user/other/v1/avatar.png';
      final targetCacheKeys =
          resolveAvatarImageUrlCandidates(
                target,
                endpointConfig: _testMediaEndpointConfig,
              )
              .map(
                (candidate) => CdnMediaUrlProcessor.avatar(
                  candidate,
                  size: AppSpacing.loginAvatarSize.toInt(),
                ),
              )
              .toSet();
      final untouchedCacheKeys =
          resolveAvatarImageUrlCandidates(
                untouched,
                endpointConfig: _testMediaEndpointConfig,
              )
              .map(
                (candidate) => CdnMediaUrlProcessor.avatar(
                  candidate,
                  size: AppSpacing.loginAvatarSize.toInt(),
                ),
              )
              .toSet();
      expect(targetCacheKeys, isNotEmpty);
      expect(untouchedCacheKeys, isNotEmpty);
      final manager = AppImageCacheController.cacheManagerForPreset(
        CdnImagePreset.avatar,
      );
      for (final cacheKey in targetCacheKeys) {
        await manager.putFile(cacheKey, _transparentImage);
      }
      for (final cacheKey in untouchedCacheKeys) {
        await manager.putFile(cacheKey, _transparentImage);
      }

      await AppImageCacheController.evictAvatar(
        target,
        size: AppSpacing.loginAvatarSize,
        endpointConfig: _testMediaEndpointConfig,
      );

      for (final cacheKey in targetCacheKeys) {
        expect(await manager.getFileFromCache(cacheKey), isNull);
      }
      for (final cacheKey in untouchedCacheKeys) {
        expect(await manager.getFileFromCache(cacheKey), isNotNull);
        await manager.removeFile(cacheKey);
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
            imageUrl: 'media/background/s/archived-avatar/user/fixture_user_current/v1/background.png',
          ),
        ),
      );

      final image = tester.widget<CachedNetworkImage>(
        find.byType(CachedNetworkImage),
      );
      const objectKey =
          'media/background/s/archived-avatar/user/fixture_user_current/v1/background.png';
      expect(
        image.imageUrl,
        _testMediaEndpointConfig
            .baseFor(MediaDeliveryKind.image)
            .replace(path: '/$objectKey')
            .toString(),
      );
    });

    testWidgets('resolves canonical published image without path duplication', (
      tester,
    ) async {
      const objectKey =
          'media/image/s/archived-image/post/release-post-1/v1/image.jpg';
      await tester.pumpWidget(
        _wrap(const AppCachedNetworkImage(imageUrl: objectKey)),
      );

      final image = tester.widget<CachedNetworkImage>(
        find.byType(CachedNetworkImage),
      );
      expect(
        image.imageUrl,
        _testMediaEndpointConfig
            .baseFor(MediaDeliveryKind.image)
            .replace(path: '/$objectKey')
            .toString(),
      );
      expect(image.imageUrl, contains('/media/image/'));
      expect(image.imageUrl, isNot(contains('/media/image/media/image/')));
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

        expect(find.text(ContentText.imageLoadFailed), findsOneWidget);
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

    testWidgets('成功与失败共享加载周期起点并上报真实耗时', (tester) async {
      var now = DateTime.utc(2026, 8, 27, 4, 15);
      final telemetry = RecordingAppTelemetryRecorder();
      const successUrl = 'https://cdn.example.test/media/image/success.png';

      await tester.pumpWidget(
        _wrap(
          AppCachedNetworkImage(
            key: const ValueKey<String>('timed-success-image'),
            imageUrl: successUrl,
            imageUrlCandidates: const <String>[successUrl],
            now: () => now,
          ),
          overrides: [
            appTelemetryReporterProvider.overrideWithValue(telemetry),
          ],
        ),
      );
      final successFinder = find.byType(CachedNetworkImage);
      final successImage = tester.widget<CachedNetworkImage>(successFinder);
      now = now.add(const Duration(milliseconds: 175));
      successImage.imageBuilder!(
        tester.element(successFinder),
        MemoryImage(_transparentImage),
      );
      await tester.pump();

      final successEvent = telemetry.recorded.single;
      expect(successEvent.eventType, 'media_load_state');
      expect(successEvent.extensions['result'], 'success');
      expect(successEvent.extensions['durationMs'], 175);
      expect(successEvent.extensions['candidatesTried'], 1);

      telemetry.recorded.clear();
      now = DateTime.utc(2026, 8, 27, 4, 16);
      const failureUrl = 'https://cdn.example.test/media/image/failure.png';
      await tester.pumpWidget(
        _wrap(
          AppCachedNetworkImage(
            key: const ValueKey<String>('timed-failure-image'),
            imageUrl: failureUrl,
            imageUrlCandidates: const <String>[failureUrl],
            now: () => now,
          ),
          overrides: [
            appTelemetryReporterProvider.overrideWithValue(telemetry),
          ],
        ),
      );
      final failureFinder = find.byType(CachedNetworkImage);
      final failureImage = tester.widget<CachedNetworkImage>(failureFinder);
      now = now.add(const Duration(milliseconds: 420));
      failureImage.errorWidget!(
        tester.element(failureFinder),
        failureUrl,
        StateError('network unavailable'),
      );
      await tester.pump();

      final failureEvent = telemetry.recorded.single;
      expect(failureEvent.eventType, 'media_load_state');
      expect(failureEvent.extensions['result'], 'failure');
      expect(failureEvent.extensions['durationMs'], 420);
      expect(failureEvent.extensions['candidatesTried'], 1);
    });

    testWidgets('三态语义 key：加载占位 / 显式失败 / 解码成功可被测试与 UAT 区分', (tester) async {
      // 失败态（候选为空）：必须暴露 error key，不得与占位混同。
      await tester.pumpWidget(_wrap(const AppCachedNetworkImage(imageUrl: '')));
      await tester.pump();
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
      expect(find.byKey(appImageLoadPlaceholderKey), findsNothing);
      expect(find.byKey(appImageLoadSuccessKey), findsNothing);

      // 自定义 errorWidget（如 feed 灰块）同样必须携带 error key：
      // 这是「图片全灰」可被 UAT 检出的前提。
      await tester.pumpWidget(
        _wrap(
          AppCachedNetworkImage(
            imageUrl: '',
            errorWidget: Container(color: CupertinoColors.systemGrey5),
          ),
        ),
      );
      await tester.pump();
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);

      // 加载中：placeholder key 可见，error/success 不可见。
      await tester.pumpWidget(
        _wrap(
          const AppCachedNetworkImage(
            imageUrl: 'media/image/s/archived-image/post/loading/v1/cover.png',
          ),
        ),
      );
      await tester.pump();
      expect(find.byKey(appImageLoadPlaceholderKey), findsOneWidget);
      expect(find.byKey(appImageLoadErrorKey), findsNothing);

      // 成功态：imageBuilder 产物必须携带 success key。
      final cachedFinder = find.byType(CachedNetworkImage);
      final cachedImage = tester.widget<CachedNetworkImage>(cachedFinder);
      final decoded = cachedImage.imageBuilder!(
        tester.element(cachedFinder),
        MemoryImage(_transparentImage),
      );
      await tester.pumpWidget(_wrap(decoded));
      await tester.pump();
      expect(find.byKey(appImageLoadSuccessKey), findsOneWidget);
      expect(find.byKey(appImageLoadErrorKey), findsNothing);
    });

    testWidgets(
      'avatar reports successful decode once and rejects raw provider URL',
      (tester) async {
        var succeededCount = 0;

        await tester.pumpWidget(
          _wrap(
            AppAvatarImage(
              imageUrl: 'media/avatar/s/mock/user/current/v1/avatar.png',
              onLoadSucceeded: () => succeededCount += 1,
            ),
          ),
        );
        final cachedFinder = find.byType(CachedNetworkImage);
        expect(cachedFinder, findsOneWidget);
        final cachedImage = tester.widget<CachedNetworkImage>(cachedFinder);
        final decodedBuilder = cachedImage.imageBuilder;
        expect(decodedBuilder, isNotNull);
        final decoded = decodedBuilder!(
          tester.element(cachedFinder),
          MemoryImage(_transparentImage),
        );
        await tester.pumpWidget(_wrap(decoded));
        await tester.pump();

        expect(succeededCount, 1);
        expect(find.byType(Image), findsOneWidget);
        await tester.pump();
        expect(succeededCount, 1);

        await tester.pumpWidget(
          _wrap(
            AppAvatarImage(
              imageUrl: 'https://provider.example/profile/user-secret.png',
              onLoadSucceeded: () => succeededCount += 1,
              errorWidget: const SizedBox.shrink(),
            ),
          ),
        );
        await tester.pump();

        expect(succeededCount, 1);
        expect(find.byType(CachedNetworkImage), findsNothing);
      },
    );

    testWidgets('circular avatar uses the unified avatar loader and fallback', (
      tester,
    ) async {
      const fallbackKey = ValueKey<String>('avatar-fallback');
      await tester.pumpWidget(
        _wrap(
          const AppCircularAvatar(
            imageUrl: '',
            size: AppSpacing.avatarSize,
            backgroundColor: CupertinoColors.systemGrey5,
            fallback: Icon(CupertinoIcons.person, key: fallbackKey),
          ),
        ),
      );

      expect(find.byKey(fallbackKey), findsOneWidget);
      expect(find.byType(AppAvatarImage), findsNothing);

      await tester.pumpWidget(
        _wrap(
          const AppCircularAvatar(
            imageUrl: 'media/avatar/s/mock/user/current/v1/avatar.png',
            size: AppSpacing.avatarSize,
            backgroundColor: CupertinoColors.systemGrey5,
            fallback: Icon(CupertinoIcons.person, key: fallbackKey),
          ),
        ),
      );

      expect(find.byType(AppAvatarImage), findsOneWidget);
    });
  });
}
