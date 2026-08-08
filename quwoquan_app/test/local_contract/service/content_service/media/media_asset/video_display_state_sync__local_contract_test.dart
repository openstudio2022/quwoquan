import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_read_model_projection.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';

/// 媒体 CDN base URL 是 fail-closed 的运行时配置，裸 `flutter test` 不注入。
/// 本用例验证的是「三个消费面同源」，因此自己声明确定的交付端点，
/// 而不是依赖环境注入。
final _endpoints = MediaEndpointConfig(
  avatarBaseUrl: 'https://cdn.example.test/media/avatar',
  imageBaseUrl: 'https://cdn.example.test/media/image',
  videoBaseUrl: 'https://cdn.example.test/media/video',
  attachmentBaseUrl: 'https://cdn.example.test/media/image',
);

void main() {
  test('feed/card/viewer 视频状态同源消费 videoUrl 与 video cover', () {
    // read model 已单轨收敛到 canonical Post 字段名，测试 wire 必须同步。
    final wire = <String, dynamic>{
      'postId': 'video-sync',
      'contentType': 'video',
      'contentIdentity': 'work',
      'authorId': 'author',
      'authorDisplayName': '作者',
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

    final dto = contentPostViewDataFromReadModelMap(wire);
    final view = ContentSurfaceViewMapper.fromDto(
      dto,
      wire: wire,
      mediaResolver: MediaDeliveryResolver(_endpoints),
    );

    expect(dto.mediaVideoUrl, 'media/video/s/fixture/video-sync/v1/clip.mp4');
    expect(
      dto.mediaVideoCoverUrl,
      'media/image/s/fixture/video-sync/v1/thumb.jpg',
    );
    expect(
      view.video!.url,
      resolveContentVideoUrl(dto.mediaVideoUrl, endpointConfig: _endpoints),
    );
    expect(
      view.video!.thumbnailUrl,
      resolveContentMediaUrl(
        dto.mediaVideoCoverUrl,
        endpointConfig: _endpoints,
      ),
    );
    expect(view.cover!.url, view.video!.thumbnailUrl);
    expect(view.video!.durationMs, 15000);
    expect(view.video!.aspectRatio, closeTo(1080 / 1920, 0.001));
  });
}
