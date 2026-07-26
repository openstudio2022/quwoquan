import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/remote/content_post_projection_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('详情读取把 canonical mediaUrls 投影为图片展示字段', () {
    final detail = decodeContentPostDetailSlice(<String, Object?>{
      'postId': 'post-image-canonical',
      'contentType': 'image',
      'status': 'pending_review',
      'mediaUrls': <String>['media/image/s/asset/post-image-canonical'],
    });

    expect(detail.post.mediaUrls, <String>[
      'media/image/s/asset/post-image-canonical',
    ]);
    final dto = const ContentPostProjectionMapper().toDto(detail.post);
    expect(dto.imageUrls, detail.post.mediaUrls);
  });

  test('详情读取不接受已退役 imageUrls 别名', () {
    final projection = decodeContentPostProjection(<String, Object?>{
      'postId': 'post-image-retired-alias',
      'contentType': 'image',
      'imageUrls': <String>['https://legacy.example.test/image.jpg'],
    });

    expect(projection.mediaUrls, isEmpty);
  });

  test('视频详情从 canonical mediaUrls 形成播放地址', () {
    final projection = decodeContentPostProjection(<String, Object?>{
      'postId': 'post-video-canonical',
      'contentType': 'video',
      'mediaUrls': <String>['media/video/s/asset/post-video-canonical'],
    });

    final dto = const ContentPostProjectionMapper().toDto(projection);
    expect(dto.videoUrl, 'media/video/s/asset/post-video-canonical');
    expect(dto.imageUrls, isEmpty);
  });
}
