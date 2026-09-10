import 'package:flutter/painting.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';

/// 已选定 authority 的公开媒体读取能力；调用方不选择环境或回退来源。
abstract interface class PublicMediaDeliveryPort {
  MediaEndpointConfig? get endpoints;
  MediaDeliveryReference? tryResolve(
    String? reference, {
    required MediaDeliveryKind kind,
    String assetId = '',
    int version = 0,
    String? sha256,
  });
  List<String> candidates(
    String reference,
    MediaDeliveryKind kind, {
    int version = 0,
  });
  ImageProvider<Object>? verifiedImageProvider(String reference);
  Future<String?> verifiedVideoPath(
    String reference, {
    MediaDeliveryReference? binding,
  });
}
