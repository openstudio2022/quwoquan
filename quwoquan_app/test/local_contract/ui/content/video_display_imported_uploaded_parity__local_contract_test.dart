import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_read_model_projection.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';

void main() {
  test('导入视频与用户上传视频使用同一封面展示合同', () {
    final imported = _videoWire(
      id: 'imported-video',
      videoUrl: 'media/video/s/imported-video/post/imported-video/v1/clip.mp4',
      thumbnailUrl:
          'media/video/s/imported-video/post/imported-video/v1/thumb.jpg'
          '?variant=thumb&t=0',
      coverStrategy: 'first_frame',
      coverFrameTimeMs: 0,
    );
    final uploaded = _videoWire(
      id: 'uploaded-video',
      videoUrl: 'media/video/s/uploaded-video/post/uploaded-video/v1/clip.mp4',
      thumbnailUrl:
          'media/image/s/uploaded-image/post/uploaded-video/v1/manual-cover.jpg',
      coverStrategy: 'manual',
      coverFrameTimeMs: 3200,
    );

    final importedView = ContentSurfaceViewMapper.fromDto(
      contentPostViewDataFromReadModelMap(imported),
      wire: imported,
      mediaResolver: _mediaResolver,
    );
    final uploadedView = ContentSurfaceViewMapper.fromDto(
      contentPostViewDataFromReadModelMap(uploaded),
      wire: uploaded,
      mediaResolver: _mediaResolver,
    );

    expect(importedView.video!.thumbnailUrl, importedView.cover!.url);
    expect(uploadedView.video!.thumbnailUrl, uploadedView.cover!.url);
    expect(importedView.video!.url, contains('/imported-video/'));
    expect(uploadedView.video!.url, contains('/uploaded-video/'));
    expect(importedView.video!.thumbnailUrl, contains('variant=thumb'));
    expect(uploadedView.video!.thumbnailUrl, contains('manual-cover.jpg'));
  });
}

final _mediaResolver = MediaDeliveryResolver(
  MediaEndpointConfig(
    avatarBaseUrl: 'https://cdn.example.test/media/avatar',
    imageBaseUrl: 'https://cdn.example.test/media/image',
    videoBaseUrl: 'https://cdn.example.test/media/video',
    attachmentBaseUrl: 'https://cdn.example.test/media/image',
  ),
);

Map<String, dynamic> _videoWire({
  required String id,
  required String videoUrl,
  required String thumbnailUrl,
  required String coverStrategy,
  required int coverFrameTimeMs,
}) {
  return <String, dynamic>{
    'id': id,
    'type': 'video',
    'identity': 'work',
    'authorId': 'author',
    'displayName': '作者',
    'avatarUrl': '',
    'videoUrl': videoUrl,
    'thumbnailUrl': thumbnailUrl,
    'coverUrl': thumbnailUrl,
    'coverStrategy': coverStrategy,
    'coverFrameTimeMs': coverFrameTimeMs,
    'durationMs': 12000,
    'width': 1080,
    'height': 1920,
    'createdAt': '2026-01-01T00:00:00.000Z',
  };
}
