import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';

void main() {
  test('feed/card/viewer 视频状态同源消费 videoUrl 与 video cover', () {
    final wire = <String, dynamic>{
      '_id': 'video-sync',
      'postId': 'video-sync',
      'contentType': 'video',
      'identity': 'work',
      'authorId': 'author',
      'displayName': '作者',
      'authorAvatarUrl': '',
      'videoUrl': 'media/video/s/fixture/video-sync/v1/clip.mp4',
      'thumbnailUrl': 'media/image/s/fixture/video-sync/v1/thumb.jpg',
      'coverUrl': 'media/image/s/fixture/video-sync/v1/thumb.jpg',
      'coverStrategy': 'manual',
      'coverFrameTimeMs': 2400,
      'durationMs': 15000,
      'width': 1080,
      'height': 1920,
      'createdAt': '2026-01-01T00:00:00.000Z',
    };

    final dto = postBaseDtoFromMap(wire);
    final view = ContentSurfaceViewMapper.fromDto(dto, wire: wire);

    expect(dto.mediaVideoUrl, contains('/clip.mp4'));
    expect(dto.mediaVideoCoverUrl, contains('/thumb.jpg'));
    expect(view.video!.url, dto.mediaVideoUrl);
    expect(view.video!.thumbnailUrl, dto.mediaVideoCoverUrl);
    expect(view.cover!.url, dto.mediaVideoCoverUrl);
    expect(view.video!.durationMs, 15000);
    expect(view.video!.aspectRatio, closeTo(1080 / 1920, 0.001));
  });
}
