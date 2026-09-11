import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/painting.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_app/runtime/di/login_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/executor/unavailable_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_bundled.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/user_profile_cache_service.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_bundled.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';

import '../../support/runtime/cloud_boundary_test_scope.dart';

import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_image_provider.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';

import '../../support/runtime/config/runtime_package_test_hydration.dart';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007.t1
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007.t2
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('Alpha 组合根选择 creator 与作者作品，Beta 不复用离线 adapter', () async {
    final client = GeneratedCloudOperationClient(
      const UnavailableCloudOperationExecutor(),
    );
    CloudOperationInvocationContext context(String _, String _) =>
        throw StateError('离线不得构造调用上下文');
    await hydrateRuntimePackageForTests(environment: 'alpha');
    final container = ProviderContainer(
      overrides: sealedCloudBoundaryOverrides(),
    );
    try {
      expect(container.read(loginCapabilityFailureProvider), isNotNull);
      final profile = UserProductionComposition.generatedAdapter<ProfileQuery>(
        UserProductionAdapter.profileQuery,
        client: client,
        invocationContext: context,
      );
      final persona = UserProductionComposition.generatedAdapter<PersonaQuery>(
        UserProductionAdapter.personaQuery,
        client: client,
        invocationContext: context,
      );
      expect(profile, isA<BundledProfileQuery>());
      expect(persona, isA<BundledProfileQuery>());
      final facets = ContentProductionComposition.contentPostReaderFacets(
        client: client,
        invocationContext: (String _) => throw StateError('离线不得请求 Remote'),
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
        currentCacheIdentity: () => null,
        userProfileCache: UserProfileCacheService(),
        telemetrySink: const SilentCacheTelemetrySink(),
      );
      expect(facets.authorPosts, isA<BundledContentPostReader>());
      expect(facets.detail, same(facets.authorPosts));
      final bundle = await OfflineContentBundle.load();
      final creator = PersonaProfileView.fromWire(
        bundle.rows('creators').first['projection']! as Map<String, Object?>,
      );
      expect(
        (await profile.getUserHomepageBundle(creator.personaId))
            .profile
            .displayName,
        creator.displayName,
      );
      expect(
        (await facets.authorPosts.listUserPosts(userId: creator.personaId))
            .items,
        isNotEmpty,
      );
    } finally {
      container.dispose();
      await hydrateRuntimePackageForTests(environment: 'beta');
    }
    final remote = UserProductionComposition.generatedAdapter<ProfileQuery>(
      UserProductionAdapter.profileQuery,
      client: client,
      invocationContext: context,
    );
    expect(remote, isNot(isA<BundledProfileQuery>()));
    final onlineContainer = ProviderContainer(
      overrides: sealedCloudBoundaryOverrides(),
    );
    expect(onlineContainer.read(loginCapabilityFailureProvider), isNull);
    onlineContainer.dispose();
  });

  test('真实包内内容通过制品 pin 和现役 Dart 生成 decoder', () async {
    final bytes = await rootBundle.load(offlineContentManifestAssetPath);
    final raw = bytes.buffer.asUint8List(
      bytes.offsetInBytes,
      bytes.lengthInBytes,
    );
    expect('sha256:${sha256.convert(raw)}', offlineContentManifestDigest);
    final manifest = jsonDecode(utf8.decode(raw)) as Map<String, dynamic>;
    expect(manifest['schema'], 'quwoquan.offline_content_bundle');
    final posts = manifest['posts'] as List<dynamic>;
    final ids = <String>{};
    for (final value in posts) {
      final row = value as Map<String, dynamic>;
      final projection = ContentPostProjection.fromWire(row['projection']);
      final detail = ContentPostDetailSlice.fromWire(row['detail']);
      final card = ContentPostViewData.fromWire(projection);
      final detailView = ContentPostDetailPayload.fromWire(detail);
      expect(card.id, detailView.post.id);
      expect(card.type, detailView.post.type);
      expect(ids.add(card.id), isTrue);
      if (card.type == 'article') {
        expect(detail.articleMarkdown, isNotEmpty);
      }
    }
    expect(ids, hasLength(posts.length));
    for (final channel in manifest['channels'] as List<dynamic>) {
      final selected = (channel['orderedPostIds'] as List<dynamic>)
          .cast<String>();
      expect(selected.every(ids.contains), isTrue);
      if (channel['channelId'] == 'premium') expect(selected, isNotEmpty);
    }
    ContentAppConfig.fromWire(manifest['configuration']['content']);
    for (final creator in manifest['creators'] as List<dynamic>) {
      PersonaProfileView.fromWire(creator['projection']);
    }
    for (final homepage in manifest['homepages'] as List<dynamic>) {
      HomepageIntroduction.fromWire(homepage['projection']);
    }
  });

  test('Alpha 公开图片由实际包内字节解码，缺媒体拒绝且换文档不复用旧来源', () async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    final offline = publicMediaDelivery;
    try {
      expect(offline.endpoints, isNull);
      final manifest = jsonDecode(
        await rootBundle.loadString(offlineContentManifestAssetPath),
      ) as Map<String, dynamic>;
      final media = (manifest['media'] as List<dynamic>)
          .cast<Map<String, dynamic>>();
      for (final row in media.where((row) => row['kind'] != 'video')) {
        final provider = offline.verifiedImageProvider(
          row['canonicalReference'] as String,
        )!;
        expect(provider, isA<BundledImageProvider>());
        final image = await _decodeImage(provider);
        expect(image.image.width, greaterThan(0));
        expect(image.image.height, greaterThan(0));
        image.dispose();
      }
      await expectLater(
        _decodeImage(offline.verifiedImageProvider('media/image/missing.png')!),
        throwsA(isA<OfflineContentFailure>()),
      );
      await expectLater(
        offline.verifiedVideoPath('media/video/missing.mp4'),
        throwsA(isA<OfflineContentFailure>()),
      );
      await hydrateRuntimePackageForTests(environment: 'beta');
      final remote = publicMediaDelivery;
      expect(identical(remote, offline), isFalse);
      expect(remote.endpoints, isNotNull);
      expect(
        remote.verifiedImageProvider(
          media.first['canonicalReference'] as String,
        ),
        isNull,
      );
      expect(
        remote.candidates(
          'https://untrusted.invalid/image.png',
          MediaDeliveryKind.image,
        ),
        isEmpty,
      );
      await hydrateRuntimePackageForTests(environment: 'alpha');
      expect(identical(publicMediaDelivery, offline), isFalse);
    } finally {
      await hydrateRuntimePackageForTests(environment: 'beta');
    }
  });

  test('Alpha 视频物化来自完整快照并保持摘要，缺媒体不创建网络候选', () async {
    final directory = await Directory.systemTemp.createTemp(
      'qwq-offline-video-',
    );
    const channel = MethodChannel('plugins.flutter.io/path_provider');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (_) async => directory.path);
    await hydrateRuntimePackageForTests(environment: 'alpha');
    try {
      final manifest = jsonDecode(
        await rootBundle.loadString(offlineContentManifestAssetPath),
      ) as Map<String, dynamic>;
      final video = (manifest['media'] as List<dynamic>)
          .cast<Map<String, dynamic>>()
          .firstWhere((row) => row['kind'] == 'video');
      final delivery = publicMediaDelivery;
      final path = await delivery.verifiedVideoPath(
        video['canonicalReference'] as String,
      );
      expect(path, isNotNull);
      expect(path, startsWith(directory.path));
      final bytes = await File(path!).readAsBytes();
      expect(bytes.length, video['byteLength']);
      expect('sha256:${sha256.convert(bytes)}', video['sha256']);
      expect(
        await delivery.verifiedVideoPath(video['canonicalReference'] as String),
        path,
      );
    } finally {
      messenger.setMockMethodCallHandler(channel, null);
      await hydrateRuntimePackageForTests(environment: 'beta');
      await directory.delete(recursive: true);
    }
  });

  test('真实包内全部媒体均有完整字节，摘要及总量匹配', () async {
    final manifest = jsonDecode(
      await rootBundle.loadString(offlineContentManifestAssetPath),
    ) as Map<String, dynamic>;
    final media = manifest['media'] as List<dynamic>;
    var total = 0;
    for (final value in media) {
      final row = value as Map<String, dynamic>;
      final data = await rootBundle.load(row['assetPath'] as String);
      final bytes = data.buffer.asUint8List(
        data.offsetInBytes,
        data.lengthInBytes,
      );
      expect(bytes.length, row['byteLength']);
      expect('sha256:${sha256.convert(bytes)}', row['sha256']);
      total += bytes.length;
    }
    expect(media, isNotEmpty);
    expect(total, manifest['counts']['mediaBytes']);
  });
}

Future<ImageInfo> _decodeImage(ImageProvider<Object> provider) async {
  final stream = provider.resolve(ImageConfiguration.empty);
  final result = Completer<ImageInfo>();
  final listener = ImageStreamListener(
    (image, synchronous) {
      if (!result.isCompleted) result.complete(image);
    },
    onError: (Object error, StackTrace? stack) {
      if (!result.isCompleted) result.completeError(error, stack);
    },
  );
  stream.addListener(listener);
  try {
    return await result.future.timeout(const Duration(seconds: 10));
  } finally {
    stream.removeListener(listener);
  }
}
