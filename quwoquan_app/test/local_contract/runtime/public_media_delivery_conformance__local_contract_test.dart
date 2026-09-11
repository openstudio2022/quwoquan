// spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-003
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/video_preview_track_remote.dart';

import '../../support/runtime/observability/recording_app_telemetry_recorder.dart';

import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:video_player/video_player.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_content_block_renderer.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/domain/signed_media_delivery_lease.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../support/runtime/media/signed_media_lease_test_support.dart';

// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';

import '../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/di/video_preview_track_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_public_media_delivery.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_binding.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_canvas.dart';

import '../../support/runtime/cloud_boundary_test_scope.dart';
import '../../support/runtime/config/runtime_package_test_hydration.dart';

class _CachePaths extends PathProviderPlatform {
  _CachePaths(this.root);
  final Directory root;
  @override
  Future<String?> getTemporaryPath() async => root.path;
  @override
  Future<String?> getApplicationSupportPath() async => root.path;
  @override
  Future<String?> getApplicationDocumentsPath() async => root.path;
}

/// 只记录调用字节并委托真实 adapter，绝不构造或替换被测媒体结果。
class _RecordingDelivery implements PublicMediaDeliveryPort {
  _RecordingDelivery(this.actual);
  final PublicMediaDeliveryPort actual;
  final calls =
      <({String operation, String source, CdnImagePreset? profile})>[];
  @override
  MediaEndpointConfig? get endpoints => actual.endpoints;
  @override
  MediaDeliveryReference? tryResolve(
    String? reference, {
    required MediaDeliveryKind kind,
    String assetId = '',
    int version = 0,
    String? sha256,
  }) => actual.tryResolve(
    reference,
    kind: kind,
    assetId: assetId,
    version: version,
    sha256: sha256,
  );
  @override
  List<String> candidates(
    String reference,
    MediaDeliveryKind kind, {
    int version = 0,
  }) => actual.candidates(reference, kind, version: version);
  @override
  Future<SignedMediaDeliveryLease> acquireLease(
    String reference, {
    required MediaDeliveryBinding binding,
    required MediaDeliveryKind kind,
    bool refresh = false,
  }) => actual.acquireLease(
    reference,
    binding: binding,
    kind: kind,
    refresh: refresh,
  );
  @override
  Future<ImageProvider<Object>> acquireImage(
    String reference, {
    required MediaDeliveryBinding binding,
    CdnImagePreset profile = CdnImagePreset.none,
    bool refresh = false,
  }) {
    calls.add((operation: 'image', source: reference, profile: profile));
    return actual.acquireImage(
      reference,
      binding: binding,
      profile: profile,
      refresh: refresh,
    );
  }

  @override
  ImageProvider<Object> imageProvider(
    String reference, {
    CdnImagePreset profile = CdnImagePreset.none,
    MediaDeliveryKind kind = MediaDeliveryKind.image,
    String? cacheKey,
    SignedMediaDeliveryLease? lease,
  }) {
    calls.add((operation: 'image', source: reference, profile: profile));
    return actual.imageProvider(
      reference,
      profile: profile,
      kind: kind,
      cacheKey: cacheKey,
      lease: lease,
    );
  }

  @override
  Future<List<PlayableVideoSource>> playableSources(
    String reference, {
    MediaDeliveryReference? binding,
    SignedMediaDeliveryLease? lease,
    VideoViewType? viewType,
  }) {
    calls.add((operation: 'video', source: reference, profile: null));
    return actual.playableSources(
      reference,
      binding: binding,
      lease: lease,
      viewType: viewType,
    );
  }

  @override
  Future<Map<String, dynamic>> loadJson(
    String reference, {
    required MediaDeliveryReference binding,
  }) {
    calls.add((operation: 'manifest', source: reference, profile: null));
    return actual.loadJson(reference, binding: binding);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() {
    ensureSqfliteFfiInitialized();
    PathProviderPlatform.instance = _CachePaths(
      Directory.systemTemp.createTempSync('qwq-media-conformance-'),
    );
  });
  test('缓存键不授予权限且typed lease必须匹配引用种类及有效期', () async {
    final port = RemotePublicMediaDelivery(
      MediaEndpointConfig(
        avatarBaseUrl: 'https://cdn.test/media/avatar',
        imageBaseUrl: 'https://cdn.test/media/image',
        videoBaseUrl: 'https://cdn.test/media/video',
        attachmentBaseUrl: 'https://cdn.test',
      ),
    );
    final avatar = port.imageProvider(
      'media/avatar/s/test/person/v1/avatar.png',
      profile: CdnImagePreset.inline,
    ) as CachedNetworkImageProvider;
    expect(avatar.url, contains('/media/avatar/'));
    const privateUrl = 'https://untrusted.test/object.jpg?sign=a&t=1';
    expect(
      () => port.imageProvider(privateUrl, cacheKey: 'signed|image|pretend'),
      throwsFormatException,
    );
    expect(
      () => port.imageProvider('/tmp/private.png', cacheKey: 'local'),
      throwsFormatException,
    );
    final lease = testSignedMediaLease(
      deliveryUri: Uri.parse(privateUrl),
      assetId: 'asset',
      kind: MediaDeliveryKind.image,
    );
    final provider = port.imageProvider(
      privateUrl,
      lease: lease,
    ) as CachedNetworkImageProvider;
    expect(provider.url, privateUrl);
    expect(
      () => port.imageProvider('$privateUrl&other=1', lease: lease),
      throwsFormatException,
    );
    await expectLater(
      port.playableSources(privateUrl, lease: lease),
      throwsFormatException,
    );
    final expired = testSignedMediaLease(
      deliveryUri: Uri.parse(privateUrl),
      assetId: 'asset',
      kind: MediaDeliveryKind.image,
      expiresAt: DateTime.utc(2026, 2),
    );
    expect(
      () => port.imageProvider(privateUrl, lease: expired),
      throwsFormatException,
    );
  });

  test('四环境使用同一图片驱动且返回同一 provider 类型边界', () async {
    installCanonicalOfflineAssetsForTests();
    final bundle = await OfflineContentBundle.load();
    final image = bundle.media.byAssetId.values.firstWhere(
      (a) => a.kind == 'image',
    );
    for (final environment in ['alpha', 'beta', 'gamma', 'prod']) {
      final PublicMediaDeliveryPort port = environment == 'alpha'
          ? BundledPublicMediaDelivery()
          : RemotePublicMediaDelivery(
              MediaEndpointConfig(
                avatarBaseUrl: 'https://$environment.example.test/media/avatar',
                imageBaseUrl: 'https://$environment.example.test/media/image',
                videoBaseUrl: 'https://$environment.example.test/media/video',
                attachmentBaseUrl: 'https://$environment.example.test',
              ),
            );
      final source = image.canonicalReference;
      final provider = await port.acquireImage(
        source,
        binding: MediaDeliveryBinding.public(publicUrl: source),
        profile: CdnImagePreset.full,
      );
      expect(provider, isA<ImageProvider<Object>>());
      final identity = port.tryResolve(source, kind: MediaDeliveryKind.image)!;
      expect(identity.sourceReference.codeUnits, source.codeUnits);
      await expectLater(
        port.acquireImage(
          source,
          binding: MediaDeliveryBinding(
            assetId: image.assetId,
            accessMode: null,
            publicUrl: source,
          ),
          profile: CdnImagePreset.full,
        ),
        throwsA(isA<FormatException>()),
      );
    }
  });

  test('四环境视频同Post驱动返回平台源且manifest缺席不改变P0获取', () async {
    installCanonicalOfflineAssetsForTests();
    final bundle = await OfflineContentBundle.load();
    final post = bundle
        .rows('posts')
        .map(
          (row) => ContentPostViewData.fromWire(
            ContentPostProjection.fromWire(
              row['projection'] as Map<String, Object?>,
            ),
          ),
        )
        .firstWhere((post) => post.mediaVideoUrl.isNotEmpty);
    final client = CloudHttpClient(
      client: MockClient((_) async => http.Response('{}', 404)),
    );
    addTearDown(client.close);
    for (final env in ['alpha', 'beta', 'gamma', 'prod']) {
      final port = _RecordingDelivery(
        env == 'alpha'
            ? BundledPublicMediaDelivery()
            : RemotePublicMediaDelivery(
                MediaEndpointConfig(
                  avatarBaseUrl: 'https://$env.test/media/avatar',
                  imageBaseUrl: 'https://$env.test/media/image',
                  videoBaseUrl: 'https://$env.test/media/video',
                  attachmentBaseUrl: 'https://$env.test',
                ),
                httpClient: () => client,
              ),
      );
      final reference = port.tryResolve(
        post.mediaVideoUrl,
        kind: MediaDeliveryKind.video,
        assetId: post.mediaAssetId ?? '',
        version: post.mediaAssetVersion ?? 0,
      )!;
      final sources = await port.playableSources(
        post.mediaVideoUrl,
        binding: reference,
      );
      expect(sources, hasLength(1));
      final missing = '${post.mediaVideoUrl}/preview/manifest.json';
      final manifestReference = port.tryResolve(
        missing,
        kind: MediaDeliveryKind.video,
      )!;
      final query = RemoteVideoPreviewTrackQuery(
        mediaDelivery: port,
        telemetry: RecordingAppTelemetryRecorder(),
      );
      await expectLater(
        query.loadManifest(
          VideoPreviewTrackDescriptor(
            assetId: reference.assetId,
            assetVersion: reference.version,
            trackVersion: 1,
            manifestReference: manifestReference,
          ),
        ),
        throwsA(isA<Object>()),
      );
      expect(port.calls.first.source.codeUnits, post.mediaVideoUrl.codeUnits);
      expect(port.calls.last.source.codeUnits, missing.codeUnits);
      expect(
        await port.playableSources(post.mediaVideoUrl, binding: reference),
        hasLength(1),
      );
    }
  });

  for (final environment in ['alpha', 'beta', 'gamma', 'prod']) {
    testWidgets('$environment Post头像封面文章同业务驱动逐字节进入真实adapter', (tester) async {
      installCanonicalOfflineAssetsForTests();
      MediaLoadFailureCache.instance.clear();
      final bundle = await tester.runAsync(OfflineContentBundle.load);
      final post = bundle!
          .rows('posts')
          .map(
            (row) => ContentPostViewData.fromWire(
              ContentPostProjection.fromWire(
                row['projection'] as Map<String, Object?>,
              ),
            ),
          )
          .firstWhere(
            (post) =>
                post.primaryImageUrl.isNotEmpty && post.avatarUrl.isNotEmpty,
          );
      final recording = _RecordingDelivery(
        environment == 'alpha'
            ? BundledPublicMediaDelivery()
            : RemotePublicMediaDelivery(
                MediaEndpointConfig(
                  avatarBaseUrl: 'https://$environment.test/media/avatar',
                  imageBaseUrl: 'https://$environment.test/media/image',
                  videoBaseUrl: 'https://$environment.test/media/video',
                  attachmentBaseUrl: 'https://$environment.test',
                ),
              ),
      );
      final cover = post.mediaCoverUrl.isEmpty
          ? post.primaryImageUrl
          : post.mediaCoverUrl;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            ...sealedCloudBoundaryOverrides(),
            publicMediaDeliveryProvider.overrideWithValue(recording),
          ],
          child: MaterialApp(
            home: Column(
              children: [
                SizedBox(
                  width: 40,
                  height: 40,
                  child: AppAvatarImage(imageUrl: post.avatarUrl),
                ),
                SizedBox(
                  width: 40,
                  height: 40,
                  child: AppCachedNetworkImage(
                    imageUrl: cover,
                    cdnPreset: CdnImagePreset.cover,
                  ),
                ),
                SizedBox(
                  width: 40,
                  height: 40,
                  child: ArticleAdaptiveImage(imageUrl: cover),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pump();
      expect(
        recording.calls.any(
          (call) =>
              call.source.codeUnits.toString() ==
                  post.avatarUrl.codeUnits.toString() &&
              call.profile == CdnImagePreset.avatar,
        ),
        isTrue,
      );
      expect(
        recording.calls.any(
          (call) =>
              call.source == cover && call.profile == CdnImagePreset.cover,
        ),
        isTrue,
      );
      expect(
        recording.calls.any(
          (call) => call.source == cover && call.profile == CdnImagePreset.none,
        ),
        isTrue,
      );
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 250)),
      );
      await tester.pump(const Duration(seconds: 7));
    });
  }

  testWidgets('Alpha 相对引用经真实 canvas 默认 loader 成功解码且 preview provider 可构造', (
    tester,
  ) async {
    installCanonicalOfflineAssetsForTests();
    final bundle = await tester.runAsync(OfflineContentBundle.load);
    final image = bundle!.media.byAssetId.values.firstWhere(
      (a) => a.kind == 'image',
    );
    final delivery = BundledPublicMediaDelivery();
    final events = <ImageBookMediaLoadEvent>[];
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          publicMediaDeliveryProvider.overrideWithValue(delivery),
        ],
        child: MaterialApp(
          home: Consumer(
            builder: (context, ref, _) {
              ref.watch(videoPreviewTrackQueryProvider);
              return SizedBox(
                width: 375,
                height: 600,
                child: ImageBookCanvas(
                  deliveries: [
                    MediaDeliveryBinding.public(
                      publicUrl: image.canonicalReference,
                    ),
                  ],
                  onImageChanged: (_) {},
                  onMediaLoad: events.add,
                ),
              );
            },
          ),
        ),
      ),
    );
    for (var i = 0; i < 80 && !events.any((e) => e.result == 'success'); i++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 25)),
      );
      await tester.pump(const Duration(milliseconds: 20));
    }
    expect(
      events.any((e) => e.result == 'success'),
      isTrue,
      reason: events.map((e) => '${e.result}: ${e.error}').join(', '),
    );
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
