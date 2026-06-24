import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';

void main() {
  group('video display cover priority', () {
    test('视频封面优先 thumbnailUrl 并与播放 poster 同源', () {
      final dto = VideoPostDto.fromMap(<String, dynamic>{
        '_id': 'video-thumb-first',
        'postId': 'video-thumb-first',
        'contentType': 'video',
        'identity': 'work',
        'authorId': 'author',
        'displayName': '作者',
        'authorAvatarUrl': '',
        'videoUrl': 'media/video/s/fixture/video/v1/clip.mp4',
        'thumbnailUrl': 'media/image/s/fixture/video/v1/thumb.jpg',
        'coverUrl': 'media/image/s/fixture/video/v1/cover.jpg',
        'createdAt': '2026-01-01T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(dto.primaryVisualUrl, contains('/thumb.jpg'));
      expect(view.cover!.url, contains('/thumb.jpg'));
      expect(view.video!.thumbnailUrl, equals(view.cover!.url));
      expect(view.video!.url, contains('/clip.mp4'));
    });

    test('thumbnailUrl 缺失时只回退同源 coverUrl', () {
      final dto = VideoPostDto.fromMap(<String, dynamic>{
        '_id': 'video-cover-fallback',
        'postId': 'video-cover-fallback',
        'contentType': 'video',
        'identity': 'work',
        'authorId': 'author',
        'displayName': '作者',
        'authorAvatarUrl': '',
        'videoUrl': 'media/video/s/fixture/video/v1/clip.mp4',
        'coverUrl': 'media/image/s/fixture/video/v1/cover.jpg',
        'createdAt': '2026-01-01T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(dto.mediaVideoCoverUrl, contains('/cover.jpg'));
      expect(view.cover!.url, contains('/cover.jpg'));
      expect(view.video!.thumbnailUrl, equals(view.cover!.url));
    });

    test('缺封面视频不把 videoUrl 当 image poster', () {
      final dto = VideoPostDto.fromMap(<String, dynamic>{
        '_id': 'video-no-cover',
        'postId': 'video-no-cover',
        'contentType': 'video',
        'identity': 'work',
        'authorId': 'author',
        'displayName': '作者',
        'authorAvatarUrl': '',
        'videoUrl': 'media/video/s/fixture/video/v1/clip.mp4',
        'createdAt': '2026-01-01T00:00:00.000Z',
      });

      final view = ContentSurfaceViewMapper.fromDto(dto);

      expect(dto.mediaVideoCoverUrl, isEmpty);
      expect(dto.primaryVisualUrl, isEmpty);
      expect(view.cover, isNull);
      expect(view.video!.thumbnailUrl, isEmpty);
      expect(view.video!.url, contains('/clip.mp4'));
    });
  });
}
