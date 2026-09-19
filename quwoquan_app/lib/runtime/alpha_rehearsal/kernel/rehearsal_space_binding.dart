import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';

/// Alpha 内部纯值接缝，不是 launch wire、信任验证器或 UAT 授权。
/// 调用方必须先从 canonical source 验证选择；禁止把 runner 期望当选择值。
final class RehearsalSpaceBinding {
  RehearsalSpaceBinding._(
    this.snapshotDigest,
    this.instanceId,
    this.isIsolated, [
    this.storageNamespace,
  ]);

  factory RehearsalSpaceBinding.verified(VerifiedRehearsalSpace space) =>
      RehearsalSpaceBinding._(
        space.snapshotDigest,
        space.instanceId,
        space.isIsolated,
        space.isIsolated ? RehearsalStorageNamespace(space) : null,
      );

  factory RehearsalSpaceBinding.isolated({
    required AppContentSource source,
    required String snapshotDigest,
    required String? selectedInstanceId,
    required String expectedInstanceId,
  }) {
    if (source != AppContentSource.bundledSnapshot ||
        selectedInstanceId == null ||
        selectedInstanceId != expectedInstanceId ||
        selectedInstanceId == 'default' ||
        !_safeInstance.hasMatch(selectedInstanceId) ||
        !_digest.hasMatch(snapshotDigest)) {
      throw contentCapabilityUnavailable('rehearsal_space_binding');
    }
    return RehearsalSpaceBinding._(snapshotDigest, selectedInstanceId, true);
  }

  /// 只供 canonical source 已确认没有 isolated 请求的普通启动使用。
  factory RehearsalSpaceBinding.standard({
    required AppContentSource source,
    required String snapshotDigest,
  }) {
    if (source != AppContentSource.bundledSnapshot ||
        !_digest.hasMatch(snapshotDigest)) {
      throw contentCapabilityUnavailable('rehearsal_space_binding');
    }
    return RehearsalSpaceBinding._(snapshotDigest, 'default', false);
  }

  static final _safeInstance = RegExp(r'^[a-zA-Z0-9_-]{1,80}$');
  static final _digest = RegExp(r'^sha256:[a-f0-9]{64}$');
  final String snapshotDigest;
  final String instanceId;
  final bool isIsolated;

  /// 未验签的内部纯值构造不授予共享存储 namespace。
  final RehearsalStorageNamespace? storageNamespace;

  String get isolatedAuthNamespace => _verifiedNamespace.authNamespace;
  String get isolatedPendingOtpKey => _verifiedNamespace.pendingOtpKey;

  RehearsalStorageNamespace get _verifiedNamespace {
    final namespace = storageNamespace;
    if (namespace == null) {
      throw contentCapabilityUnavailable('rehearsal_isolated_namespace');
    }
    return namespace;
  }

  void verifyStorage({required String snapshot, required String instance}) {
    if (snapshot != snapshotDigest || instance != instanceId) {
      throw contentCapabilityUnavailable('rehearsal_space_binding');
    }
  }
}
