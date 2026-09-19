import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 生产侧接缝：Alpha 注入本地演练身份，在线 composition 保持 null。
abstract interface class RehearsalAuthPort {
  bool isRehearsalCredential(String token);

  String? get lastIssuedOtp;

  Future<AuthSessionState?> restore({required String installId});

  Future<AuthSessionState> applyGrant(
    AuthSessionGrant grant, {
    required String installId,
  });

  Future<void> clear();
}

RehearsalAuthPort? installedRehearsalAuth;

void installRehearsalAuth(RehearsalAuthPort port) {
  installedRehearsalAuth = port;
}

void clearRehearsalAuth() {
  installedRehearsalAuth = null;
}

bool get rehearsalAuthInstalled => installedRehearsalAuth != null;

const String rehearsalCredentialPrefix = 'rehearsal.';

bool isRehearsalCredential(String token) {
  return token.startsWith(rehearsalCredentialPrefix);
}
