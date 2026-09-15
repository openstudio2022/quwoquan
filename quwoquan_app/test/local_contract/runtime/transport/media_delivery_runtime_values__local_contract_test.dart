import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_binding.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/runtime/transport/media/signed_video_delivery.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';

import '../../../support/runtime/media/signed_media_lease_test_support.dart';

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'typed media bindings keep access modes and value identity explicit',
    () {
      expect(
        articleAssetAccessMode(' signed_grant '),
        MediaDeliveryAccessMode.signedGrant,
      );
      expect(articleAssetAccessMode('public'), MediaDeliveryAccessMode.public);
      expect(articleAssetAccessMode('legacy'), isNull);

      const private = MediaDeliveryBinding(
        assetId: 'asset-1',
        accessMode: MediaDeliveryAccessMode.signedGrant,
        publicUrl: 'https://cdn.test/private.m3u8',
      );
      const public = MediaDeliveryBinding.public(
        publicUrl: 'https://cdn.test/a.jpg',
      );
      const previous = MediaDeliveryBinding.previousPublic(
        publicUrl: 'https://cdn.test/legacy.jpg',
      );
      const absent = MediaDeliveryBinding.absent();

      expect(private.isSignedGrant, isTrue);
      expect(private.isUnsupportedPrivateHls, isTrue);
      expect(private.hasRenderableSource, isTrue);
      expect(public.isPublic, isTrue);
      expect(previous.isPublic, isTrue);
      expect(absent.hasRenderableSource, isFalse);
      expect(
        const MediaDeliveryBinding(
          assetId: 'asset-1',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: '',
        ),
        const MediaDeliveryBinding(
          assetId: 'asset-1',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: '',
        ),
      );
      expect(private.hashCode, isNot(0));
    },
  );

  test('signed video delivery equality ignores callback identity', () {
    final uri = Uri.parse('https://cdn.test/video.mp4?sign=a&t=1');
    final first = SignedVideoDelivery(
      lease: testSignedMediaLease(deliveryUri: uri, assetId: 'asset-1'),
      onReSignRequested: () {},
    );
    final second = SignedVideoDelivery(
      lease: testSignedMediaLease(deliveryUri: uri, assetId: 'asset-1'),
    );

    expect(first, second);
    expect(first.hashCode, second.hashCode);
    expect(first, isNot(const Object()));
  });
  test('signed media lease has value equality and typed failure text', () {
    final expiresAt = DateTime.utc(2030, 1, 1);
    final uri = Uri.parse('https://cdn.test/image.jpg?sign=a&t=1');
    final first = testSignedMediaLease(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      deliveryUri: uri,
      expiresAt: expiresAt,
    );
    final second = testSignedMediaLease(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      deliveryUri: uri,
      expiresAt: expiresAt,
    );
    const failure = SignedMediaDeliveryException(
      SignedMediaDeliveryFailure.expiredGrant,
      'expired',
    );

    expect(first, second);
    expect(first.hashCode, second.hashCode);
    expect(first, isNot(const Object()));
    expect(failure.toString(), contains('expiredGrant: expired'));
  });
}
