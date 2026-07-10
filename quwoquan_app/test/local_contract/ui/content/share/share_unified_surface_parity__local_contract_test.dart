import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';

void main() {
  group('分享模板：统一 model 单路径产出 (D1b/T2)', () {
    void expectSurfaceTemplate(PostBaseDto dto, {Map<String, dynamic>? wire}) {
      final template = ContentShareTemplateBuilder.build(
        surfaceView: ContentSurfaceViewMapper.fromDto(dto, wire: wire),
        enableIdentityTemplate: true,
      );
      expect(template.shareTitle, isNotEmpty,
          reason: 'shareTitle 必须由 surfaceView 种子产出');
      expect(template.coverUrl, isNotNull);
      expect(template.layout, isNotEmpty);
      expect(template.permission, 'public');
    }

    test('image 帖同源', () {
      expectSurfaceTemplate(
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
          'createdAt': '2026-01-01T00:00:00.000Z',
        }),
      );
    });

    test('video 帖同源', () {
      expectSurfaceTemplate(
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
          'createdAt': '2026-01-01T00:00:00.000Z',
        }),
      );
    });

    test('article 帖同源', () {
      expectSurfaceTemplate(
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
          'createdAt': '2026-01-01T00:00:00.000Z',
        }),
      );
    });

    test('micro 帖同源', () {
      expectSurfaceTemplate(
        MicroPostDto.fromMap(<String, dynamic>{
          '_id': 'm1',
          'postId': 'm1',
          'type': 'micro',
          'contentType': 'micro',
          'identity': 'moment',
          'authorId': 'a4',
          'displayName': '作者丁',
          'authorAvatarUrl': '',
          'body': '随手一条点滴',
          'likeCount': 0,
          'commentCount': 0,
          'shareCount': 0,
          'createdAt': '2026-01-01T00:00:00.000Z',
        }),
      );
    });
  });
}
