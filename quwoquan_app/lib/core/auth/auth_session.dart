import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

enum AuthSessionStatus { restoring, guest, authenticated }

enum AuthPromptReason {
  firstRun,
  manualLoggedOut,
  sessionExpired,
  actionRequired,
}

class AuthSessionState {
  const AuthSessionState({
    required this.status,
    this.promptReason,
    this.accessToken = '',
    this.refreshToken = '',
    this.ownerId = '',
    this.activeSubAccountId = '',
    this.accountState = '',
    this.identityOrigin = '',
    this.installId = '',
    this.errorMessage,
  });

  const AuthSessionState.restoring()
    : this(status: AuthSessionStatus.restoring);

  final AuthSessionStatus status;
  final AuthPromptReason? promptReason;
  final String accessToken;
  final String refreshToken;
  final String ownerId;
  final String activeSubAccountId;
  final String accountState;
  final String identityOrigin;
  final String installId;
  final String? errorMessage;

  bool get isAuthenticated =>
      status == AuthSessionStatus.authenticated &&
      accessToken.isNotEmpty &&
      ownerId.isNotEmpty;

  bool get isGuest => status == AuthSessionStatus.guest;

  AuthSessionState copyWith({
    AuthSessionStatus? status,
    AuthPromptReason? Function()? promptReason,
    String? accessToken,
    String? refreshToken,
    String? ownerId,
    String? activeSubAccountId,
    String? accountState,
    String? identityOrigin,
    String? installId,
    String? Function()? errorMessage,
  }) {
    return AuthSessionState(
      status: status ?? this.status,
      promptReason: promptReason != null ? promptReason() : this.promptReason,
      accessToken: accessToken ?? this.accessToken,
      refreshToken: refreshToken ?? this.refreshToken,
      ownerId: ownerId ?? this.ownerId,
      activeSubAccountId: activeSubAccountId ?? this.activeSubAccountId,
      accountState: accountState ?? this.accountState,
      identityOrigin: identityOrigin ?? this.identityOrigin,
      installId: installId ?? this.installId,
      errorMessage: errorMessage != null ? errorMessage() : this.errorMessage,
    );
  }
}

class StoredAuthSession {
  const StoredAuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.ownerId,
    required this.activeSubAccountId,
    required this.accountState,
    required this.identityOrigin,
    required this.installId,
    required this.manualLoggedOut,
    required this.launchPromptDismissed,
  });

  final String accessToken;
  final String refreshToken;
  final String ownerId;
  final String activeSubAccountId;
  final String accountState;
  final String identityOrigin;
  final String installId;
  final bool manualLoggedOut;
  final bool launchPromptDismissed;
}

class AuthSessionStore {
  AuthSessionStore({
    FlutterSecureStorage? secureStorage,
    Future<SharedPreferences> Function()? prefsFactory,
  }) : _secureStorage = secureStorage ?? const FlutterSecureStorage(),
       _prefsFactory = prefsFactory ?? SharedPreferences.getInstance;

  static const _accessTokenKey = 'auth.access_token';
  static const _refreshTokenKey = 'auth.refresh_token';
  static const _ownerIdKey = 'auth.owner_id';
  static const _activeSubAccountIdKey = 'auth.active_sub_account_id';
  static const _accountStateKey = 'auth.account_state';
  static const _identityOriginKey = 'auth.identity_origin';
  static const _installIdKey = 'auth.install_id';
  static const _manualLoggedOutKey = 'auth.manual_logged_out';
  static const _launchPromptDismissedKey = 'auth.launch_prompt_dismissed';

  final FlutterSecureStorage _secureStorage;
  final Future<SharedPreferences> Function() _prefsFactory;

  Future<StoredAuthSession> read() async {
    final prefs = await _prefsFactory();
    final installId = await _ensureInstallId(prefs);
    return StoredAuthSession(
      accessToken: await _secureStorage.read(key: _accessTokenKey) ?? '',
      refreshToken: await _secureStorage.read(key: _refreshTokenKey) ?? '',
      ownerId: prefs.getString(_ownerIdKey) ?? '',
      activeSubAccountId: prefs.getString(_activeSubAccountIdKey) ?? '',
      accountState: prefs.getString(_accountStateKey) ?? '',
      identityOrigin: prefs.getString(_identityOriginKey) ?? '',
      installId: installId,
      manualLoggedOut: prefs.getBool(_manualLoggedOutKey) ?? false,
      launchPromptDismissed: prefs.getBool(_launchPromptDismissedKey) ?? false,
    );
  }

  Future<void> saveLoginResult(AuthLoginResultDto result) async {
    final prefs = await _prefsFactory();
    final activeSub = _activeSubAccountIdFromResult(result);
    await _secureStorage.write(key: _accessTokenKey, value: result.accessToken);
    await _secureStorage.write(
      key: _refreshTokenKey,
      value: result.refreshToken,
    );
    await prefs.setString(_ownerIdKey, result.ownerId);
    await prefs.setString(_activeSubAccountIdKey, activeSub);
    await prefs.setString(_accountStateKey, result.accountState);
    await prefs.setString(_identityOriginKey, result.identityOrigin);
    await prefs.setBool(_manualLoggedOutKey, false);
    await prefs.setBool(_launchPromptDismissedKey, false);
    await _ensureInstallId(prefs);
  }

  Future<void> updateActiveSubAccount(String subAccountId) async {
    final prefs = await _prefsFactory();
    await prefs.setString(_activeSubAccountIdKey, subAccountId.trim());
  }

  Future<void> clearSession({required bool manualLogout}) async {
    final prefs = await _prefsFactory();
    await _secureStorage.delete(key: _accessTokenKey);
    await _secureStorage.delete(key: _refreshTokenKey);
    await prefs.remove(_ownerIdKey);
    await prefs.remove(_activeSubAccountIdKey);
    await prefs.remove(_accountStateKey);
    await prefs.remove(_identityOriginKey);
    await prefs.setBool(_manualLoggedOutKey, manualLogout);
    await prefs.setBool(_launchPromptDismissedKey, false);
    await _ensureInstallId(prefs);
  }

  Future<void> markLaunchPromptDismissed() async {
    final prefs = await _prefsFactory();
    await prefs.setBool(_launchPromptDismissedKey, true);
    await _ensureInstallId(prefs);
  }

  Future<String> _ensureInstallId(SharedPreferences prefs) async {
    final existing = prefs.getString(_installIdKey);
    if (existing != null && existing.trim().isNotEmpty) {
      return existing;
    }
    final generated = const Uuid().v4();
    await prefs.setString(_installIdKey, generated);
    return generated;
  }

  static String _activeSubAccountIdFromResult(AuthLoginResultDto result) {
    final activeSub = result.activeSub ?? const <String, dynamic>{};
    return activeSub['subAccountId']?.toString().trim() ?? '';
  }
}

class AuthSessionController extends Notifier<AuthSessionState> {
  bool _restoreStarted = false;

  AuthSessionStore get _store => ref.read(authSessionStoreProvider);

  @override
  AuthSessionState build() {
    if (!_restoreStarted) {
      _restoreStarted = true;
      unawaited(restore());
    }
    return const AuthSessionState.restoring();
  }

  Future<void> restore() async {
    try {
      final stored = await _store.read();
      if (stored.accessToken.isNotEmpty &&
          stored.refreshToken.isNotEmpty &&
          stored.ownerId.isNotEmpty) {
        state = AuthSessionState(
          status: AuthSessionStatus.authenticated,
          accessToken: stored.accessToken,
          refreshToken: stored.refreshToken,
          ownerId: stored.ownerId,
          activeSubAccountId: stored.activeSubAccountId,
          accountState: stored.accountState,
          identityOrigin: stored.identityOrigin,
          installId: stored.installId,
        );
        return;
      }
      state = AuthSessionState(
        status: AuthSessionStatus.guest,
        promptReason: stored.launchPromptDismissed
            ? null
            : stored.manualLoggedOut
            ? AuthPromptReason.manualLoggedOut
            : AuthPromptReason.firstRun,
        installId: stored.installId,
      );
    } catch (e) {
      state = AuthSessionState(
        status: AuthSessionStatus.guest,
        promptReason: AuthPromptReason.sessionExpired,
        errorMessage: e.toString(),
      );
    }
  }

  Future<void> applyLoginResult(AuthLoginResultDto result) async {
    await _store.saveLoginResult(result);
    final stored = await _store.read();
    state = AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activeSubAccountId: stored.activeSubAccountId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
    );
  }

  Future<void> continueAsGuest({AuthPromptReason? reason}) async {
    await _store.markLaunchPromptDismissed();
    final stored = await _store.read();
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: reason,
      installId: stored.installId,
    );
  }

  Future<void> clearForLogout() async {
    await _store.clearSession(manualLogout: true);
    final stored = await _store.read();
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: AuthPromptReason.manualLoggedOut,
      installId: stored.installId,
    );
  }

  Future<void> clearForExpiredSession() async {
    await _store.clearSession(manualLogout: false);
    final stored = await _store.read();
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: AuthPromptReason.sessionExpired,
      installId: stored.installId,
    );
  }

  Future<void> updateActiveSubAccount(String subAccountId) async {
    await _store.updateActiveSubAccount(subAccountId);
    state = state.copyWith(activeSubAccountId: subAccountId.trim());
  }
}

class ProviderBackedCloudAuthTokenProvider implements CloudAuthTokenProvider {
  const ProviderBackedCloudAuthTokenProvider(this._readAccessToken);

  final String Function() _readAccessToken;

  @override
  Future<String?> getAccessToken() async {
    final token = _readAccessToken().trim();
    return token.isEmpty ? null : token;
  }
}

final authSessionStoreProvider = Provider<AuthSessionStore>((ref) {
  return AuthSessionStore();
});

final authSessionControllerProvider =
    NotifierProvider<AuthSessionController, AuthSessionState>(
      AuthSessionController.new,
    );
