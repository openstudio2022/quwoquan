// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// DEC-033 四路投影媒体交付绑定薄改（post 媒体 + 作者头像路）：
// App 业务 DTO/mapper 必须保留契约投影携带的资产标识与 accessMode，
// 缺席时保持缺席，禁止以 postId/personaId 冒充媒体资产标识。

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/content_surface_view_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/post/content_post_contract_fixture.dart';

final _mediaResolver = MediaDeliveryResolver(
  MediaEndpointConfig(
    avatarBaseUrl: 'https://avatar.example.test',
    imageBaseUrl: 'https://image.example.test',
    videoBaseUrl: 'https://video.example.test',
    attachmentBaseUrl: 'https://attachment.example.test',
  ),
);

const _imageUrl = 'media/image/s/fixture/photo1/v1/1.jpg';
const _videoUrl = 'media/video/s/fixture/video1/v1/clip.mp4';
const _posterUrl = 'media/image/s/fixture/video1/v1/poster.jpg';
const _avatarUrl = 'media/avatar/s/fixture/a1/v1/avatar.png';

void main() {
  group('ContentPostViewData.fromWire — 媒体交付绑定保留', () {
    test('signed_grant 绑定在场时 mediaItems 与作者头像绑定完整透传', () {
      final dto = ContentPostViewData.fromWire(
        contentPostProjectionFixture(
          postId: 'photo1',
          contentType: 'image',
          contentIdentity: 'work',
          authorId: 'persona-a1',
          authorAvatarUrl: _avatarUrl,
          authorAvatarAssetId: 'asset-avatar-1',
          authorAvatarAccessMode: MediaDeliveryAccessMode.signedGrant,
          mediaUrls: const <String>[_imageUrl],
          mediaItems: const <PostMediaItem>[
            PostMediaItem(
              kind: 'image',
              url: _imageUrl,
              mediaAssetId: 'asset-img-1',
              accessMode: MediaDeliveryAccessMode.signedGrant,
              coverAssetId: 'asset-cover-1',
            ),
          ],
        ),
      );

      expect(dto.authorAvatarAssetId, 'asset-avatar-1');
      expect(dto.authorAvatarAccessMode, MediaDeliveryAccessMode.signedGrant);
      expect(dto.mediaItems, hasLength(1));
      expect(dto.mediaItems.single.mediaAssetId, 'asset-img-1');
      expect(
        dto.mediaItems.single.accessMode,
        MediaDeliveryAccessMode.signedGrant,
      );
      expect(dto.mediaItems.single.coverAssetId, 'asset-cover-1');
    });

    test('存量 public 投影未携带绑定字段时缺席为 null，不以对象 id 冒充', () {
      final dto = ContentPostViewData.fromWire(
        contentPostProjectionFixture(
          postId: 'photo-legacy',
          contentType: 'image',
          authorId: 'persona-a1',
          mediaUrls: const <String>[_imageUrl],
        ),
      );

      expect(dto.authorAvatarAssetId, isNull);
      expect(dto.authorAvatarAccessMode, isNull);
      expect(dto.mediaItems, isEmpty);
      // 缺席不得以 postId/personaId 造值。
      expect(dto.authorAvatarAssetId, isNot('photo-legacy'));
      expect(dto.authorAvatarAssetId, isNot('persona-a1'));
    });

    test('copyWith 保留媒体交付绑定字段', () {
      final dto = ContentPostViewData.fromWire(
        contentPostProjectionFixture(
          postId: 'photo1',
          contentType: 'image',
          authorAvatarAssetId: 'asset-avatar-1',
          authorAvatarAccessMode: MediaDeliveryAccessMode.public,
          mediaUrls: const <String>[_imageUrl],
          mediaItems: const <PostMediaItem>[
            PostMediaItem(
              kind: 'image',
              url: _imageUrl,
              mediaAssetId: 'asset-img-1',
              accessMode: MediaDeliveryAccessMode.public,
            ),
          ],
        ),
      );

      final copied = dto.copyWith(title: '改标题');

      expect(copied.authorAvatarAssetId, 'asset-avatar-1');
      expect(copied.authorAvatarAccessMode, MediaDeliveryAccessMode.public);
      expect(copied.mediaItems.single.mediaAssetId, 'asset-img-1');
    });
  });

  group('ContentSurfaceViewMapper — 真实资产标识与 accessMode 透传', () {
    test('图片 delivery 绑定条目 mediaAssetId 与 accessMode，不冒充 postId', () {
      final dto = ContentPostViewData.fromWire(
        contentPostProjectionFixture(
          postId: 'photo1',
          contentType: 'image',
          contentIdentity: 'work',
          authorId: 'persona-a1',
          authorAvatarUrl: _avatarUrl,
          authorAvatarAssetId: 'asset-avatar-1',
          authorAvatarAccessMode: MediaDeliveryAccessMode.signedGrant,
          mediaUrls: const <String>[_imageUrl],
          mediaItems: const <PostMediaItem>[
            PostMediaItem(
              kind: 'image',
              url: _imageUrl,
              mediaAssetId: 'asset-img-1',
              accessMode: MediaDeliveryAccessMode.signedGrant,
            ),
          ],
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        mediaResolver: _mediaResolver,
      );

      expect(view.images, hasLength(1));
      expect(view.images.single.delivery.assetId, 'asset-img-1');
      expect(view.images.single.delivery.assetId, isNot(dto.id));
      expect(
        view.images.single.delivery.accessMode,
        MediaDeliveryAccessMode.signedGrant,
      );
      expect(view.author.avatar, isNotNull);
      expect(view.author.avatar!.assetId, 'asset-avatar-1');
      expect(view.author.avatar!.assetId, isNot(dto.personaId));
      expect(
        view.author.avatar!.accessMode,
        MediaDeliveryAccessMode.signedGrant,
      );
    });

    test('video delivery 绑定条目 mediaAssetId，poster 绑定 coverAssetId', () {
      final dto = ContentPostViewData.fromWire(
        contentPostProjectionFixture(
          postId: 'video1',
          contentType: 'video',
          contentIdentity: 'work',
          videoUrl: _videoUrl,
          thumbnailUrl: _posterUrl,
          mediaItems: const <PostMediaItem>[
            PostMediaItem(
              kind: 'video',
              url: _videoUrl,
              mediaAssetId: 'asset-video-1',
              accessMode: MediaDeliveryAccessMode.signedGrant,
              coverUrl: _posterUrl,
              coverAssetId: 'asset-poster-1',
            ),
          ],
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        mediaResolver: _mediaResolver,
      );

      expect(view.video, isNotNull);
      expect(view.video!.delivery.assetId, 'asset-video-1');
      expect(view.video!.delivery.assetId, isNot(dto.id));
      expect(
        view.video!.delivery.accessMode,
        MediaDeliveryAccessMode.signedGrant,
      );
      expect(view.cover, isNotNull);
      expect(view.cover!.delivery.assetId, 'asset-poster-1');
      expect(
        view.cover!.delivery.accessMode,
        MediaDeliveryAccessMode.signedGrant,
      );
    });

    test('绑定缺席时资产标识保持缺席，不以 postId/personaId 造值', () {
      final dto = ContentPostViewData.fromWire(
        contentPostProjectionFixture(
          postId: 'photo-legacy',
          contentType: 'image',
          authorId: 'persona-a1',
          authorAvatarUrl: _avatarUrl,
          mediaUrls: const <String>[_imageUrl],
        ),
      );

      final view = ContentSurfaceViewMapper.fromDto(
        dto,
        mediaResolver: _mediaResolver,
      );

      expect(view.images, hasLength(1));
      expect(view.images.single.delivery.assetId, isEmpty);
      expect(view.images.single.delivery.accessMode, isNull);
      expect(view.author.avatar, isNotNull);
      expect(view.author.avatar!.assetId, isEmpty);
      expect(view.author.avatar!.assetId, isNot('persona-a1'));
      expect(view.author.avatar!.accessMode, isNull);
    });
  });
}
