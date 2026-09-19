import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';

/// 已验签 isolated 空间的纯存储投影。无 I/O、无授权签发、无 Alpha 实现依赖。
/// 存储 owner 必须在每次 read/write/delete 前调用 requireCurrent。
final class RehearsalStorageNamespace {
  RehearsalStorageNamespace(VerifiedRehearsalSpace space) : _space = space {
    if (!space.isIsolated || space.instanceId == 'default') {
      throw contentCapabilityUnavailable('rehearsal_isolated_namespace');
    }
    // 保持迁移前算法的输入顺序、Dart enum name 与 JSON 编码字节不变。
    final partition = sha256
        .convert(
          utf8.encode(
            jsonEncode([
              AppContentSource.bundledSnapshot.name,
              space.snapshotDigest,
              space.instanceId,
            ]),
          ),
        )
        .toString();
    authNamespace = 'alpha.rehearsal.$partition';
    pendingOtpKey = '$authNamespace.pending_otp_attempt';
    installIdKey = '$authNamespace.install_id';
  }

  final VerifiedRehearsalSpace _space;
  late final String authNamespace;
  late final String installIdKey;
  late final String pendingOtpKey;

  /// 同值新验签对象也代表新 scope；旧 owner 不得继续执行 I/O。
  void requireCurrent(VerifiedRehearsalSpace? currentSpace) {
    if (!identical(currentSpace, _space)) {
      throw contentCapabilityUnavailable('rehearsal_space_binding');
    }
  }
}
