import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';

void main() {
  group('ContentSurfaceViewMapper.fromDto — 四媒体类型投影契约 (T1)', () {
    test('image 帖 → kind.image，多图 + 作者/统计字段对齐', () {
      final dto = PhotoPostDto.fromMap(<String, dynamic>{
        '_id': 'photo1',
        'postId': 'photo1',
        'type': 'photo',
        'contentType': 'image',
        'identity': 'work',
        'authorId': 'a1',
        'displayName': '作者甲',
        'authorAvatarUrl': 'https://example.com/a1.png',
        'imageUrls': <String>['https://img/1.jpg', 'https://img/2.jpg'],
        'coverUrl': 'https://img/cover.jpg',
        'likeCount': 10,
        'commentCount': 2,
        'shareCount': 3,
        'favoriteCount': 4,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(view.postId, 'photo1');
      expect(view.kind, ContentSurfaceKind.image);
      expect(view.contentType, dto.type);
      expect(view.author.id, 'a1');
      expect(view.author.displayName, '作者甲');
      expect(view.images.map((e) => e.url).toList(),
          <String>['https://img/1.jpg', 'https://img/2.jpg']);
      expect(view.video, isNull);
      expect(view.stats.like, 10);
      expect(view.stats.comment, 2);
      expect(view.stats.share, 3);
      expect(view.stats.favorite, 4);
    });

    test('video 帖 → kind.video，单视频 ref + 时长', () {
      final dto = VideoPostDto.fromMap(<String, dynamic>{
        '_id': 'video1',
        'postId': 'video1',
        'type': 'video',
        'contentType': 'video',
        'identity': 'work',
        'authorId': 'a2',
        'displayName': '作者乙',
        'authorAvatarUrl': '',
        'videoUrl': 'https://v/1.mp4',
        'thumbnailUrl': 'https://v/thumb.jpg',
        'durationMs': 12000,
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(view.kind, ContentSurfaceKind.video);
      expect(view.hasVideo, isTrue);
      expect(view.video!.url, 'https://v/1.mp4');
      expect(view.video!.thumbnailUrl, 'https://v/thumb.jpg');
      expect(view.video!.durationMs, 12000);
      expect(view.hasImages, isFalse);
    });

    test('article 帖 → kind.article，标题/正文/封面 + wire 模板字段', () {
      final dto = ArticlePostDto.fromMap(<String, dynamic>{
        '_id': 'article1',
        'postId': 'article1',
        'type': 'article',
        'contentType': 'article',
        'identity': 'work',
        'authorId': 'a3',
        'displayName': '作者丙',
        'authorAvatarUrl': '',
        'title': '统一展示标题',
        'body': '正文摘要',
        'coverUrl': 'https://img/article-cover.jpg',
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        wire: <String, dynamic>{
          'articleTemplate': 'modern',
          'articleFontPreset': 'serif',
          'tagRefs': <String>['校园', '摄影'],
        },
      );

      expect(view.kind, ContentSurfaceKind.article);
      expect(view.title, '统一展示标题');
      expect(view.body, '正文摘要');
      expect(view.cover, isNotNull);
      expect(view.cover!.url, 'https://img/article-cover.jpg');
      expect(view.articleTemplate, 'modern');
      expect(view.articleFontPreset, 'serif');
      expect(view.tags, <String>['校园', '摄影']);
    });

    test('micro 帖 → kind.micro，仅正文，无媒体', () {
      final dto = MicroPostDto.fromMap(<String, dynamic>{
        '_id': 'micro1',
        'postId': 'micro1',
        'type': 'micro',
        'contentType': 'micro',
        'identity': 'moment',
        'authorId': 'a4',
        'displayName': '作者丁',
        'authorAvatarUrl': '',
        'body': '随手一条',
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(view.kind, ContentSurfaceKind.micro);
      expect(view.body, '随手一条');
      expect(view.hasImages, isFalse);
      expect(view.hasVideo, isFalse);
      expect(view.cover, isNull);
    });

    test('intersectionReasons 透传到统一 model', () {
      final dto = MicroPostDto.fromMap(<String, dynamic>{
        '_id': 'micro2',
        'postId': 'micro2',
        'type': 'micro',
        'contentType': 'micro',
        'identity': 'moment',
        'authorId': 'a5',
        'displayName': '作者戊',
        'authorAvatarUrl': '',
        'body': '带交集理由',
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
        'intersectionReasons': <Map<String, dynamic>>[
          <String, dynamic>{
            'dimension': 'alumni',
            'tagRefs': <String>['tag:school:neworiental'],
            'relationKind': 'circle',
            'relationObjectId': 'circle1',
            'label': '校友圈',
            'sharedCount': 12,
            'strength': 0.8,
            'displayText': '你和 TA 都来自新东方校友圈',
            'actionType': 'open',
            'actionTargetId': 'circle1',
            'source': 'rec',
          },
        ],
      });

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(view.hasIntersectionReasons, isTrue);
      expect(view.intersectionReasons, isA<List<IntersectionReason>>());
      expect(view.intersectionReasons.first.displayText,
          '你和 TA 都来自新东方校友圈');
    });

    test('时间语义：createdAt 用真实创作时间，updatedAt/publishedAt 透传 (T1)', () {
      final dto = ArticlePostDto.fromMap(<String, dynamic>{
        '_id': 'time1',
        'postId': 'time1',
        'type': 'article',
        'contentType': 'article',
        'identity': 'work',
        'authorId': 'a7',
        'displayName': '作者庚',
        'authorAvatarUrl': '',
        'title': '时间语义文章',
        'body': '正文',
        'coverUrl': '',
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
        'updatedAt': '2026-02-01T00:00:00.000Z',
        'publishedAt': '2026-01-03T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(view.createdAt, DateTime.utc(2026, 1, 1));
      expect(view.updatedAt, DateTime.utc(2026, 2, 1));
      expect(view.publishedAt, DateTime.utc(2026, 1, 3));
      // updatedAt 明显晚于 createdAt → 视为实质更新。
      expect(view.hasMeaningfulUpdate, isTrue);
    });

    test('时间语义：未更新内容只有 createdAt，hasMeaningfulUpdate=false (T1)', () {
      final dto = ArticlePostDto.fromMap(<String, dynamic>{
        '_id': 'time2',
        'postId': 'time2',
        'type': 'article',
        'contentType': 'article',
        'identity': 'work',
        'authorId': 'a8',
        'displayName': '作者辛',
        'authorAvatarUrl': '',
        'title': '未更新文章',
        'body': '正文',
        'coverUrl': '',
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(view.createdAt, DateTime.utc(2026, 1, 1));
      expect(view.updatedAt, isNull);
      expect(view.hasMeaningfulUpdate, isFalse);
    });

    test('时间语义：createdAt 缺失时不以 publishedAt 借壳（契约纯洁） (T1)', () {
      final dto = ArticlePostDto.fromMap(<String, dynamic>{
        '_id': 'time3',
        'postId': 'time3',
        'type': 'article',
        'contentType': 'article',
        'identity': 'work',
        'authorId': 'a9',
        'displayName': '作者壬',
        'authorAvatarUrl': '',
        'title': '仅有发布时间',
        'body': '正文',
        'coverUrl': '',
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'favoriteCount': 0,
        'publishedAt': '2026-01-05T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(view.createdAt, dto.createdAt);
      expect(view.createdAt, isNot(equals(view.publishedAt)));
      expect(view.publishedAt, DateTime.utc(2026, 1, 5));
    });

    test('referral 上下文透传（不影响展示字段）', () {
      final dto = MicroPostDto.fromMap(<String, dynamic>{
        '_id': 'micro3',
        'postId': 'micro3',
        'type': 'micro',
        'contentType': 'micro',
        'identity': 'moment',
        'authorId': 'a6',
        'displayName': '作者己',
        'authorAvatarUrl': '',
        'body': 'x',
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        referral: const ContentSurfaceReferral(
          position: 7,
          feedRequestId: 'req-123',
        ),
      );

      expect(view.referral.position, 7);
      expect(view.referral.feedRequestId, 'req-123');
    });
  });
}
