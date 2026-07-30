import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:quwoquan_app/application/content/onboarding/interest_onboarding.dart';

/// 安装级加密草稿；只存路径制偏好，不存账号凭据。
final class SecureInterestOnboardingDraftStore
    implements InterestOnboardingDraftStore {
  const SecureInterestOnboardingDraftStore({
    this.storage = const FlutterSecureStorage(),
  });

  static const String _storageKey = 'qwq.interest_onboarding';
  final FlutterSecureStorage storage;

  @override
  Future<InterestOnboardingDraft?> read() async {
    final raw = await storage.read(key: _storageKey);
    if (raw == null || raw.trim().isEmpty) return null;
    try {
      return InterestOnboardingDraft.tryParse(jsonDecode(raw));
    } on FormatException {
      return null;
    }
  }

  @override
  Future<void> write(InterestOnboardingDraft draft) =>
      storage.write(key: _storageKey, value: jsonEncode(draft.toJson()));

  Future<void> clearForTerminalAccountClosure() async {
    await storage.delete(key: _storageKey);
    if (await storage.read(key: _storageKey) != null) {
      throw StateError('interest onboarding draft cleanup verification failed');
    }
  }
}
