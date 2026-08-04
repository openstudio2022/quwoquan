// spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import '../../../../support/fixtures/intersection_fixtures.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/content/content/post/domain/content_surface_view.dart';
import 'package:quwoquan_app/content/content/post/domain/content_surface_view_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/content/content/post/content_post_contract_fixture.dart';

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
