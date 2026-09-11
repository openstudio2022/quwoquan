// spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/content_surface_view_mapper.dart'
    as domain;

import '../../../../../support/runtime/config/runtime_package_test_hydration.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/post/content_post_contract_fixture.dart';

final _mediaResolver = MediaDeliveryResolver(
  MediaEndpointConfig(
    avatarBaseUrl: 'https://avatar.example.test',
    imageBaseUrl: 'https://image.example.test',
    videoBaseUrl: 'https://video.example.test',
    attachmentBaseUrl: 'https://attachment.example.test',
  ),
);
final _unavailableMediaResolver = MediaDeliveryResolver(
  MediaEndpointConfig.tryCreateAvailable(
    avatarBaseUrl: '',
    imageBaseUrl: '',
    videoBaseUrl: '',
    attachmentBaseUrl: '',
  )!,
);

ContentPostViewData _viewData(ContentPostProjection projection) =>
    ContentPostViewData.fromWire(projection);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-008
  test('真实 canonical cohort 经 Alpha 与 Remote 组合根映射保留同一媒体资产版本', () async {
    final bundle = await OfflineContentBundle.load();
    final posts = bundle
        .rows('posts')
        .map(
          (row) => ContentPostViewData.fromWire(
            ContentPostProjection.fromWire(
              row['projection']! as Map<String, Object?>,
            ),
          ),
        )
        .toList();
    addTearDown(() => hydrateRuntimePackageForTests(environment: 'beta'));
    for (final environment in ['alpha', 'beta', 'gamma']) {
      await hydrateRuntimePackageForTests(environment: environment);
      final views = posts.map(ContentSurfaceViewMapper.fromDto).toList();
      expect(views.map((view) => view.postId), posts.map((post) => post.id));
      for (final view in views) {
        final post = posts.singleWhere((post) => post.id == view.postId);
        final references = [
          if (view.cover != null) view.cover!.delivery,
          if (view.author.avatar != null) view.author.avatar!,
          ...view.images.map((image) => image.delivery),
          if (view.video != null) view.video!.delivery,
        ];
        expect(references, isNotEmpty);
        for (final reference in references) {
          final uri = Uri.parse(reference.url);
          expect(uri.hasScheme, environment != 'alpha');
          if (environment != 'alpha') expect(uri.scheme, 'https');
          expect(reference.version, greaterThan(0));
        }
        if (post.isVideoLike) {
          expect(view.video, isNotNull);
          expect(view.video!.delivery.assetId, post.mediaAssetId);
          expect(view.video!.delivery.version, post.mediaAssetVersion);
          expect(view.video!.thumbnailUrl, view.cover!.url);
        }
        if (post.hasImages && !post.isVideoLike) {
          expect(view.images.length, post.mediaImageUrls.length);
        }
      }
    }
  });

  test('domain 仅消费注入能力，Alpha 状态不读取在线配置且保留解析摘要', () async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    addTearDown(() => hydrateRuntimePackageForTests(environment: 'beta'));
    final bundle = await OfflineContentBundle.load();
    final post = bundle
        .rows('posts')
        .map(
          (row) => ContentPostViewData.fromWire(
            ContentPostProjection.fromWire(
              row['projection']! as Map<String, Object?>,
            ),
          ),
        )
        .singleWhere((post) => post.isVideoLike);
    final delivery = publicMediaDelivery;
    final seen = <({String assetId, int version})>[];
    final view = domain.ContentSurfaceViewMapper.fromDto(
      post,
      resolveMedia:
          (reference, {required kind, assetId = '', version = 0, sha256}) {
            final asset = bundle.media.lookup(
              reference ?? '',
              assetId: assetId,
            );
            if (kind == MediaDeliveryKind.video) {
              seen.add((assetId: assetId, version: version));
            }
            return delivery.tryResolve(
              reference,
              kind: kind,
              assetId: assetId,
              version: version,
              sha256: asset?.digest,
            );
          },
    );
    expect(seen, [
      (assetId: post.mediaAssetId!, version: post.mediaAssetVersion!),
    ]);
    expect(
      view.video!.delivery.sha256,
      bundle.media.lookup(post.mediaVideoUrl)!.digest,
    );
    // 显式 Remote resolver 也是纯能力输入，不因当前 Alpha 去读取在线端点。
    final remote = ContentSurfaceViewMapper.fromDto(
      post,
      mediaResolver: _mediaResolver,
    );
    expect(Uri.parse(remote.video!.url).host, 'video.example.test');
    expect(remote.video!.delivery.assetId, view.video!.delivery.assetId);
    expect(remote.video!.delivery.version, view.video!.delivery.version);
  });

  group('ContentSurfaceViewMapper — canonical ContentPostProjection', () {
    test('image 投影为多图 surface，并保持作者和统计口径', () {
      final dto = _viewData(
        contentPostProjectionFixture(
          postId: 'photo1',
          contentType: 'image',
          contentIdentity: 'work',
          authorId: 'a1',
          authorDisplayName: '作者甲',
          authorAvatarUrl: 'media/avatar/s/fixture/a1/v1/avatar.png',
          mediaUrls: const <String>[
            'media/image/s/fixture/photo1/v1/1.jpg',
            'media/image/s/fixture/photo1/v1/2.jpg',
          ],
          coverUrl: 'media/image/s/fixture/photo1/v1/cover.jpg',
          likeCount: 10,
          commentCount: 2,
          shareCount: 3,
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        mediaResolver: _mediaResolver,
      );

      expect(view.postId, 'photo1');
      expect(view.kind, ContentSurfaceKind.image);
      expect(view.contentType, dto.type);
      expect(view.author.id, 'a1');
      expect(view.author.displayName, '作者甲');
      expect(view.images, hasLength(2));
      expect(view.images.first.url, contains('/photo1/v1/1.jpg'));
      expect(view.video, isNull);
      expect(view.stats.like, 10);
      expect(view.stats.comment, 2);
      expect(view.stats.share, 3);
    });

    test('video 使用 thumbnail 作为 cover 与播放 poster 的唯一来源', () {
      final dto = _viewData(
        contentPostProjectionFixture(
          postId: 'video1',
          contentType: 'video',
          contentIdentity: 'work',
          videoUrl: 'media/video/s/fixture/video1/v1/clip.mp4',
          thumbnailUrl: 'media/image/s/fixture/video1/v1/manual-thumb.jpg',
          coverUrl: 'media/image/s/fixture/video1/v1/stale-cover.jpg',
          durationMs: 12000,
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        mediaResolver: _mediaResolver,
      );

      expect(view.kind, ContentSurfaceKind.video);
      expect(view.hasVideo, isTrue);
      expect(view.video!.url, contains('/video1/v1/clip.mp4'));
      expect(view.video!.durationMs, 12000);
      expect(view.cover!.url, contains('/video1/v1/manual-thumb.jpg'));
      expect(view.cover!.url, view.video!.thumbnailUrl);
      expect(view.hasImages, isFalse);
    });

    test('article 保持标题、正文、封面与页面 presentation 字段', () {
      final dto = _viewData(
        contentPostProjectionFixture(
          postId: 'article1',
          contentType: 'article',
          contentIdentity: 'work',
          title: '统一展示标题',
          body: '正文摘要',
          coverUrl: 'media/image/s/fixture/article1/v1/cover.jpg',
          articleTemplate: 'modern',
          articleFontPreset: 'serif',
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        mediaResolver: _mediaResolver,
        wire: const <String, dynamic>{
          'articleTemplate': 'modern',
          'articleFontPreset': 'serif',
          'tagRefs': <String>['校园', '摄影'],
        },
      );

      expect(view.kind, ContentSurfaceKind.article);
      expect(view.title, '统一展示标题');
      expect(view.body, '正文摘要');
      expect(view.cover!.url, contains('/article1/v1/cover.jpg'));
      expect(view.articleTemplate, 'modern');
      expect(view.articleFontPreset, 'serif');
      expect(view.tags, <String>['校园', '摄影']);
    });

    test('micro 仅正文且无媒体', () {
      final dto = _viewData(
        contentPostProjectionFixture(
          postId: 'micro1',
          contentType: 'micro',
          contentIdentity: 'moment',
          body: '随手一条',
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(view.kind, ContentSurfaceKind.micro);
      expect(view.body, '随手一条');
      expect(view.hasImages, isFalse);
      expect(view.hasVideo, isFalse);
      expect(view.cover, isNull);
    });

    test('媒体端点不可用时保留 typed 内容事实且不伪造 URL', () {
      final dto = _viewData(
        contentPostProjectionFixture(
          postId: 'photo-without-endpoint',
          contentType: 'image',
          mediaUrls: const <String>[
            'media/image/s/fixture/photo-without-endpoint/v1/1.jpg',
          ],
          authorAvatarUrl:
              'media/avatar/s/fixture/photo-without-endpoint/v1/avatar.png',
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        mediaResolver: _unavailableMediaResolver,
      );

      expect(view.postId, 'photo-without-endpoint');
      expect(view.kind, ContentSurfaceKind.image);
      expect(view.images, isEmpty);
      expect(view.cover, isNull);
      expect(view.author.avatar, isNull);
    });

    test('canonical IntersectionReason 透传到统一 surface', () {
      final reason = intersectionReasonFixture(
        dimension: 'alumni',
        tagRefs: const <String>['tag:school:neworiental'],
        objectKind: 'circle',
        relationObjectId: 'circle1',
        primaryText: '你和 TA 都来自新东方校友圈',
        actionTargetId: 'circle1',
      );
      final dto = _viewData(
        contentPostProjectionFixture(
          postId: 'micro2',
          contentType: 'micro',
          contentIdentity: 'moment',
          body: '带交集理由',
          intersectionReasons: <IntersectionReason>[reason],
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(view.hasIntersectionReasons, isTrue);
      expect(view.intersectionReasons.single, same(reason));
      expect(view.intersectionReasons.single.primaryText, '你和 TA 都来自新东方校友圈');
    });

    test('createdAt、updatedAt、publishedAt 保持各自时间语义', () {
      final dto = _viewData(
        contentPostProjectionFixture(
          postId: 'time1',
          contentType: 'article',
          contentIdentity: 'work',
          title: '时间语义文章',
          body: '正文',
          createdAt: DateTime.utc(2026, 1),
          updatedAt: DateTime.utc(2026, 2),
          publishedAt: DateTime.utc(2026, 1, 3),
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(view.createdAt, DateTime.utc(2026, 1));
      expect(view.updatedAt, DateTime.utc(2026, 2));
      expect(view.publishedAt, DateTime.utc(2026, 1, 3));
      expect(view.hasMeaningfulUpdate, isTrue);
    });

    test('createdAt 缺失不借用 publishedAt，使用明确 epoch 缺省', () {
      final dto = ContentPostViewData.fromWire(
        const ContentPostProjection(
          postId: 'time2',
          contentType: 'article',
          contentIdentity: 'work',
          title: '仅有发布时间',
          body: '正文',
          likeCount: 0,
          commentCount: 0,
          shareCount: 0,
          publishedAt: null,
        ),
      );
      final publishedAt = DateTime.utc(2026, 1, 5);
      final wire = ContentPostProjection(
        postId: dto.id,
        contentType: dto.type,
        contentIdentity: dto.identity,
        title: dto.title,
        body: dto.body,
        likeCount: 0,
        commentCount: 0,
        shareCount: 0,
        publishedAt: publishedAt,
      );

      final view = ContentSurfaceViewMapper.fromDto(
        ContentPostViewData.fromWire(wire),
      );

      expect(
        view.createdAt,
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
      );
      expect(view.createdAt, isNot(view.publishedAt));
      expect(view.publishedAt, publishedAt);
    });

    test('显式媒体版本漂移与不可信 Remote 原点不产生可播放 surface', () {
      for (final url in [
        'media/video/s/asset/video-1/v1/source.mp4',
        'https://untrusted.invalid/media/video/s/asset/video-1/v2/source.mp4',
      ]) {
        final dto = _viewData(
          contentPostProjectionFixture(
            contentType: 'video',
            videoUrl: url,
            mediaAssetId: 'video-1',
            mediaAssetVersion: 2,
            mediaItems: [
              PostMediaItem(
                kind: 'video',
                url: url,
                mediaAssetId: 'video-1',
                mediaAssetVersion: 2,
              ),
            ],
          ),
        );
        expect(
          ContentSurfaceViewMapper.fromDto(
            dto,
            mediaResolver: _mediaResolver,
          ).video,
          isNull,
        );
      }
      const image = 'media/image/s/asset/image-1/v1/source.jpg';
      final dto = _viewData(
        contentPostProjectionFixture(
          contentType: 'image',
          mediaUrls: [image],
          mediaItems: const [
            PostMediaItem(
              kind: 'image',
              url: image,
              mediaAssetId: 'image-1',
              mediaAssetVersion: 2,
            ),
          ],
        ),
      );
      expect(
        ContentSurfaceViewMapper.fromDto(
          dto,
          mediaResolver: _mediaResolver,
        ).images,
        isEmpty,
      );
    });

    test('referral 上下文只透传，不改变展示事实', () {
      final dto = _viewData(
        contentPostProjectionFixture(
          postId: 'micro3',
          contentType: 'micro',
          contentIdentity: 'moment',
          body: 'x',
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        referral: const ContentSurfaceReferral(
          position: 7,
          feedRequestId: 'req-123',
        ),
      );

      expect(view.postId, 'micro3');
      expect(view.referral.position, 7);
      expect(view.referral.feedRequestId, 'req-123');
    });
  });
}
