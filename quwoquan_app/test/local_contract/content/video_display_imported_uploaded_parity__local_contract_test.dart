import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';

void main() {
  test('导入视频与用户上传视频使用同一封面展示合同', () {
    final imported = _videoWire(
      id: 'imported-video',
      videoUrl: 'media/video/imported/clip.mp4',
      thumbnailUrl: 'media/video/imported/clip.mp4?variant=thumb&t=0',
      coverStrategy: 'first_frame',
      coverFrameTimeMs: 0,
    );
    final uploaded = _videoWire(
      id: 'uploaded-video',
      videoUrl: 'media/user/uploaded/clip.mp4',
      thumbnailUrl: 'media/user/uploaded/manual-cover.jpg',
      coverStrategy: 'manual',
      coverFrameTimeMs: 3200,
    );

    final importedView = ContentSurfaceViewMapper.fromDto(
      postBaseDtoFromMap(imported),
      wire: imported,
    );
    final uploadedView = ContentSurfaceViewMapper.fromDto(
      postBaseDtoFromMap(uploaded),
      wire: uploaded,
    );

    expect(importedView.video!.thumbnailUrl, importedView.cover!.url);
    expect(uploadedView.video!.thumbnailUrl, uploadedView.cover!.url);
    expect(importedView.video!.url, contains('imported/clip.mp4'));
    expect(uploadedView.video!.url, contains('uploaded/clip.mp4'));
    expect(importedView.video!.thumbnailUrl, contains('variant=thumb'));
    expect(uploadedView.video!.thumbnailUrl, contains('manual-cover.jpg'));
  });
}

Map<String, dynamic> _videoWire({
  required String id,
  required String videoUrl,
  required String thumbnailUrl,
  required String coverStrategy,
  required int coverFrameTimeMs,
}) {
  return <String, dynamic>{
    '_id': id,
    'postId': id,
    'contentType': 'video',
    'identity': 'work',
    'authorId': 'author',
    'displayName': '作者',
    'authorAvatarUrl': '',
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
