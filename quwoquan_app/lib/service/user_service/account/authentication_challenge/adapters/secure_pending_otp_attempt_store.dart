import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/pending_otp_attempt_store.dart';

/// 安装级加密 OTP 恢复存储；验证码字段不在 schema 中，无法被此适配器落盘。
final class SecurePendingOtpAttemptStore implements PendingOtpAttemptStore {
  const SecurePendingOtpAttemptStore({
    this.storage = const FlutterSecureStorage(),
  });

  static const String _storageKey = 'auth.pending_otp_attempt.v1';
  final FlutterSecureStorage storage;

  @override
  Future<PendingOtpAttempt?> read() async {
    final raw = await storage.read(key: _storageKey);
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
  Future<void> write(PendingOtpAttempt attempt) =>
      storage.write(key: _storageKey, value: jsonEncode(attempt.toJson()));

  @override
  Future<void> clear() => storage.delete(key: _storageKey);
}
