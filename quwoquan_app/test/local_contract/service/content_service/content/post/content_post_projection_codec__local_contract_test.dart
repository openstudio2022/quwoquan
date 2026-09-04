// spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_codec.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('App projection encodes one canonical generated post wire', () {
    final createdAt = DateTime.utc(2026, 8, 6, 1, 2, 3);
    final updatedAt = DateTime.utc(2026, 8, 6, 2, 3, 4);
    final source = ContentPostViewData(
      id: 'post-projection-codec',
      type: 'video',
      identity: 'work',
      displayFormat: 'video',
      assistantUsePolicy: AssistantUsePolicy.inherit,
      authorId: 'persona-projection-codec',
      displayName: 'Canonical author',
      avatarUrl: 'media/image/s/avatar/projection-codec',
      authorAvatarAssetId: 'avatar-asset-1',
      authorAvatarAccessMode: MediaDeliveryAccessMode.signedGrant,
      authorRoleLabel: 'creator',
      authorIdentityTags: const <String>['verified_creator'],
      authorVerified: true,
      title: 'Canonical video',
      summary: 'Generated projection boundary',
      coverUrl: 'media/image/m/asset/cover-projection-codec',
      videoUrl: 'media/video/m/asset/video-projection-codec/v2/delivery.mp4',
      thumbnailUrl: 'media/image/m/asset/thumbnail-projection-codec',
      width: 1080,
      height: 1920,
      durationMs: 15000,
      mediaAssetId: 'video-projection-codec',
      mediaAssetVersion: 2,
      mediaItems: const <PostMediaItem>[
        PostMediaItem(
          kind: 'video',
          url: 'media/video/m/asset/video-projection-codec/v2/delivery.mp4',
          mediaAssetId: 'video-projection-codec',
          accessMode: MediaDeliveryAccessMode.signedGrant,
        ),
      ],
      hlsCmafMasterManifestUrl:
          'media/video/m/asset/video-projection-codec/v2/hls/master.m3u8',
      hlsCmafDescriptorVersion: 1,
      likeCount: 7,
      commentCount: 3,
      shareCount: 2,
      createdAt: createdAt,
      updatedAt: updatedAt,
      recallPath: 'following',
      supplySource: 'creator',
    );

    final projection = contentPostProjectionFromViewData(source);
    final wire = projection.toWire();

    expect(wire['postId'], 'post-projection-codec');
    expect(wire['contentType'], 'video');
    expect(wire['contentIdentity'], 'work');
    expect(wire['authorAvatarAssetId'], 'avatar-asset-1');
    expect(wire['authorAvatarAccessMode'], 'signed_grant');
    final mediaItems = wire['mediaItems']! as List<Object?>;
    expect(mediaItems, hasLength(1));
    expect(
      (mediaItems.single! as Map<String, Object?>)['accessMode'],
      'signed_grant',
    );
    expect(wire['authorDisplayName'], 'Canonical author');
    expect(wire['mediaAssetId'], 'video-projection-codec');
    expect(wire['mediaAssetVersion'], 2);
    expect(
      wire['hlsCmafMasterManifestUrl'],
      'media/video/m/asset/video-projection-codec/v2/hls/master.m3u8',
    );
    expect(wire['createdAt'], createdAt.toUtc().toIso8601String());
    expect(wire['updatedAt'], updatedAt.toUtc().toIso8601String());
    expect(wire, isNot(contains('contentVertical')));
    expect(wire, isNot(contains('id')));
    expect(wire, isNot(contains('type')));
    expect(wire, isNot(contains('displayName')));
  });
}
