import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 离线输入/能力的具名终态；不编码成网络失败、空数据或待同步成功。
final class OfflineContentFailure extends RuntimeFailure implements Exception {
  const OfflineContentFailure(this.reason, {bool unavailable = false})
    : super(
        code: RuntimeFailureCodes.clientPlatformCapabilityUnavailable,
        semanticReason: reason,
        origin: RuntimeFailureOrigin.localClient,
        kind: unavailable ? RuntimeFailureKind.unsupported : RuntimeFailureKind.contract,
        nature: RuntimeFailureNature.permanent,
        location: const RuntimeFailureLocation.unknown(),
        context: const RuntimeFailureContext(),
      );

  final String reason;

  @override
  String toString() => 'OfflineContentFailure($reason)';
}
