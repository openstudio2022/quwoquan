import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:crypto/crypto.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/core/auth/terminal_account_cleanup_receipt_store.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/media/app_image_cache_controller.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show accountSessionLifecycleCommandWriterProvider;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
part "auth_session_controller.dart";

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

/// 软退出后"快速登录凭证"的默认有效期（秒）。默认 30 天。
///
/// 真相源为云端系统配置（登录/刷新时下发 `sessionRememberTtlSeconds`），
/// 端侧仅在云端未下发或旧数据缺失时用此默认值兜底，避免回归即失效。
const int kDefaultSessionRememberTtlSeconds = 2592000;

enum AuthSessionStatus { restoring, guest, authenticated }

enum AuthPromptReason {
  firstRun,
  manualLoggedOut,
  sessionExpired,
  accountSuspended,
  accountClosed,
  actionRequired,
}

enum AuthRememberedLoginMethod {
  unknown,
  oneTap,
  phoneOtp,
  wechat,
  alipay,
  qq,
  apple,
  passkey,
  anonymous,
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
    this.rememberedLoginMethod = AuthRememberedLoginMethod.unknown,
    this.rememberedLoginMaskedIdentifier = '',
    this.rememberedDisplayName = '',
    this.rememberedAvatarUrl = '',
    this.rememberedNicknameCustomized = false,
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
  final String rememberedDisplayName;
  final String rememberedAvatarUrl;
  final bool rememberedNicknameCustomized;
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
    String? rememberedDisplayName,
    String? rememberedAvatarUrl,
    bool? rememberedNicknameCustomized,
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
      rememberedDisplayName:
          rememberedDisplayName ?? this.rememberedDisplayName,
      rememberedAvatarUrl: rememberedAvatarUrl ?? this.rememberedAvatarUrl,
      rememberedNicknameCustomized:
          rememberedNicknameCustomized ?? this.rememberedNicknameCustomized,
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
    this.rememberedLoginIdentifier = '',
    this.rememberedDisplayName = '',
    this.rememberedAvatarUrl = '',
    this.rememberedNicknameCustomized = false,
    this.quickLoginExpiresAtEpochMs = 0,
    this.sessionRememberTtlSeconds = kDefaultSessionRememberTtlSeconds,
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

  /// 记住的完整登录标识（仅手机号验证码登录时持有完整手机号，存安全存储）。
  ///
  /// 用于「过期后再登录」自动预填手机号并自动发码，免去用户重新输入。掩码版本
  /// （[rememberedLoginMaskedIdentifier]）仅供展示；完整号仅用于本人快速重登。
  final String rememberedLoginIdentifier;
  final String rememberedDisplayName;
  final String rememberedAvatarUrl;
  final bool rememberedNicknameCustomized;

  /// 软退出后快速登录凭证的过期时间戳（epoch ms）。0 表示未设置（非软退出态）。
  final int quickLoginExpiresAtEpochMs;

  /// 云端下发并缓存的快速登录有效期（秒），软退出时据此推算过期戳。
  final int sessionRememberTtlSeconds;

  final bool manualLoggedOut;
  final bool launchPromptDismissed;

  /// 是否存在仍在有效期内的快速登录凭证（refreshToken 在且未过期）。
  ///
  /// `quickLoginExpiresAtEpochMs == 0` 表示旧数据/未显式写入过期戳，
  /// 此时按 `lastRefreshAt + ttl` 兜底，避免既往用户回归即失效。
  bool get hasValidQuickLoginCredential {
    if (refreshToken.trim().isEmpty) {
      return false;
    }
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    if (quickLoginExpiresAtEpochMs > 0) {
      return nowMs < quickLoginExpiresAtEpochMs;
    }
    if (lastRefreshAtEpochMs > 0) {
      return nowMs < lastRefreshAtEpochMs + sessionRememberTtlSeconds * 1000;
    }
    return true;
  }
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
  // 完整手机号属 PII，存安全存储（与 token 同等保护），不入 SharedPreferences。
  static const _rememberedLoginIdentifierKey =
      'auth.remembered_login_identifier';
  static const _rememberedDisplayNameKey = 'auth.remembered_display_name';
  static const _rememberedAvatarUrlKey = 'auth.remembered_avatar_url';
  static const _rememberedNicknameCustomizedKey =
      'auth.remembered_nickname_customized';
  static const _manualLoggedOutKey = 'auth.manual_logged_out';
  static const _launchPromptDismissedKey = 'auth.launch_prompt_dismissed';
  static const _quickLoginExpiresAtKey = 'auth.quick_login_expires_at_epoch_ms';
  static const _sessionRememberTtlKey = 'auth.session_remember_ttl_seconds';

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
      rememberedLoginIdentifier:
          await _secureStorage.read(key: _rememberedLoginIdentifierKey) ?? '',
      rememberedDisplayName: prefs.getString(_rememberedDisplayNameKey) ?? '',
      rememberedAvatarUrl: prefs.getString(_rememberedAvatarUrlKey) ?? '',
      rememberedNicknameCustomized:
          prefs.get(_rememberedNicknameCustomizedKey) == true,
      manualLoggedOut: prefs.getBool(_manualLoggedOutKey) ?? false,
      launchPromptDismissed: prefs.getBool(_launchPromptDismissedKey) ?? false,
      quickLoginExpiresAtEpochMs: prefs.getInt(_quickLoginExpiresAtKey) ?? 0,
      sessionRememberTtlSeconds:
          prefs.getInt(_sessionRememberTtlKey) ??
          kDefaultSessionRememberTtlSeconds,
    );
  }

  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
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
          accountHint: result.accountHint,
        );
    final normalizedDisplayName = result.accountHint?.displayName.trim() ?? '';
    final normalizedAvatarUrl = result.accountHint?.avatarUrl.trim() ?? '';
    final normalizedNicknameCustomized =
        result.accountHint?.nicknameCustomized ?? false;
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
    // 仅手机号验证码登录持有可复用的完整号；其他方式登录清除残留完整号，避免错配。
    final normalizedFullIdentifier =
        normalizedRememberedMethod == AuthRememberedLoginMethod.phoneOtp
        ? (rememberedLoginIdentifier ?? '').trim()
        : '';
    if (normalizedFullIdentifier.isNotEmpty) {
      await _secureStorage.write(
        key: _rememberedLoginIdentifierKey,
        value: normalizedFullIdentifier,
      );
    } else {
      await _secureStorage.delete(key: _rememberedLoginIdentifierKey);
    }
    await prefs.setString(_rememberedDisplayNameKey, normalizedDisplayName);
    await prefs.setString(_rememberedAvatarUrlKey, normalizedAvatarUrl);
    await prefs.setBool(
      _rememberedNicknameCustomizedKey,
      normalizedNicknameCustomized,
    );
    await prefs.setBool(_manualLoggedOutKey, false);
    await prefs.setBool(_launchPromptDismissedKey, false);
    // 缓存云端下发的快速登录有效期（缺省/<=0 用默认 30 天兜底），软退出时据此推算过期戳。
    await prefs.setInt(
      _sessionRememberTtlKey,
      _normalizedRememberTtl(result.sessionRememberTtlSeconds),
    );
    // 全新登录是活跃会话，清除任何残留的软退出过期戳。
    await prefs.remove(_quickLoginExpiresAtKey);
    await _ensureInstallId(prefs);
  }

  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {
    final prefs = await _prefsFactory();
    final nowEpochMs = DateTime.now().millisecondsSinceEpoch;
    await _secureStorage.write(key: _accessTokenKey, value: result.accessToken);
    await _secureStorage.write(
      key: _refreshTokenKey,
      value: result.refreshToken,
    );
    await prefs.setInt(_lastRefreshAtKey, nowEpochMs);
    await prefs.setInt(_lastForegroundAuthCheckAtKey, nowEpochMs);
    await prefs.setBool(_manualLoggedOutKey, false);
    await prefs.setBool(_launchPromptDismissedKey, false);
    await prefs.setInt(
      _sessionRememberTtlKey,
      _normalizedRememberTtl(result.sessionRememberTtlSeconds),
    );
    // 刷新成功代表会话仍活跃，清除残留的软退出过期戳；沿用登录时缓存的快速登录 TTL。
    await prefs.remove(_quickLoginExpiresAtKey);
    await _ensureInstallId(prefs);
  }

  Future<void> saveRefreshedAccountHint(
    AccountHintSnapshot? accountHint,
  ) async {
    if (accountHint == null) {
      return;
    }
    final prefs = await _prefsFactory();
    await prefs.setString(
      _rememberedLoginMaskedIdentifierKey,
      accountHint.maskedPhone.trim(),
    );
    await prefs.setString(
      _rememberedDisplayNameKey,
      accountHint.displayName.trim(),
    );
    await prefs.setString(
      _rememberedAvatarUrlKey,
      accountHint.avatarUrl.trim(),
    );
    await prefs.setBool(
      _rememberedNicknameCustomizedKey,
      accountHint.nicknameCustomized,
    );
  }

  int _normalizedRememberTtl(int ttlSeconds) {
    if (ttlSeconds <= 0) {
      return kDefaultSessionRememberTtlSeconds;
    }
    return ttlSeconds;
  }

  Future<void> updateActiveSubAccount(String subAccountId) async {
    final prefs = await _prefsFactory();
    await prefs.setString(_activeSubAccountIdKey, subAccountId.trim());
  }

  /// 软退出：保留快速登录凭证（refreshToken / 账号摘要），仅失效当前活跃会话。
  ///
  /// 个人设备（手机/iPad）上，用户主动退出后仍希望"有效期内免验证码快速登录"。
  /// 因此这里只删除 accessToken，保留 refreshToken / ownerId / identityOrigin /
  /// remembered* 摘要，并写入快速登录过期时间戳（now + 有效期）。
  /// 不调用远端吊销由调用方（settings）保证。
  Future<void> softLogout() async {
    final prefs = await _prefsFactory();
    await _secureStorage.delete(key: _accessTokenKey);
    final ttlSeconds =
        prefs.getInt(_sessionRememberTtlKey) ??
        kDefaultSessionRememberTtlSeconds;
    final expiresAtMs =
        DateTime.now().millisecondsSinceEpoch + ttlSeconds * 1000;
    await prefs.setInt(_quickLoginExpiresAtKey, expiresAtMs);
    await prefs.setBool(_manualLoggedOutKey, true);
    await prefs.setBool(_launchPromptDismissedKey, false);
    await _ensureInstallId(prefs);
  }

  Future<void> clearSession({required bool manualLogout}) async {
    final prefs = await _prefsFactory();
    final rememberedAvatarUrl =
        prefs.getString(_rememberedAvatarUrlKey)?.trim() ?? '';
    await _secureStorage.delete(key: _accessTokenKey);
    await _secureStorage.delete(key: _refreshTokenKey);
    // 彻底退出清除本机完整手机号，避免他人沿用快速重登。
    await _secureStorage.delete(key: _rememberedLoginIdentifierKey);
    await prefs.remove(_ownerIdKey);
    await prefs.remove(_activeSubAccountIdKey);
    await prefs.remove(_accountStateKey);
    await prefs.remove(_identityOriginKey);
    await prefs.remove(_lastRefreshAtKey);
    await prefs.remove(_lastForegroundAuthCheckAtKey);
    await prefs.remove(_quickLoginExpiresAtKey);
    await prefs.remove(_sessionRememberTtlKey);
    if (manualLogout) {
      await prefs.remove(_rememberedLoginMethodKey);
      await prefs.remove(_rememberedLoginMaskedIdentifierKey);
      await prefs.remove(_rememberedDisplayNameKey);
      await prefs.remove(_rememberedAvatarUrlKey);
      await prefs.remove(_rememberedNicknameCustomizedKey);
      await AppImageCacheController.evictAvatar(
        rememberedAvatarUrl,
        size: AppSpacing.loginAvatarSize,
      );
    }
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

  static String _activeSubAccountIdFromResult(AuthSessionGrant result) =>
      result.activeSub?.subAccountId.trim() ?? '';

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
      'alipay' => AuthRememberedLoginMethod.alipay,
      'qq' => AuthRememberedLoginMethod.qq,
      'apple' => AuthRememberedLoginMethod.apple,
      'passkey' => AuthRememberedLoginMethod.passkey,
      'anonymous_device' => AuthRememberedLoginMethod.anonymous,
      _ => AuthRememberedLoginMethod.unknown,
    };
  }

  static String _normalizedRememberedMaskedIdentifier({
    required AuthRememberedLoginMethod method,
    String? maskedIdentifier,
    AccountHintSnapshot? accountHint,
  }) {
    final explicitMasked = maskedIdentifier?.trim() ?? '';
    if (explicitMasked.isNotEmpty) {
      return explicitMasked;
    }
    final hintMaskedPhone = accountHint?.maskedPhone.trim() ?? '';
    if (hintMaskedPhone.isNotEmpty) {
      return hintMaskedPhone;
    }
    return '';
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
