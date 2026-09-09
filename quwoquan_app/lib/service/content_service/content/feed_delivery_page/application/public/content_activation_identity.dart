import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentFeedEmptyReason, isCanonicalSha256Digest;

/// App 内容缓存的完整隔离身份。
///
/// key 同时绑定环境、账号、Persona、sourceOwner 与 Content authority tuple，
/// 避免内容跨 principal、跨 release 或跨环境回放，不读取 JWT audience。
final class ContentCacheIsolationIdentity {
  ContentCacheIsolationIdentity({
    required this.environment,
    required this.accountId,
    required this.personaId,
    required this.sourceOwner,
    required this.activationIdentity,
  }) {
    for (final entry in <String, String>{
      'environment': environment,
      'accountId': accountId,
      'personaId': personaId,
      'sourceOwner': sourceOwner,
    }.entries) {
      if (entry.value.trim().isEmpty || entry.value != entry.value.trim()) {
        throw FormatException(
          'content cache ${entry.key} must be a non-empty canonical value',
        );
      }
    }
  }

  final String environment;
  final String accountId;
  final String personaId;
  final String sourceOwner;
  final ContentActivationIdentity activationIdentity;

  String get cacheKeyPrefix => <String>[
    'environment=${Uri.encodeQueryComponent(environment)}',
    'account=${Uri.encodeQueryComponent(accountId)}',
    'persona=${Uri.encodeQueryComponent(personaId)}',
    'sourceOwner=${Uri.encodeQueryComponent(sourceOwner)}',
    'releaseId=${Uri.encodeQueryComponent(activationIdentity.releaseId)}',
    'manifestDigest=${Uri.encodeQueryComponent(activationIdentity.manifestDigest)}',
  ].join('&');

  String isolateQueryKey(String queryKey) {
    final normalized = queryKey.trim();
    if (normalized.isEmpty) {
      throw const FormatException(
        'content cache query key must be a non-empty canonical value',
      );
    }
    return '$cacheKeyPrefix&$normalized';
  }

  @override
  bool operator ==(Object other) =>
      other is ContentCacheIsolationIdentity &&
      other.environment == environment &&
      other.accountId == accountId &&
      other.personaId == personaId &&
      other.sourceOwner == sourceOwner &&
      other.activationIdentity == activationIdentity;

  @override
  int get hashCode => Object.hash(
    environment,
    accountId,
    personaId,
    sourceOwner,
    activationIdentity,
  );
}

/// 运行时内容激活身份（runtime-client-foundation DEC-004）。
///
/// 该 value object 由 Content API 响应在运行时下发，App 不拥有写入：
/// - 在场：release-bound 页面（有内容、no_eligible_content、continuation）
///   必须携带完整二元组；
/// - 缺席：`no_active_release` 与不绑定 release 的社交流用 `null` 表达；
/// - 失败：wire 上只带一半身份或 digest 非 canonical 属协议失败，
///   由 [resolveContentActivationIdentity] 抛出，不得塌陷为缺席。
final class ContentActivationIdentity {
  ContentActivationIdentity({
    required this.releaseId,
    required this.manifestDigest,
  }) {
    if (releaseId.trim().isEmpty || releaseId != releaseId.trim()) {
      throw const FormatException(
        'content activation releaseId must be a non-empty canonical value',
      );
    }
    if (!isCanonicalSha256Digest(manifestDigest)) {
      throw const FormatException(
        'content activation manifestDigest must be a canonical sha256 digest',
      );
    }
  }

  final String releaseId;
  final String manifestDigest;

  @override
  bool operator ==(Object other) =>
      other is ContentActivationIdentity &&
      other.releaseId == releaseId &&
      other.manifestDigest == manifestDigest;

  @override
  int get hashCode => Object.hash(releaseId, manifestDigest);

  @override
  String toString() => 'ContentActivationIdentity($releaseId, $manifestDigest)';
}

/// 把 wire 上的可空二元组解析为四态之一。
///
/// 返回 `null` 表示合法缺席；malformed（半身份、非 canonical digest、
/// `no_active_release` 却携带身份）一律抛 [FormatException]，调用方按
/// Remote 协议失败处理，不得编码为空态。
ContentActivationIdentity? resolveContentActivationIdentity({
  required String? releaseId,
  required String? manifestDigest,
  required ContentFeedEmptyReason? emptyReason,
}) {
  final normalizedReleaseId = releaseId?.trim() ?? '';
  final normalizedDigest = manifestDigest?.trim() ?? '';
  final hasAny = normalizedReleaseId.isNotEmpty || normalizedDigest.isNotEmpty;
  if (emptyReason == ContentFeedEmptyReason.noActiveRelease) {
    if (hasAny) {
      throw const FormatException(
        'no_active_release must not carry a content activation identity',
      );
    }
    return null;
  }
  if (!hasAny) {
    return null;
  }
  if (normalizedReleaseId.isEmpty || normalizedDigest.isEmpty) {
    throw const FormatException(
      'content activation identity must be complete or absent',
    );
  }
  return ContentActivationIdentity(
    releaseId: normalizedReleaseId,
    manifestDigest: normalizedDigest,
  );
}
