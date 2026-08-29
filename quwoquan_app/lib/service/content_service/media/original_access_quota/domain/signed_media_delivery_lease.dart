import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;

/// 私有媒体（accessMode=signed_grant）的短签交付租约。
///
/// 由 SignedMediaDeliveryCoordinator 校验 grant 响应后产出；页面与图片/视频
/// 原子只消费本类型，不直接接触 grant wire 对象或裸签名 URL 字符串。
/// 签名 URL 只存在于本租约的短期生命周期内，不写回业务 DTO 或持久缓存文档。
@immutable
final class SignedMediaDeliveryLease {
  const SignedMediaDeliveryLease({
    required this.assetId,
    required this.kind,
    required this.deliveryUri,
    required this.expiresAt,
  });

  /// release authority 下发的媒体资产标识（业务身份，非 CAS 字节身份）。
  final String assetId;

  /// 媒体交付种类，复用公开交付层的同一枚举，避免第二套种类真相源。
  final MediaDeliveryKind kind;

  /// 已通过校验的短签交付 URL（https，query 含 sign 与 t）。
  final Uri deliveryUri;

  /// 签发方声明的绝对到期时间；复用窗口由协调器按安全余量收窄。
  final DateTime expiresAt;

  /// 稳定缓存身份：只绑定种类与资产标识，刻意不含签名 query——
  /// 签名随 TTL 轮换，若进入缓存键会造成解码缓存失效与磁盘重复下载。
  String get cacheIdentity => 'signed|${kind.name}|$assetId';

  @override
  bool operator ==(Object other) {
    return other is SignedMediaDeliveryLease &&
        other.assetId == assetId &&
        other.kind == kind &&
        other.deliveryUri == deliveryUri &&
        other.expiresAt == expiresAt;
  }

  @override
  int get hashCode => Object.hash(assetId, kind, deliveryUri, expiresAt);
}
