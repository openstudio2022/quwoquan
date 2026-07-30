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

  test('首页视频投影保留同 asset/version 的 HLS/CMAF typed 绑定', () {
    final projection = decodeContentPostProjection(<String, Object?>{
      'postId': 'post-video-adaptive',
      'contentType': 'video',
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
    final wire = const ContentPostProjectionMapper().toWire(projection);
    expect(wire['mediaAssetId'], 'mas-video-adaptive');
    expect(wire['mediaAssetVersion'], 3);
    expect(
      wire['hlsCmafMasterManifestUrl'],
      'media/video/m/asset/mas-video-adaptive/v3/hls/master.m3u8',
    );
    expect(wire['hlsCmafDescriptorVersion'], 1);
  });
}
