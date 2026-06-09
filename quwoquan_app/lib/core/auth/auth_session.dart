import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

/// 派生隐私安全的设备 actor 标识（installId hash 派生，非原始设备 ID）。
///
/// 用带版本前缀的 salt 对 installId 做 SHA-256，取前 32 位 hex，既稳定可复算、
/// 又不回传原始 installId/设备 ID。游客以此作为设备维度计数键；登录用户也携带。
String deriveDeviceActorId(String installId) {
  final trimmed = installId.trim();
  if (trimmed.isEmpty) {
    return '';
  }
  final digest = sha256.convert(utf8.encode('qwq-device-actor-v1:$trimmed'));
  return digest.toString().substring(0, 32);
}

void _syncDeviceActorId(String installId) {
  AppTraceContextStore.instance.deviceActorId = deriveDeviceActorId(installId);
}

enum AuthSessionStatus { restoring, guest, authenticated }

enum AuthPromptReason {
  firstRun,
  manualLoggedOut,
  sessionExpired,
  actionRequired,
}

enum AuthRememberedLoginMethod {
  unknown,
  oneTap,
  phoneOtp,
  wechat,
  apple,
  passkey,
  anonymous,
}

typedef AuthSessionRefreshExecutor =
    Future<AuthLoginResultDto> Function(String refreshToken);

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
    this.rememberedLoginMethod = AuthRememberedLoginMethod.unknown,
    this.rememberedLoginMaskedIdentifier = '',
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
  final AuthRememberedLoginMethod rememberedLoginMethod;
  final String rememberedLoginMaskedIdentifier;
  final String? errorMessage;

  bool get isAuthenticated =>
      status == AuthSessionStatus.authenticated &&
      accessToken.isNotEmpty &&
      ownerId.isNotEmpty;

  bool get isGuest => status == AuthSessionStatus.guest;

  bool get hasRememberedLogin =>
      rememberedLoginMethod != AuthRememberedLoginMethod.unknown;

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
    AuthRememberedLoginMethod? rememberedLoginMethod,
    String? rememberedLoginMaskedIdentifier,
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
      rememberedLoginMethod:
          rememberedLoginMethod ?? this.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier:
          rememberedLoginMaskedIdentifier ??
          this.rememberedLoginMaskedIdentifier,
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
    this.lastRefreshAtEpochMs = 0,
    this.lastForegroundAuthCheckAtEpochMs = 0,
    this.rememberedLoginMethod = AuthRememberedLoginMethod.unknown,
    this.rememberedLoginMaskedIdentifier = '',
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
  final int lastRefreshAtEpochMs;
  final int lastForegroundAuthCheckAtEpochMs;
  final AuthRememberedLoginMethod rememberedLoginMethod;
  final String rememberedLoginMaskedIdentifier;
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
  static const _lastRefreshAtKey = 'auth.last_refresh_at_epoch_ms';
  static const _lastForegroundAuthCheckAtKey =
      'auth.last_foreground_auth_check_at_epoch_ms';
  static const _rememberedLoginMethodKey = 'auth.remembered_login_method';
  static const _rememberedLoginMaskedIdentifierKey =
      'auth.remembered_login_masked_identifier';
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
      lastRefreshAtEpochMs: prefs.getInt(_lastRefreshAtKey) ?? 0,
      lastForegroundAuthCheckAtEpochMs:
          prefs.getInt(_lastForegroundAuthCheckAtKey) ?? 0,
      rememberedLoginMethod: _rememberedLoginMethodFromRaw(
        prefs.getString(_rememberedLoginMethodKey),
      ),
      rememberedLoginMaskedIdentifier:
          prefs.getString(_rememberedLoginMaskedIdentifierKey) ?? '',
      manualLoggedOut: prefs.getBool(_manualLoggedOutKey) ?? false,
      launchPromptDismissed: prefs.getBool(_launchPromptDismissedKey) ?? false,
    );
  }

  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
  }) async {
    final prefs = await _prefsFactory();
    final activeSub = _activeSubAccountIdFromResult(result);
    final nowEpochMs = DateTime.now().millisecondsSinceEpoch;
    final normalizedRememberedMethod =
        rememberedLoginMethod == AuthRememberedLoginMethod.unknown
        ? _rememberedLoginMethodFromIdentityOrigin(result.identityOrigin)
        : rememberedLoginMethod;
    final normalizedRememberedMaskedIdentifier =
        _normalizedRememberedMaskedIdentifier(
          method: normalizedRememberedMethod,
          maskedIdentifier: rememberedLoginMaskedIdentifier,
        );
    await _secureStorage.write(key: _accessTokenKey, value: result.accessToken);
    await _secureStorage.write(
      key: _refreshTokenKey,
      value: result.refreshToken,
    );
    await prefs.setString(_ownerIdKey, result.ownerId);
    await prefs.setString(_activeSubAccountIdKey, activeSub);
    await prefs.setString(_accountStateKey, result.accountState);
    await prefs.setString(_identityOriginKey, result.identityOrigin);
    await prefs.setInt(_lastRefreshAtKey, nowEpochMs);
    await prefs.setInt(_lastForegroundAuthCheckAtKey, nowEpochMs);
    await prefs.setString(
      _rememberedLoginMethodKey,
      normalizedRememberedMethod.name,
    );
    await prefs.setString(
      _rememberedLoginMaskedIdentifierKey,
      normalizedRememberedMaskedIdentifier,
    );
    await prefs.setBool(_manualLoggedOutKey, false);
    await prefs.setBool(_launchPromptDismissedKey, false);
    await _ensureInstallId(prefs);
  }

  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    final prefs = await _prefsFactory();
    final nowEpochMs = DateTime.now().millisecondsSinceEpoch;
    await _secureStorage.write(key: _accessTokenKey, value: accessToken);
    await _secureStorage.write(key: _refreshTokenKey, value: refreshToken);
    await prefs.setInt(_lastRefreshAtKey, nowEpochMs);
    await prefs.setInt(_lastForegroundAuthCheckAtKey, nowEpochMs);
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
    await prefs.remove(_lastRefreshAtKey);
    await prefs.remove(_lastForegroundAuthCheckAtKey);
    await prefs.setBool(_manualLoggedOutKey, manualLogout);
    await prefs.setBool(_launchPromptDismissedKey, false);
    await _ensureInstallId(prefs);
  }

  Future<void> markLaunchPromptDismissed() async {
    final prefs = await _prefsFactory();
    await prefs.setBool(_launchPromptDismissedKey, true);
    await _ensureInstallId(prefs);
  }

  Future<void> markForegroundAuthCheckNow() async {
    final prefs = await _prefsFactory();
    await prefs.setInt(
      _lastForegroundAuthCheckAtKey,
      DateTime.now().millisecondsSinceEpoch,
    );
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

  static AuthRememberedLoginMethod _rememberedLoginMethodFromRaw(String? raw) {
    final normalized = raw?.trim() ?? '';
    for (final method in AuthRememberedLoginMethod.values) {
      if (method.name == normalized) {
        return method;
      }
    }
    return AuthRememberedLoginMethod.unknown;
  }

  static AuthRememberedLoginMethod _rememberedLoginMethodFromIdentityOrigin(
    String identityOrigin,
  ) {
    return switch (identityOrigin.trim()) {
      'phone' => AuthRememberedLoginMethod.phoneOtp,
      'wechat' => AuthRememberedLoginMethod.wechat,
      'apple' => AuthRememberedLoginMethod.apple,
      'passkey' => AuthRememberedLoginMethod.passkey,
      'anonymous_device' => AuthRememberedLoginMethod.anonymous,
      _ => AuthRememberedLoginMethod.unknown,
    };
  }

  static String _normalizedRememberedMaskedIdentifier({
    required AuthRememberedLoginMethod method,
    String? maskedIdentifier,
  }) {
    final explicitMasked = maskedIdentifier?.trim() ?? '';
    if (explicitMasked.isNotEmpty) {
      return explicitMasked;
    }
    return '';
  }
}

class AuthSessionController extends Notifier<AuthSessionState> {
  static const Duration _staleRestoreRefreshThreshold = Duration(hours: 12);
  static const Duration _foregroundAuthCheckThreshold = Duration(hours: 24);

  bool _restoreStarted = false;
  Future<bool>? _refreshInFlight;

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
      _syncDeviceActorId(stored.installId);
      if (!ref.mounted) {
        return;
      }
      if (stored.accessToken.isNotEmpty &&
          stored.refreshToken.isNotEmpty &&
          stored.ownerId.isNotEmpty) {
        final authenticatedState = AuthSessionState(
          status: AuthSessionStatus.authenticated,
          accessToken: stored.accessToken,
          refreshToken: stored.refreshToken,
          ownerId: stored.ownerId,
          activeSubAccountId: stored.activeSubAccountId,
          accountState: stored.accountState,
          identityOrigin: stored.identityOrigin,
          installId: stored.installId,
          rememberedLoginMethod: stored.rememberedLoginMethod,
          rememberedLoginMaskedIdentifier:
              stored.rememberedLoginMaskedIdentifier,
        );
        state = authenticatedState;
        if (_shouldRefreshDuringRestore(stored)) {
          await refreshSessionIfNeeded(force: true);
        }
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
        rememberedLoginMethod: stored.rememberedLoginMethod,
        rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      );
    } catch (e) {
      if (!ref.mounted) {
        return;
      }
      state = AuthSessionState(
        status: AuthSessionStatus.guest,
        promptReason: AuthPromptReason.sessionExpired,
        rememberedLoginMethod: state.rememberedLoginMethod,
        rememberedLoginMaskedIdentifier: state.rememberedLoginMaskedIdentifier,
        errorMessage: e.toString(),
      );
    }
  }

  Future<void> applyLoginResult(AuthLoginResultDto result) async {
    await _store.saveLoginResult(result);
    final stored = await _store.read();
    _syncDeviceActorId(stored.installId);
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activeSubAccountId: stored.activeSubAccountId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
    );
  }

  Future<void> applyRememberedLoginResult(
    AuthLoginResultDto result, {
    required AuthRememberedLoginMethod rememberedLoginMethod,
    String? rememberedLoginMaskedIdentifier,
  }) async {
    await _store.saveLoginResult(
      result,
      rememberedLoginMethod: rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: rememberedLoginMaskedIdentifier,
    );
    final stored = await _store.read();
    _syncDeviceActorId(stored.installId);
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activeSubAccountId: stored.activeSubAccountId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
    );
  }

  Future<void> applyRefreshResult(AuthLoginResultDto result) async {
    final current = state;
    final accessToken = result.accessToken.trim();
    final refreshToken = result.refreshToken.trim();
    if (accessToken.isEmpty || refreshToken.isEmpty) {
      throw StateError('refresh result missing tokens');
    }
    await _store.saveRefreshedTokens(
      accessToken: accessToken,
      refreshToken: refreshToken,
    );
    final stored = await _store.read();
    _syncDeviceActorId(stored.installId);
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: accessToken,
      refreshToken: refreshToken,
      ownerId: current.ownerId.isNotEmpty ? current.ownerId : stored.ownerId,
      activeSubAccountId: current.activeSubAccountId.isNotEmpty
          ? current.activeSubAccountId
          : stored.activeSubAccountId,
      accountState: current.accountState.isNotEmpty
          ? current.accountState
          : stored.accountState,
      identityOrigin: current.identityOrigin.isNotEmpty
          ? current.identityOrigin
          : stored.identityOrigin,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
    );
  }

  Future<bool> refreshSessionIfNeeded({bool force = false}) async {
    final current = state;
    if (!current.isAuthenticated || current.refreshToken.trim().isEmpty) {
      return false;
    }
    if (!force && _refreshInFlight != null) {
      return _refreshInFlight!;
    }
    final future = _performRefresh();
    _refreshInFlight = future;
    try {
      return await future;
    } finally {
      if (identical(_refreshInFlight, future)) {
        _refreshInFlight = null;
      }
    }
  }

  Future<bool> refreshIfSessionLooksStale() async {
    final stored = await _store.read();
    if (!_shouldRefreshForForegroundCheck(stored)) {
      return false;
    }
    return refreshSessionIfNeeded(force: true);
  }

  Future<void> markForegroundAuthCheck() async {
    await _store.markForegroundAuthCheckNow();
  }

  Future<void> continueAsGuest({AuthPromptReason? reason}) async {
    await _store.markLaunchPromptDismissed();
    final stored = await _store.read();
    _syncDeviceActorId(stored.installId);
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: reason,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
    );
  }

  Future<void> clearForLogout() async {
    await _store.clearSession(manualLogout: true);
    final stored = await _store.read();
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: AuthPromptReason.manualLoggedOut,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
    );
  }

  Future<void> clearForExpiredSession() async {
    await _store.clearSession(manualLogout: false);
    final stored = await _store.read();
    if (!ref.mounted) {
      return;
    }
    state = AuthSessionState(
      status: AuthSessionStatus.guest,
      promptReason: AuthPromptReason.sessionExpired,
      installId: stored.installId,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
    );
  }

  Future<void> updateActiveSubAccount(String subAccountId) async {
    await _store.updateActiveSubAccount(subAccountId);
    state = state.copyWith(activeSubAccountId: subAccountId.trim());
  }

  Future<bool> _performRefresh() async {
    final current = state;
    final refreshToken = current.refreshToken.trim();
    if (!current.isAuthenticated || refreshToken.isEmpty) {
      return false;
    }
    try {
      final result = await ref.read(authSessionRefreshExecutorProvider)(
        refreshToken,
      );
      await applyRefreshResult(result);
      return true;
    } catch (e) {
      if (_shouldClearSessionForRefreshFailure(e)) {
        await clearForExpiredSession();
        if (!ref.mounted) {
          return false;
        }
        state = state.copyWith(errorMessage: () => e.toString());
        return false;
      }
      await _store.markForegroundAuthCheckNow();
      if (!ref.mounted) {
        return false;
      }
      state = state.copyWith(errorMessage: () => e.toString());
      return false;
    }
  }

  bool _shouldClearSessionForRefreshFailure(Object error) {
    if (error is CloudException) {
      return error.type == CloudErrorType.unauthorized ||
          error.type == CloudErrorType.forbidden;
    }
    if (error is StateError) {
      return true;
    }
    return false;
  }

  bool _shouldRefreshDuringRestore(StoredAuthSession stored) {
    return _isOlderThan(
      stored.lastRefreshAtEpochMs,
      _staleRestoreRefreshThreshold,
    );
  }

  bool _shouldRefreshForForegroundCheck(StoredAuthSession stored) {
    if (stored.accessToken.isEmpty ||
        stored.refreshToken.isEmpty ||
        stored.ownerId.isEmpty) {
      return false;
    }
    return _isOlderThan(
      stored.lastForegroundAuthCheckAtEpochMs,
      _foregroundAuthCheckThreshold,
    );
  }

  bool _isOlderThan(int epochMs, Duration threshold) {
    if (epochMs <= 0) {
      return true;
    }
    final now = DateTime.now().millisecondsSinceEpoch;
    return now - epochMs >= threshold.inMilliseconds;
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

final authSessionRefreshExecutorProvider = Provider<AuthSessionRefreshExecutor>((
  ref,
) {
  if (_shouldUseRemoteAuthRefreshEndpoint()) {
    return (String refreshToken) async {
      final client = CloudHttpClient();
      final response = await client.postJson(
        Uri.parse(
          '${CloudRuntimeConfig.gatewayBaseUrl}${UserApiMetadata.refreshTokenPath}',
        ),
        headers: CloudRequestHeaders.forPage(UserRequestPageIds.refreshToken),
        body: <String, dynamic>{'refreshToken': refreshToken},
      );
      return AuthLoginResultDto.fromMap(
        Map<String, dynamic>.from(response as Map),
      );
    };
  }
  return (String refreshToken) async {
    return AuthLoginResultDto.fromMap(<String, dynamic>{
      'accessToken': 'mock_refreshed_token_${refreshToken.hashCode}',
      'refreshToken': 'mock_refreshed_refresh',
      'ownerId': 'mock_owner_id',
      'activeSub': <String, dynamic>{'subAccountId': 'mock_sub_id'},
      'subAccountCount': 1,
      'accountState': 'active',
      'identityOrigin': 'phone',
    });
  };
});

bool _shouldUseRemoteAuthRefreshEndpoint() {
  const value = String.fromEnvironment('APP_DATA_SOURCE', defaultValue: '');
  if (value == 'remote') {
    return true;
  }
  if (value == 'mock') {
    return false;
  }
  if (CloudRuntimeConfig.appRuntimeEnv == 'beta' ||
      CloudRuntimeConfig.appRuntimeEnv == 'gamma' ||
      CloudRuntimeConfig.appRuntimeEnv == 'prod') {
    return true;
  }
  return false;
}
