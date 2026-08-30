import 'package:flutter/foundation.dart';

/// 私有视频的短签播放交付（DEC-033）。
///
/// 私有资产没有公开交付引用：[MediaDeliveryReference] 只服务公开 canonical
/// path，签名 query 进不去它的校验。因此私有路单独用本类型承载已由
/// SignedMediaDeliveryCoordinator 兑换并校验过的短签地址与稳定缓存身份。
///
/// 渐进式 MP4 的 Range 分段由原生播放器自行发起，交付边缘按段复算签名，
/// 因此播放器只需要一个单签 URL，不需要逐段换签。
@immutable
class SignedVideoDelivery {
  const SignedVideoDelivery({
    required this.deliveryUri,
    required this.cacheIdentity,
    required this.assetId,
    this.onReSignRequested,
  });

  /// 已校验的短签交付地址（https + sign + t）。
  final Uri deliveryUri;

  /// 稳定缓存身份：签名 query 随 TTL 轮换，不参与缓存键。
  final String cacheIdentity;

  final String assetId;

  /// 播放失败后请求强制换签。TTL 到期或签名被边缘拒绝时由播放器回调，
  /// 换签编排仍在协调器一侧，播放器不自行兑换。
  final VoidCallback? onReSignRequested;

  @override
  bool operator ==(Object other) =>
      other is SignedVideoDelivery &&
      other.deliveryUri == deliveryUri &&
      other.cacheIdentity == cacheIdentity &&
      other.assetId == assetId;

  @override
  int get hashCode => Object.hash(deliveryUri, cacheIdentity, assetId);
}
