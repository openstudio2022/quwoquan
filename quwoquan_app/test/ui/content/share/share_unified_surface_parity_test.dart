import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';

void main() {
  group('分享模板：统一 model 双读与旧投影同源 (D1b/T2)', () {
    void expectParity(PostBaseDto dto, {Map<String, dynamic>? wire}) {
      final legacy = ContentShareTemplateBuilder.build(
        post: dto,
        enableIdentityTemplate: true,
        tags: const <String>['校园'],
      );
      final unified = ContentShareTemplateBuilder.build(
        post: dto,
        enableIdentityTemplate: true,
        tags: const <String>['校园'],
        surfaceView: ContentSurfaceViewMapper.fromDto(dto, wire: wire),
      );
      expect(unified.shareTitle, legacy.shareTitle,
          reason: 'shareTitle 必须同源');
      expect(unified.shareSummary, legacy.shareSummary,
          reason: 'shareSummary 必须同源');
      expect(unified.coverUrl, legacy.coverUrl, reason: 'coverUrl 必须同源');
      expect(unified.layout, legacy.layout);
      expect(unified.permission, legacy.permission);
    }

    test('image 帖同源', () {
      expectParity(
        PhotoPostDto.fromMap(<String, dynamic>{
          '_id': 'p1',
          'postId': 'p1',
          'type': 'photo',
          'contentType': 'image',
          'identity': 'work',
          'authorId': 'a1',
          'displayName': '作者甲',
          'authorAvatarUrl': '',
          'body': '美图配文',
          'imageUrls': <String>['https://img/1.jpg'],
          'coverUrl': 'https://img/cover.jpg',
          'likeCount': 0,
          'commentCount': 0,
          'shareCount': 0,
          'favoriteCount': 0,
          'createdAt': '2026-01-01T00:00:00.000Z',
        }),
      );
    });

    test('video 帖同源', () {
      expectParity(
        VideoPostDto.fromMap(<String, dynamic>{
          '_id': 'v1',
          'postId': 'v1',
          'type': 'video',
          'contentType': 'video',
          'identity': 'work',
          'authorId': 'a2',
          'displayName': '作者乙',
          'authorAvatarUrl': '',
          'body': '视频配文',
          'videoUrl': 'https://v/1.mp4',
          'thumbnailUrl': 'https://v/thumb.jpg',
          'likeCount': 0,
          'commentCount': 0,
          'shareCount': 0,
          'favoriteCount': 0,
          'createdAt': '2026-01-01T00:00:00.000Z',
        }),
      );
    });

    test('article 帖同源', () {
      expectParity(
        ArticlePostDto.fromMap(<String, dynamic>{
          '_id': 'art1',
          'postId': 'art1',
          'type': 'article',
          'contentType': 'article',
          'identity': 'work',
          'authorId': 'a3',
          'displayName': '作者丙',
          'authorAvatarUrl': '',
          'title': '长文标题',
          'body': '长文正文摘要内容',
          'coverUrl': 'https://img/art-cover.jpg',
          'likeCount': 0,
          'commentCount': 0,
          'shareCount': 0,
          'favoriteCount': 0,
          'createdAt': '2026-01-01T00:00:00.000Z',
        }),
      );
    });

    test('micro 帖同源', () {
      expectParity(
        MomentPostDto.fromMap(<String, dynamic>{
          '_id': 'm1',
          'postId': 'm1',
          'type': 'moment',
          'contentType': 'micro',
          'identity': 'moment',
          'authorId': 'a4',
          'displayName': '作者丁',
          'authorAvatarUrl': '',
          'body': '随手一条点滴',
          'likeCount': 0,
          'commentCount': 0,
          'shareCount': 0,
          'favoriteCount': 0,
          'createdAt': '2026-01-01T00:00:00.000Z',
        }),
      );
    });
  });
}
