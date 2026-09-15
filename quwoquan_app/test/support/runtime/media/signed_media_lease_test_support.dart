import 'package:quwoquan_app/service/content_service/media/original_access_quota/domain/signed_media_delivery_lease.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 真实工厂消费 typed grant，不开放未校验 lease 构造。
SignedMediaDeliveryLease testSignedMediaLease({
  required Uri deliveryUri,
  required String assetId,
  MediaDeliveryKind kind = MediaDeliveryKind.video,
  DateTime? expiresAt,
}) {
  final expiry = expiresAt ?? DateTime.utc(2035);
  return SignedMediaDeliveryLease.fromGrant(
    grant: MediaOriginalAccessGrant(
      mediaId: assetId,
      status: 'granted',
      originalUrl: deliveryUri,
      format: kind == MediaDeliveryKind.video ? 'video/mp4' : 'image/jpeg',
      sizeBytes: 1,
      expiresAt: expiry,
      ttlSeconds: 300,
      auditId: 'test-audit',
    ),
    assetId: assetId,
    kind: kind,
    now: DateTime.utc(2026),
  );
}
