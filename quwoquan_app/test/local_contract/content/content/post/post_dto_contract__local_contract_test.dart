// spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/content/content/post/content_mock_data.dart';
import '../../../../support/content/content/post/content_post_contract_fixture.dart';

ContentPostViewData _decodeView(Map<String, Object?> wire) =>
    ContentPostViewData.fromWire(ContentPostProjection.fromWire(wire));

Map<String, Object?> _canonicalWire({
  required String postId,
  required String contentType,
  String? contentIdentity,
  String? authorId = 'author-1',
  String? authorDisplayName = 'Author',
  String? authorAvatarUrl = '',
  String? title,
  String? body,
  String? coverUrl,
  List<String>? mediaUrls,
  String? videoUrl,
  String? thumbnailUrl,
  int? width,
  int? height,
  int? durationMs,
  int likeCount = 0,
  int commentCount = 0,
  int shareCount = 0,
  DateTime? createdAt,
  DateTime? updatedAt,
  DateTime? publishedAt,
  String? articleTemplate,
  String? articleFontPreset,
}) => contentPostProjectionFixture(
  postId: postId,
  contentType: contentType,
  contentIdentity: contentIdentity,
  authorId: authorId,
  authorDisplayName: authorDisplayName,
  authorAvatarUrl: authorAvatarUrl,
  title: title,
  body: body,
  coverUrl: coverUrl,
  mediaUrls: mediaUrls,
  videoUrl: videoUrl,
  thumbnailUrl: thumbnailUrl,
  width: width,
  height: height,
  durationMs: durationMs,
  likeCount: likeCount,
  commentCount: commentCount,
  shareCount: shareCount,
  createdAt: createdAt,
  updatedAt: updatedAt,
  publishedAt: publishedAt,
  articleTemplate: articleTemplate,
  articleFontPreset: articleFontPreset,
).toWire();

void main() {
  group('ContentPostProjection — canonical wire', () {
    test('image 解析尺寸、媒体、作者和统计字段', () {
      final view = _decodeView(
        _canonicalWire(
          postId: 'p1',
          contentType: 'image',
          contentIdentity: 'work',
          authorId: 'auth1',
          authorDisplayName: '摄影师',
          authorAvatarUrl: 'https://example.com/avatar.jpg',
          coverUrl: 'https://example.com/cover.jpg',
          mediaUrls: const <String>[
            'https://example.com/img1.jpg',
            'https://example.com/img2.jpg',
          ],
          width: 1200,
          height: 800,
          likeCount: 100,
          commentCount: 10,
          shareCount: 5,
          createdAt: DateTime.utc(2025, 12, 1, 10),
          publishedAt: DateTime.utc(2025, 12, 1, 10),
        ),
      );

      expect(view.id, 'p1');
      expect(view.type, 'image');
      expect(view.identity, 'work');
      expect(view.displayFormat, 'image');
      expect(view.authorId, 'auth1');
      expect(view.displayName, '摄影师');
      expect(view.imageUrls, hasLength(2));
      expect(view.width, 1200);
      expect(view.height, 800);
      expect(view.aspectRatio, 1.5);
      expect(view.likeCount, 100);
      expect(view.createdAt.year, 2025);
    });

    test('video 解析唯一视频、封面、尺寸和时长', () {
      final view = _decodeView(
        _canonicalWire(
          postId: 'video-portrait',
          contentType: 'video',
          contentIdentity: 'work',
          videoUrl: 'https://example.com/video.mp4',
          thumbnailUrl: 'https://example.com/thumb.jpg',
          width: 1080,
          height: 1920,
          durationMs: 30000,
          likeCount: 500,
        ),
      );

      expect(view.id, 'video-portrait');
      expect(view.type, 'video');
      expect(view.identity, 'work');
      expect(view.displayFormat, 'video');
      expect(view.videoUrl, 'https://example.com/video.mp4');
      expect(view.thumbnailUrl, 'https://example.com/thumb.jpg');
      expect(view.imageUrls, isEmpty);
      expect(view.aspectRatio, lessThan(1));
      expect(view.durationMs, 30000);
      expect(view.likeCount, 500);
    });

    test('article 解析标题、正文和 presentation 元数据', () {
      final view = _decodeView(
        _canonicalWire(
          postId: 'article-1',
          contentType: 'article',
          contentIdentity: 'work',
          title: '连续文档标题',
          body: '文章摘要内容',
          coverUrl: 'https://example.com/article.jpg',
          articleTemplate: 'journal',
          articleFontPreset: 'handwritten',
        ),
      );

      expect(view.type, 'article');
      expect(view.identity, 'work');
      expect(view.displayFormat, 'note');
      expect(view.title, '连续文档标题');
      expect(view.normalizedBody, '文章摘要内容');
      expect(view.coverUrl, 'https://example.com/article.jpg');
      expect(view.articleTemplate, 'journal');
      expect(view.articleFontPreset, 'handwritten');
    });

    test('micro 按 canonical 媒体事实派生 note、image、video 展示形态', () {
      final text = _decodeView(
        _canonicalWire(
          postId: 'micro-text',
          contentType: 'micro',
          contentIdentity: 'moment',
          body: '一条微趣文字',
        ),
      );
      final image = _decodeView(
        _canonicalWire(
          postId: 'micro-image',
          contentType: 'micro',
          contentIdentity: 'moment',
          body: '图文微趣',
          mediaUrls: const <String>['https://example.com/img.jpg'],
        ),
      );
      final video = _decodeView(
        _canonicalWire(
          postId: 'micro-video',
          contentType: 'micro',
          contentIdentity: 'moment',
          body: '视频微趣',
          videoUrl: 'https://example.com/video.mp4',
          durationMs: 15000,
        ),
      );

      expect(text.displayFormat, 'note');
      expect(text.hasAnyMedia, isFalse);
      expect(image.displayFormat, 'image');
      expect(image.hasImages, isTrue);
      expect(video.displayFormat, 'video');
      expect(video.hasVideo, isTrue);
    });
  });

  group('ContentPostProjection — single track', () {
    test('generated decoder 拒绝旧 identity/media dimension aliases', () {
      for (final noncanonical in <Map<String, Object?>>[
        <String, Object?>{
          ..._canonicalWire(postId: 'p1', contentType: 'image'),
          'id': 'p1',
        },
        <String, Object?>{
          ..._canonicalWire(postId: 'p1', contentType: 'image'),
          'type': 'image',
        },
        <String, Object?>{
          ..._canonicalWire(postId: 'p1', contentType: 'image'),
          'imageUrls': const <String>[],
        },
        <String, Object?>{
          ..._canonicalWire(postId: 'p1', contentType: 'image'),
          'imageWidth': 800,
          'imageHeight': 600,
        },
        <String, Object?>{
          ..._canonicalWire(postId: 'v1', contentType: 'video'),
          'videoWidth': 1920,
          'videoHeight': 1080,
        },
      ]) {
        expect(
          () => ContentPostProjection.fromWire(noncanonical),
          throwsFormatException,
        );
      }
    });

    test('canonical round-trip 只输出当前字段并保持尺寸', () {
      final projection = ContentPostProjection.fromWire(
        _canonicalWire(
          postId: 'p2',
          contentType: 'image',
          width: 1080,
          height: 720,
        ),
      );
      final wire = projection.toWire();

      expect(wire['postId'], 'p2');
      expect(wire['contentType'], 'image');
      expect(wire['width'], 1080);
      expect(wire['height'], 720);
      expect(wire, isNot(contains('id')));
      expect(wire, isNot(contains('type')));
      expect(wire, isNot(contains('imageUrls')));
    });

    test('未知 contentType 在 App mapper 边界 fail closed', () {
      final projection = ContentPostProjection.fromWire(
        _canonicalWire(postId: 'unknown', contentType: 'future-type'),
      );

      expect(
        () => ContentPostViewData.fromWire(projection),
        throwsFormatException,
      );
    });

    test('缺少 canonical required fields 不降级为伪对象', () {
      expect(
        () => ContentPostProjection.fromWire(const <String, Object?>{}),
        throwsFormatException,
      );
      final missingCounts = _canonicalWire(
        postId: 'missing-counts',
        contentType: 'image',
      )..remove('likeCount');
      expect(
        () => ContentPostProjection.fromWire(missingCounts),
        throwsFormatException,
      );
    });
  });

  group('ContentPostViewData — canonical presentation', () {
    test('四种内容共享同一个 ViewData 类型，不再按 DTO 子类分轨', () {
      final items = <ContentPostViewData>[
        for (final type in const <String>['image', 'video', 'article', 'micro'])
          _decodeView(
            _canonicalWire(
              postId: 'post-$type',
              contentType: type,
              contentIdentity: type == 'micro' ? 'moment' : 'work',
              videoUrl: type == 'video' ? 'https://example.com/v.mp4' : null,
            ),
          ),
      ];

      expect(items, everyElement(isA<ContentPostViewData>()));
      expect(items.map((item) => item.type), <String>[
        'image',
        'video',
        'article',
        'micro',
      ]);
    });

    test('canonical fixture 的 image/video 尺寸均有效', () {
      for (final item in <ContentPostViewData>[
        ...ContentMockData.discoveryPhotoData,
        ...ContentMockData.discoveryVideoData,
      ]) {
        expect(item.width, isNotNull, reason: 'postId=${item.id} width');
        expect(item.height, isNotNull, reason: 'postId=${item.id} height');
        expect(item.width!, greaterThan(0));
        expect(item.height!, greaterThan(0));
        expect(item.aspectRatio, greaterThan(0));
      }
    });

    test('copyWith 只更新 App presentation 字段并保持 canonical identity', () {
      final original = _decodeView(
        _canonicalWire(
          postId: 'copy-1',
          contentType: 'article',
          contentIdentity: 'work',
          title: 'Original',
          body: 'Body',
        ),
      );
      final updated = original.copyWith(title: 'Updated');

      expect(updated.title, 'Updated');
      expect(updated.id, original.id);
      expect(updated.type, original.type);
      expect(updated.identity, original.identity);
      expect(updated.body, original.body);
    });
  });
}
