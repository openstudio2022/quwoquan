import 'dart:collection';
import 'dart:math' as math;

import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/domain/signed_media_delivery_lease.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 私有媒体租约兑换的 typed 失败原因。
enum SignedMediaDeliveryFailure {
  /// 请求携带空资产标识；私有媒体不允许从路径或 URL 反推身份。
  emptyAssetId,

  /// 请求的资产 accessMode 不是 signed_grant；公开资产不经本层。
  publicAccessMode,

  /// grant 响应的 mediaId 与请求资产标识漂移。
  grantIdentityMismatch,

  /// grant 响应的交付 URL 不是 https。
  insecureDeliveryUri,

  /// grant 响应的交付 URL 缺少 sign 或 t 签名 query。
  incompleteSignatureQuery,

  /// grant 响应到达时已过绝对到期时间。
  expiredGrant,
}

/// 私有媒体租约兑换失败的 typed 异常。
///
/// 失败一律以本异常抛出，不降级为 null——「失败」与「缺席」是两个状态，
/// 语义约束见 system-architecture-and-engineering-guide DEC-025。
final class SignedMediaDeliveryException implements Exception {
  const SignedMediaDeliveryException(this.failure, this.message);

  final SignedMediaDeliveryFailure failure;
  final String message;

  @override
  String toString() =>
      'SignedMediaDeliveryException(${failure.name}: $message)';
}

/// App 私有媒体消费的唯一异步 grant 协调器（DEC-033）。
///
/// 职责：按资产标识经 [OriginalAccessQuotaGateway] 兑换 original-access
/// grant，校验响应后输出 [SignedMediaDeliveryLease]。grant 调用、校验、
/// 缓存、单飞与刷新只存在于本类一处；页面与设计系统组件不得各自实现。
/// 公开媒体继续走纯同步 MediaDeliveryResolver，两条边界互不放宽。
final class SignedMediaDeliveryCoordinator {
  SignedMediaDeliveryCoordinator({
    required this._gateway,
    this._now = DateTime.now,
    this._maxCachedLeases = defaultMaxCachedLeases,
  }) : assert(_maxCachedLeases > 0, '租约缓存上限必须为正数');

  /// 租约缓存数量上限：单屏私有媒体（feed 卡片、沉浸页、头像）远小于该值，
  /// 上限只为阻止长会话下的无界增长，超出后按 LRU 逐出。
  static const int defaultMaxCachedLeases = 256;

  /// 到期安全余量上限（30 秒）：租约被复用后到字节 GET 完成之间存在网络
  /// 窗口，30 秒足以覆盖慢网下的请求发出与传输；余量更大只会提前换签、
  /// 压低 DEC-033 约定的 grant cache 命中率（稳态目标 ≥ 80%）。
  static const Duration maxRenewalSafetyMargin = Duration(seconds: 30);

  /// 安全余量的 TTL 比例上限（20%）：短 TTL 时固定 30 秒会吃掉过大比例的
  /// 可用期（如 ttl=60s 只剩一半），按 ttl 的 20% 收敛保证复用窗口始终
  /// 不低于 TTL 的 80%。最终余量取 min(30 秒, ttl × 20%)。
  static const double renewalSafetyMarginTtlFraction = 0.2;

  final OriginalAccessQuotaGateway _gateway;
  final DateTime Function() _now;
  final int _maxCachedLeases;

  /// LinkedHashMap 的插入序即 LRU 访问序：命中时重插，逐出时删首键。
  final LinkedHashMap<String, _CachedLease> _leases =
      LinkedHashMap<String, _CachedLease>();
  final Map<String, Future<_CachedLease>> _inFlight =
      <String, Future<_CachedLease>>{};

  /// 兑换（或复用）一张私有媒体交付租约。
  ///
  /// - 仅服务 [MediaDeliveryAccessMode.signedGrant] 的资产；
  /// - 同一资产的并发请求共享同一个 in-flight Future（单飞）；
  /// - 未过安全窗的租约直接复用，过窗后重新兑换；
  /// - 任何校验失败抛 [SignedMediaDeliveryException]，不返回 null。
  Future<SignedMediaDeliveryLease> resolve({
    required String assetId,
    required MediaDeliveryKind kind,
    required MediaDeliveryAccessMode accessMode,
  }) async {
    final normalizedAssetId = assetId.trim();
    if (normalizedAssetId.isEmpty) {
      throw const SignedMediaDeliveryException(
        SignedMediaDeliveryFailure.emptyAssetId,
        '私有媒体请求缺少资产标识',
      );
    }
    if (accessMode != MediaDeliveryAccessMode.signedGrant) {
      throw SignedMediaDeliveryException(
        SignedMediaDeliveryFailure.publicAccessMode,
        '资产 $normalizedAssetId 的 accessMode 为 ${accessMode.wireName}，'
        '公开媒体不经 signed grant 协调器',
      );
    }

    final key = '${kind.name}|$normalizedAssetId';
    final cached = _leases[key];
    if (cached != null) {
      if (_now().isBefore(cached.reuseUntil)) {
        // LRU 触达：重插以刷新访问序。
        _leases.remove(key);
        _leases[key] = cached;
        return cached.lease;
      }
      _leases.remove(key);
    }

    final pending = _inFlight[key];
    if (pending != null) {
      final entry = await pending;
      return entry.lease;
    }

    return _exchange(key, normalizedAssetId, kind);
  }

  /// 丢弃该键的缓存租约后重新兑换（单次强制换签，DEC-033 失败恢复单义）。
  ///
  /// 供图片/视频原子在签名字节 GET 首次 401/403 或加载失败后发起：旧签名
  /// 已被交付边缘拒绝，复用缓存或等待旧在途只会重复失败，因此本方法同时
  /// 丢弃该键的缓存与在途落缓存资格。校验链路与 [resolve] 完全同源，
  /// 不提供绕过校验的通道；新租约照常落缓存并参与后续复用。
  Future<SignedMediaDeliveryLease> refresh({
    required String assetId,
    required MediaDeliveryKind kind,
  }) async {
    final normalizedAssetId = assetId.trim();
    if (normalizedAssetId.isEmpty) {
      throw const SignedMediaDeliveryException(
        SignedMediaDeliveryFailure.emptyAssetId,
        '私有媒体强制换签缺少资产标识',
      );
    }

    final key = '${kind.name}|$normalizedAssetId';
    _leases.remove(key);
    _inFlight.remove(key);
    return _exchange(key, normalizedAssetId, kind);
  }

  Future<SignedMediaDeliveryLease> _exchange(
    String key,
    String assetId,
    MediaDeliveryKind kind,
  ) async {
    final future = _redeem(assetId, kind);
    _inFlight[key] = future;
    try {
      final entry = await future;
      // clearAll 或后续换签可能已替换同键 in-flight，只有仍是本次兑换时才落缓存。
      if (identical(_inFlight[key], future)) {
        _store(key, entry);
      }
      return entry.lease;
    } finally {
      if (identical(_inFlight[key], future)) {
        _inFlight.remove(key);
      }
    }
  }

  /// 清空全部租约缓存与在途兑换的落缓存资格。
  ///
  /// DEC-033：登出、persona 切换与 active release 切换时必须清空 grant
  /// 缓存，防止授权身份变更后复用旧身份签发的 URL。
  void clearAll() {
    _leases.clear();
    _inFlight.clear();
  }

  Future<_CachedLease> _redeem(String assetId, MediaDeliveryKind kind) async {
    // purpose 固定 view：浏览消费一律走 view 配额；save 属「保存原图」动作，
    // 由动作方自行携带，不进本协调器。
    final grant = await _gateway.requestOriginalAccess(
      RequestContentMediaOriginalAccessCommand(
        mediaId: assetId,
        purpose: MediaOriginalAccessPurpose.view,
      ),
    );

    if (grant.mediaId != assetId) {
      throw SignedMediaDeliveryException(
        SignedMediaDeliveryFailure.grantIdentityMismatch,
        'grant mediaId ${grant.mediaId} 与请求资产 $assetId 漂移',
      );
    }
    final uri = grant.originalUrl;
    if (uri.scheme.toLowerCase() != 'https' || uri.host.isEmpty) {
      throw SignedMediaDeliveryException(
        SignedMediaDeliveryFailure.insecureDeliveryUri,
        '资产 $assetId 的交付 URL 不是 HTTPS absolute URI',
      );
    }
    final sign = uri.queryParameters['sign'];
    final expiryToken = uri.queryParameters['t'];
    if (sign == null ||
        sign.isEmpty ||
        expiryToken == null ||
        expiryToken.isEmpty) {
      throw SignedMediaDeliveryException(
        SignedMediaDeliveryFailure.incompleteSignatureQuery,
        '资产 $assetId 的交付 URL 缺少 sign/t 签名 query',
      );
    }
    if (!grant.expiresAt.isAfter(_now())) {
      throw SignedMediaDeliveryException(
        SignedMediaDeliveryFailure.expiredGrant,
        '资产 $assetId 的 grant 到达时已过期（expiresAt=${grant.expiresAt}）',
      );
    }

    final lease = SignedMediaDeliveryLease(
      assetId: assetId,
      kind: kind,
      deliveryUri: uri,
      expiresAt: grant.expiresAt,
    );
    // 复用窗口按契约声明的 ttlSeconds 计算余量，不用本地时钟反推剩余时间。
    final margin = _renewalSafetyMargin(Duration(seconds: grant.ttlSeconds));
    return _CachedLease(
      lease: lease,
      reuseUntil: grant.expiresAt.subtract(margin),
    );
  }

  void _store(String key, _CachedLease entry) {
    _leases.remove(key);
    _leases[key] = entry;
    while (_leases.length > _maxCachedLeases) {
      _leases.remove(_leases.keys.first);
    }
  }

  static Duration _renewalSafetyMargin(Duration ttl) {
    final fractionMs = (ttl.inMilliseconds * renewalSafetyMarginTtlFraction)
        .floor();
    return Duration(
      milliseconds: math.min(
        maxRenewalSafetyMargin.inMilliseconds,
        math.max(fractionMs, 0),
      ),
    );
  }
}

final class _CachedLease {
  const _CachedLease({required this.lease, required this.reuseUntil});

  final SignedMediaDeliveryLease lease;

  /// 复用截止时间 = expiresAt − 安全余量；此后即使未到 expiresAt 也重新兑换。
  final DateTime reuseUntil;
}
