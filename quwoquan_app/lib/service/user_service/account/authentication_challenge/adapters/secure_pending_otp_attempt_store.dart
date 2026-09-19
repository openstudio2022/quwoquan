import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_observer.dart';
import 'package:quwoquan_app/runtime/config/generated/app_launch_contract.g.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/pending_otp_attempt_store.dart';

/// OTP 恢复存储；普通安装原键不变，isolated 必须先绑定再执行任何 I/O。
final class SecurePendingOtpAttemptStore implements PendingOtpAttemptStore {
  const SecurePendingOtpAttemptStore({
    this.storage = const FlutterSecureStorage(),
  }) : namespace = null,
       currentSpace = null,
       isActive = null,
       _observer = null;

  SecurePendingOtpAttemptStore.isolated({
    required RehearsalStorageNamespace namespace,
    required VerifiedRehearsalSpace? Function() currentSpace,
    bool Function()? isActive,
    FlutterSecureStorage storage = const FlutterSecureStorage(),
    RehearsalStorageObserver? observer,
  }) : this._isolated(namespace, currentSpace, isActive, storage, observer);

  SecurePendingOtpAttemptStore._isolated(
    this.namespace,
    this.currentSpace,
    this.isActive,
    this.storage,
    RehearsalStorageObserver? observer,
  ) : _observer = observer?.attach('pending', namespace!) {
    try {
      _requireCurrent();
    } catch (_) {
      _observer?.invalidate();
      rethrow;
    }
  }

  final FlutterSecureStorage storage;
  final RehearsalStorageNamespace? namespace;
  final VerifiedRehearsalSpace? Function()? currentSpace;
  final bool Function()? isActive;
  final RehearsalConsumerObserver? _observer;

  void dispose() => _observer?.invalidate();

  void _requireCurrent() {
    try {
      if (isActive?.call() == false) {
        throw contentCapabilityUnavailable('pending_otp_storage_disposed');
      }
      if (namespace case final namespace?) {
        namespace.requireCurrent(currentSpace!());
      }
      _observer?.requireCurrent();
    } catch (_) {
      _observer?.invalidate();
      rethrow;
    }
  }

  void _record(RehearsalSuccessfulOperation operation) {
    _requireCurrent();
    _observer?.recordSuccess(operation, fence: _requireCurrent);
  }

  String get _storageKey {
    _requireCurrent();
    return namespace?.pendingOtpKey ?? 'auth.pending_otp_attempt.v1';
  }

  @override
  Future<PendingOtpAttempt?> read() async {
    final raw = await storage.read(key: _storageKey);
    _requireCurrent();
    // null仅是缺失，不自证读取过payload；不为观察增加exists/read。
    if (raw != null) _record(RehearsalSuccessfulOperation.read);
    if (raw == null || raw.trim().isEmpty) return null;
    try {
      final attempt = PendingOtpAttempt.tryParse(jsonDecode(raw));
      if (attempt == null || attempt.isExpired(DateTime.now())) {
        await clear();
        return null;
      }
      return attempt;
    } on FormatException {
      await clear();
      return null;
    }
  }

  @override
  Future<void> write(PendingOtpAttempt attempt) async {
    await storage.write(key: _storageKey, value: jsonEncode(attempt.toJson()));
    _record(RehearsalSuccessfulOperation.write);
  }

  @override
  Future<void> clear() async {
    await storage.delete(key: _storageKey);
    _record(RehearsalSuccessfulOperation.delete);
  }
}
