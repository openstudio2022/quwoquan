import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final _mediaResolver = MediaDeliveryResolver(
  MediaEndpointConfig(
    avatarBaseUrl: 'https://avatar.example.test',
    imageBaseUrl: 'https://image.example.test',
    videoBaseUrl: 'https://video.example.test',
    attachmentBaseUrl: 'https://attachment.example.test',
  ),
);

ContentPostViewData _video({
  required String postId,
  String? thumbnailUrl,
  String? coverUrl,
}) => ContentPostViewData.fromWire(
  ContentPostProjection(
    postId: postId,
    contentType: 'video',
    contentIdentity: 'work',
    authorId: 'author',
    authorDisplayName: '作者',
    authorAvatarUrl: '',
    videoUrl: 'media/video/s/fixture/video/v1/clip.mp4',
    thumbnailUrl: thumbnailUrl,
    coverUrl: coverUrl,
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.utc(2026),
  ),
);

void main() {
  group('video display cover priority', () {
    test('视频封面优先 thumbnailUrl 并与播放 poster 同源', () {
      final dto = _video(
        postId: 'video-thumb-first',
        thumbnailUrl: 'media/image/s/fixture/video/v1/thumb.jpg',
        coverUrl: 'media/image/s/fixture/video/v1/cover.jpg',
      );

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        mediaResolver: _mediaResolver,
      );

      expect(dto.primaryVisualUrl, contains('/thumb.jpg'));
      expect(view.cover!.url, contains('/thumb.jpg'));
      expect(view.video!.thumbnailUrl, equals(view.cover!.url));
      expect(view.video!.url, contains('/clip.mp4'));
    });

    test('thumbnailUrl 缺失时只回退同源 coverUrl', () {
      final dto = _video(
        postId: 'video-cover-fallback',
        coverUrl: 'media/image/s/fixture/video/v1/cover.jpg',
      );

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        mediaResolver: _mediaResolver,
      );

      expect(dto.mediaVideoCoverUrl, contains('/cover.jpg'));
      expect(view.cover!.url, contains('/cover.jpg'));
      expect(view.video!.thumbnailUrl, equals(view.cover!.url));
    });

    test('缺封面视频不把 videoUrl 当 image poster', () {
      final dto = _video(postId: 'video-no-cover');

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        mediaResolver: _mediaResolver,
      );

      expect(dto.mediaVideoCoverUrl, isEmpty);
      expect(dto.primaryVisualUrl, isEmpty);
      expect(view.cover, isNull);
      expect(view.video!.thumbnailUrl, isEmpty);
      expect(view.video!.url, contains('/clip.mp4'));
    });
  });
}
