import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/remote/content_post_projection_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('详情读取把 canonical mediaUrls 投影为图片展示字段', () {
    final detail = decodeContentPostDetailSlice(<String, Object?>{
      'postId': 'post-image-canonical',
      'contentType': 'image',
      'status': 'pending_review',
      'visibility': 'private',
      'mediaUrls': <String>['media/image/s/asset/post-image-canonical'],
      'likeCount': 0,
      'commentCount': 0,
      'shareCount': 0,
      'viewCount': 0,
      'createdAt': '2026-08-01T00:00:00Z',
      'updatedAt': '2026-08-01T00:00:00Z',
    });

    expect(detail.mediaUrls, <String>[
      'media/image/s/asset/post-image-canonical',
    ]);
  });

  test('详情读取不接受已退役 imageUrls 别名', () {
    expect(
      () => ContentPostProjection.fromWire(<String, Object?>{
        ..._projectionWire(
          postId: 'post-image-retired-alias',
          contentType: 'image',
        ),
        'imageUrls': <String>['https://noncanonical.example.test/image.jpg'],
      }),
      throwsFormatException,
    );
  });

  test('视频详情从 canonical mediaUrls 形成播放地址', () {
    final projection = ContentPostProjection.fromWire(<String, Object?>{
      ..._projectionWire(
        postId: 'post-video-canonical',
        contentType: 'video',
      ),
      'mediaUrls': <String>['media/video/s/asset/post-video-canonical'],
    });

    final dto = const ContentPostProjectionMapper().toDto(projection);
    expect(dto.videoUrl, 'media/video/s/asset/post-video-canonical');
    expect(dto.imageUrls, isEmpty);
  });

  test('首页视频投影保留同 asset/version 的 HLS/CMAF typed 绑定', () {
    final projection = ContentPostProjection.fromWire(<String, Object?>{
      ..._projectionWire(
        postId: 'post-video-adaptive',
        contentType: 'video',
      ),
      'videoUrl': 'media/video/m/asset/mas-video-adaptive/v3/delivery.mp4',
      'mediaAssetId': 'mas-video-adaptive',
      'mediaAssetVersion': 3,
      'hlsCmafMasterManifestUrl':
          'media/video/m/asset/mas-video-adaptive/v3/hls/master.m3u8',
      'hlsCmafDescriptorVersion': 1,
    });

    expect(projection.mediaAssetId, 'mas-video-adaptive');
    expect(projection.mediaAssetVersion, 3);
    expect(
      projection.hlsCmafMasterManifestUrl,
      'media/video/m/asset/mas-video-adaptive/v3/hls/master.m3u8',
    );
    expect(projection.hlsCmafDescriptorVersion, 1);
    final wire = projection.toWire();
    expect(wire['mediaAssetId'], 'mas-video-adaptive');
    expect(wire['mediaAssetVersion'], 3);
    expect(
      wire['hlsCmafMasterManifestUrl'],
      'media/video/m/asset/mas-video-adaptive/v3/hls/master.m3u8',
    );
    expect(wire['hlsCmafDescriptorVersion'], 1);
  });
}

Map<String, Object?> _projectionWire({
  required String postId,
  required String contentType,
}) => <String, Object?>{
  'postId': postId,
  'contentType': contentType,
  'likeCount': 0,
  'commentCount': 0,
  'shareCount': 0,
};
