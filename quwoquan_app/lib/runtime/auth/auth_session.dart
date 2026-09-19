import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_observer.dart';
import 'package:quwoquan_app/runtime/config/generated/app_launch_contract.g.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';
import 'package:quwoquan_app/runtime/auth/rehearsal_auth_port.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/state/startup_auth_restore_gate_provider.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/runtime/transport/cloud_request_headers.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/runtime/auth/terminal_account_cleanup_receipt_store.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/platform/media/app_image_cache_controller.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart'
    show
        accountSessionLifecycleCommandWriterProvider,
        accountSessionLoginCommandWriterProvider,
        exceptionTelemetryPortProvider;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
part "auth_session_controller.dart";

/// 派生隐私安全的设备 actor 标识（installId hash 派生，非原始设备 ID）。
///
/// 用用途隔离且已冻结的 canonical salt 字节对 installId 做 SHA-256，取前 32 位 hex，既稳定可复算、
/// 又不回传原始 installId/设备 ID。游客以此作为设备维度计数键；登录用户也携带。
String deriveDeviceActorId(String installId) {
  final trimmed = installId.trim();
  if (trimmed.isEmpty) {
    return '';
  }
  // `v1` 是已落盘/上送身份算法的一部分，不是可协商版本；它是唯一合法字节。
  final digest = sha256.convert(utf8.encode('qwq-device-actor-v1:$trimmed'));
  return digest.toString().substring(0, 32);
}

/// 为匿名会话 bootstrap 派生不可逆、安装级稳定的设备指纹。
///
/// App 不读取硬件唯一标识；服务端只收到独立 salt 的 SHA-256 摘要。该值仅用于
/// `LoginAnonymous` 幂等复用，不能作为凭证，也不能替代服务端签发的 bearer。
String deriveAnonymousDeviceFingerprintHash(String installId) {
  final trimmed = installId.trim();
  if (trimmed.isEmpty) {
    return '';
  }
  // 与服务端幂等绑定的既有字节必须保持稳定；禁止再引入第二套 salt。
  return sha256
      .convert(utf8.encode('qwq-anonymous-device-v1:$trimmed'))
      .toString();
}

void _syncDeviceActorId(String installId) {
  AppTraceContextStore.instance.deviceActorId = deriveDeviceActorId(installId);
}

/// 软退出后"快速登录凭证"的默认有效期（秒）。默认 30 天。
///
/// 真相源为云端系统配置（登录/刷新时下发 `sessionRememberTtlSeconds`），
/// 云端未声明正数时使用该唯一默认策略。
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
    this.activePersonaId = '',
    this.accountState = '',
    this.identityOrigin = '',
    this.installId = '',
    this.rememberedLoginMethod = AuthRememberedLoginMethod.unknown,
    this.rememberedLoginMaskedIdentifier = '',
    this.rememberedDisplayName = '',
    this.rememberedAvatarUrl = '',
    this.rememberedNicknameCustomized = false,
    this.rehearsalIdentityId = '',
    this.errorMessage,
  });

  const AuthSessionState.restoring()
    : this(status: AuthSessionStatus.restoring);

  final AuthSessionStatus status;
  final AuthPromptReason? promptReason;
  final String accessToken;
  final String refreshToken;
  final String ownerId;
  final String activePersonaId;
  final String accountState;
  final String identityOrigin;
  final String installId;
  final AuthRememberedLoginMethod rememberedLoginMethod;
  final String rememberedLoginMaskedIdentifier;
  final String rememberedDisplayName;
  final String rememberedAvatarUrl;
  final bool rememberedNicknameCustomized;
  final String rehearsalIdentityId;
  final String? errorMessage;

  bool get isAnonymousSession => accountState.trim() == 'anonymous';

  /// 已由服务端签发、可供 transport 使用的可信会话。
  ///
  /// 匿名会话也满足该条件，但仍保持 [isGuest]，不能绕过显式登录门。
  bool get hasTrustedSession =>
      accessToken.trim().isNotEmpty &&
      refreshToken.trim().isNotEmpty &&
      ownerId.trim().isNotEmpty &&
      activePersonaId.trim().isNotEmpty;

  bool get isRehearsalSession => rehearsalIdentityId.trim().isNotEmpty;

  bool get isAuthenticated =>
      status == AuthSessionStatus.authenticated &&
      (hasTrustedSession || isRehearsalSession) &&
      !isAnonymousSession;

  bool get isGuest => status == AuthSessionStatus.guest;

  bool get hasRememberedLogin =>
      rememberedLoginMethod != AuthRememberedLoginMethod.unknown;

  AuthSessionState copyWith({
    AuthSessionStatus? status,
    AuthPromptReason? Function()? promptReason,
    String? accessToken,
    String? refreshToken,
    String? ownerId,
    String? activePersonaId,
    String? accountState,
    String? identityOrigin,
    String? installId,
    AuthRememberedLoginMethod? rememberedLoginMethod,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedDisplayName,
    String? rememberedAvatarUrl,
    bool? rememberedNicknameCustomized,
    String? rehearsalIdentityId,
    String? Function()? errorMessage,
  }) {
    return AuthSessionState(
      status: status ?? this.status,
      promptReason: promptReason != null ? promptReason() : this.promptReason,
      accessToken: accessToken ?? this.accessToken,
      refreshToken: refreshToken ?? this.refreshToken,
      ownerId: ownerId ?? this.ownerId,
      activePersonaId: activePersonaId ?? this.activePersonaId,
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
      rehearsalIdentityId: rehearsalIdentityId ?? this.rehearsalIdentityId,
      errorMessage: errorMessage != null ? errorMessage() : this.errorMessage,
    );
  }
}

class StoredAuthSession {
  const StoredAuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.ownerId,
    required this.activePersonaId,
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
    this.rememberedRefreshToken = '',
    this.quickLoginExpiresAtEpochMs = 0,
    this.sessionRememberTtlSeconds = kDefaultSessionRememberTtlSeconds,
    required this.manualLoggedOut,
    required this.launchPromptDismissed,
  });

  final String accessToken;
  final String refreshToken;
  final String ownerId;
  final String activePersonaId;
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

  /// 软退出后保留的显式账号 refresh token。
  ///
  /// 它与当前活跃 transport 会话的 [refreshToken] 分槽保存，避免可信游客会话覆盖
  /// 返回账号的快速登录凭证。
  final String rememberedRefreshToken;

  /// 软退出后快速登录凭证的过期时间戳（epoch ms）。0 表示未设置（非软退出态）。
  final int quickLoginExpiresAtEpochMs;

  /// 云端下发并缓存的快速登录有效期（秒），软退出时据此推算过期戳。
  final int sessionRememberTtlSeconds;

  final bool manualLoggedOut;
  final bool launchPromptDismissed;

  /// 是否存在仍在显式有效期内的快速登录凭证。
  bool get hasValidQuickLoginCredential {
    if (rememberedRefreshToken.trim().isEmpty ||
        quickLoginExpiresAtEpochMs <= 0) {
      return false;
    }
    return DateTime.now().millisecondsSinceEpoch < quickLoginExpiresAtEpochMs;
  }

  String get quickLoginRefreshToken => rememberedRefreshToken.trim();

  bool get hasCompleteActiveSession =>
      accessToken.trim().isNotEmpty &&
      refreshToken.trim().isNotEmpty &&
      ownerId.trim().isNotEmpty &&
      activePersonaId.trim().isNotEmpty;

  bool get isAnonymousSession => accountState.trim() == 'anonymous';
}

final class _IsolatedAuthSessionStore extends AuthSessionStore {
  _IsolatedAuthSessionStore({
    required RehearsalStorageNamespace namespace,
    required VerifiedRehearsalSpace? Function() currentSpace,
    super.secureStorage,
    super.prefsFactory,
    RehearsalStorageObserver? observer,
  }) : super(storageNamespace: namespace.authNamespace) {
    _configureIsolatedStorage(
      namespace: namespace,
      currentSpace: currentSpace,
      observer: observer,
    );
  }
}

extension AuthSessionStoreIsolation on AuthSessionStore {
  bool get isIsolated => this is _IsolatedAuthSessionStore;
  void requireCurrentStorage() {
    if (isIsolated) _requireCurrentStorage();
  }

  void dispose() {
    if (isIsolated) {
      _disposed = true;
      _authObserver?.invalidate();
      _installObserver?.invalidate();
    }
  }

  Future<void> saveSyntheticSession(
    SyntheticSessionResult result, {
    void Function()? fence,
  }) {
    if (!isIsolated) {
      throw contentCapabilityUnavailable('synthetic_session_storage');
    }
    return _saveSyntheticSession(result, fence: fence);
  }
}

class AuthSessionStore {
  AuthSessionStore({
    FlutterSecureStorage? secureStorage,
    Future<SharedPreferences> Function()? prefsFactory,
    String storageNamespace = 'unbound',
  }) : _currentSpace = null,
       _storageNamespace = storageNamespace.trim(),
       _secureStorage = secureStorage ?? const FlutterSecureStorage(),
       _rawPrefsFactory = prefsFactory ?? SharedPreferences.getInstance {
    if (_storageNamespace.isEmpty) {
      throw ArgumentError.value(storageNamespace, 'storageNamespace');
    }
  }

  factory AuthSessionStore.isolated({
    required RehearsalStorageNamespace namespace,
    required VerifiedRehearsalSpace? Function() currentSpace,
    FlutterSecureStorage? secureStorage,
    Future<SharedPreferences> Function()? prefsFactory,
    RehearsalStorageObserver? observer,
  }) {
    return _IsolatedAuthSessionStore(
      namespace: namespace,
      currentSpace: currentSpace,
      secureStorage: secureStorage,
      prefsFactory: prefsFactory,
      observer: observer,
    );
  }

  void _configureIsolatedStorage({
    required RehearsalStorageNamespace namespace,
    required VerifiedRehearsalSpace? Function() currentSpace,
    RehearsalStorageObserver? observer,
  }) {
    _currentSpace = currentSpace;
    _isolatedNamespace = namespace;
    requireCurrentStorage();
    _authObserver = observer?.attach('auth', namespace);
    try {
      _installObserver = observer?.attach('installId', namespace);
    } catch (_) {
      _authObserver?.invalidate();
      rethrow;
    }
  }

  final String _storageNamespace;
  RehearsalStorageNamespace? _isolatedNamespace;
  VerifiedRehearsalSpace? Function()? _currentSpace;
  bool _disposed = false;
  RehearsalConsumerObserver? _authObserver;
  RehearsalConsumerObserver? _installObserver;

  void _requireCurrentStorage() {
    if (_disposed) throw contentCapabilityUnavailable('auth_storage_disposed');
    final namespace = _isolatedNamespace;
    try {
      if (namespace != null) namespace.requireCurrent(_currentSpace!());
      _authObserver?.requireCurrent();
      _installObserver?.requireCurrent();
    } catch (_) {
      _authObserver?.invalidate();
      _installObserver?.invalidate();
      rethrow;
    }
  }

  void _recordAuth(
    RehearsalSuccessfulOperation operation, {
    void Function()? fence,
  }) {
    requireCurrentStorage();
    fence?.call();
    _authObserver?.recordSuccess(operation, fence: requireCurrentStorage);
  }

  Future<SharedPreferences> _prefsFactory() async {
    requireCurrentStorage();
    // SharedPreferences 首次装载会读全局 getAll；isolated 不允许接触旧缓存。
    if (isIsolated) {
      throw contentCapabilityUnavailable('isolated_auth_preferences');
    }
    final prefs = await _rawPrefsFactory();
    requireCurrentStorage();
    return prefs;
  }

  String _scopedKey(String suffix) {
    requireCurrentStorage();
    return 'auth.${Uri.encodeComponent(_storageNamespace)}.$suffix';
  }

  String get _accessTokenKey => _scopedKey('access_token');
  String get _refreshTokenKey => _scopedKey('refresh_token');
  String get _rememberedRefreshTokenKey =>
      _scopedKey('remembered_refresh_token');
  String get _ownerIdKey => _scopedKey('owner_id');
  String get _activePersonaIdKey => _scopedKey('active_persona_id');
  String get _accountStateKey => _scopedKey('account_state');
  String get _identityOriginKey => _scopedKey('identity_origin');
  // installId 只标识安装，不是授权凭据，不随 target 变化。
  String get _installIdKey {
    requireCurrentStorage();
    return _isolatedNamespace?.installIdKey ?? 'auth.install_id';
  }

  String get _lastRefreshAtKey => _scopedKey('last_refresh_at_epoch_ms');
  String get _lastForegroundAuthCheckAtKey =>
      _scopedKey('last_foreground_auth_check_at_epoch_ms');
  String get _rememberedLoginMethodKey => _scopedKey('remembered_login_method');
  String get _rememberedLoginMaskedIdentifierKey =>
      _scopedKey('remembered_login_masked_identifier');
  // 完整手机号与 token 同样保存在安全存储。
  String get _rememberedLoginIdentifierKey =>
      _scopedKey('remembered_login_identifier');
  String get _rememberedDisplayNameKey => _scopedKey('remembered_display_name');
  String get _rememberedAvatarUrlKey => _scopedKey('remembered_avatar_url');
  String get _rememberedNicknameCustomizedKey =>
      _scopedKey('remembered_nickname_customized');
  String get _manualLoggedOutKey => _scopedKey('manual_logged_out');
  String get _launchPromptDismissedKey => _scopedKey('launch_prompt_dismissed');
  String get _quickLoginExpiresAtKey =>
      _scopedKey('quick_login_expires_at_epoch_ms');
  String get _sessionRememberTtlKey =>
      _scopedKey('session_remember_ttl_seconds');

  final FlutterSecureStorage _secureStorage;
  final Future<SharedPreferences> Function() _rawPrefsFactory;

  Future<StoredAuthSession> read() async {
    if (isIsolated) return _readIsolatedSession();
    final prefs = await _prefsFactory();
    final installId = await _ensureInstallId(prefs);
    final activePersonaId = prefs.getString(_activePersonaIdKey)?.trim() ?? '';
    final accessToken = await _secureStorage.read(key: _accessTokenKey) ?? '';
    final refreshToken = await _secureStorage.read(key: _refreshTokenKey) ?? '';
    final rememberedRefreshToken =
        await _secureStorage.read(key: _rememberedRefreshTokenKey) ?? '';
    final manualLoggedOut = prefs.getBool(_manualLoggedOutKey) ?? false;
    final accountState = prefs.getString(_accountStateKey) ?? '';
    final identityOrigin = prefs.getString(_identityOriginKey) ?? '';
    return StoredAuthSession(
      accessToken: accessToken,
      refreshToken: refreshToken,
      ownerId: prefs.getString(_ownerIdKey) ?? '',
      activePersonaId: activePersonaId,
      accountState: accountState,
      identityOrigin: identityOrigin,
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
      rememberedRefreshToken: rememberedRefreshToken,
      manualLoggedOut: manualLoggedOut,
      launchPromptDismissed: prefs.getBool(_launchPromptDismissedKey) ?? false,
      quickLoginExpiresAtEpochMs: prefs.getInt(_quickLoginExpiresAtKey) ?? 0,
      sessionRememberTtlSeconds:
          prefs.getInt(_sessionRememberTtlKey) ??
          kDefaultSessionRememberTtlSeconds,
    );
  }

  Future<StoredAuthSession> _readIsolatedSession() async {
    final installId = await _ensureIsolatedInstallId();
    final raw = await _secureStorage.read(key: _scopedKey('synthetic_session'));
    requireCurrentStorage();
    if (raw != null) _recordAuth(RehearsalSuccessfulOperation.read);
    final session = raw == null
        ? null
        : SyntheticSessionResult.fromWire(
            (jsonDecode(raw) as Map).cast<String, Object?>(),
          );
    return StoredAuthSession(
      accessToken: '',
      refreshToken: '',
      ownerId: session?.accountId ?? '',
      activePersonaId: session?.personaId ?? '',
      accountState: session == null ? '' : 'rehearsal',
      identityOrigin: session == null ? '' : 'synthetic',
      installId: installId,
      manualLoggedOut: false,
      launchPromptDismissed: false,
    );
  }

  /// 单条本地身份记录，无 Remote grant、token 或真实账号摘要。
  Future<void> _saveSyntheticSession(
    SyntheticSessionResult result, {
    void Function()? fence,
  }) async {
    requireCurrentStorage();
    if (!isIsolated) {
      throw contentCapabilityUnavailable('synthetic_session_storage');
    }
    fence?.call();
    await _secureStorage.write(
      key: _scopedKey('synthetic_session'),
      value: jsonEncode(result.toWire()),
    );
    _recordAuth(RehearsalSuccessfulOperation.write, fence: fence);
  }

  void _requireRemoteGrantStorage() {
    requireCurrentStorage();
    if (isIsolated) throw contentCapabilityUnavailable('remote_grant_storage');
  }

  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {
    _requireRemoteGrantStorage();
    // 匿名会话只由服务端 canonical accountState 判定；登录方式仅描述用户动作。
    final isAnonymousSession = result.accountState.trim() == 'anonymous';
    final prefs = await _prefsFactory();
    final activePersona = _activePersonaIdFromResult(result);
    final nowEpochMs = DateTime.now().millisecondsSinceEpoch;
    final normalizedRememberedMethod = rememberedLoginMethod;
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
    await prefs.setString(_activePersonaIdKey, activePersona);
    await prefs.setString(_accountStateKey, result.accountState);
    await prefs.setString(_identityOriginKey, result.identityOrigin);
    await prefs.setInt(_lastRefreshAtKey, nowEpochMs);
    await prefs.setInt(_lastForegroundAuthCheckAtKey, nowEpochMs);
    if (!isAnonymousSession) {
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
      await _secureStorage.delete(key: _rememberedRefreshTokenKey);
      await prefs.setString(_rememberedDisplayNameKey, normalizedDisplayName);
      await prefs.setString(_rememberedAvatarUrlKey, normalizedAvatarUrl);
      await prefs.setBool(
        _rememberedNicknameCustomizedKey,
        normalizedNicknameCustomized,
      );
      await prefs.setBool(_manualLoggedOutKey, false);
      await prefs.setBool(_launchPromptDismissedKey, false);
      // 全新显式登录是活跃会话，清除任何残留的软退出过期戳。
      await prefs.remove(_quickLoginExpiresAtKey);
    }
    // 缓存云端下发的快速登录有效期；非正数统一使用当前默认策略。
    await prefs.setInt(
      _sessionRememberTtlKey,
      _normalizedRememberTtl(result.sessionRememberTtlSeconds),
    );
    await _ensureInstallId(prefs);
  }

  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {
    _requireRemoteGrantStorage();
    final prefs = await _prefsFactory();
    final nowEpochMs = DateTime.now().millisecondsSinceEpoch;
    final isAnonymousSession =
        (prefs.getString(_accountStateKey) ?? '').trim() == 'anonymous';
    await _secureStorage.write(key: _accessTokenKey, value: result.accessToken);
    await _secureStorage.write(
      key: _refreshTokenKey,
      value: result.refreshToken,
    );
    await prefs.setInt(_lastRefreshAtKey, nowEpochMs);
    await prefs.setInt(_lastForegroundAuthCheckAtKey, nowEpochMs);
    await prefs.setInt(
      _sessionRememberTtlKey,
      _normalizedRememberTtl(result.sessionRememberTtlSeconds),
    );
    if (!isAnonymousSession) {
      await prefs.setBool(_manualLoggedOutKey, false);
      await prefs.setBool(_launchPromptDismissedKey, false);
      // 显式会话刷新成功代表会话仍活跃，清除残留的软退出过期戳。
      await prefs.remove(_quickLoginExpiresAtKey);
    }
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

  Future<void> updateActivePersona(String personaId) async {
    final prefs = await _prefsFactory();
    await prefs.setString(_activePersonaIdKey, personaId.trim());
  }

  /// 软退出：把显式账号 refresh token 移入 remembered 槽，仅失效当前活跃会话。
  ///
  /// 个人设备（手机/iPad）上，用户主动退出后仍希望"有效期内免验证码快速登录"。
  /// 因此删除活跃 access/refresh，保留 remembered refresh 与账号摘要，并写入
  /// 快速登录过期时间戳（now + 有效期）。
  /// 不调用远端吊销由调用方（settings）保证。
  Future<void> softLogout() async {
    if (isIsolated) return clearSession(manualLogout: true);
    final prefs = await _prefsFactory();
    final refreshToken = await _secureStorage.read(key: _refreshTokenKey) ?? '';
    if (refreshToken.trim().isNotEmpty) {
      await _secureStorage.write(
        key: _rememberedRefreshTokenKey,
        value: refreshToken,
      );
    }
    await _secureStorage.delete(key: _accessTokenKey);
    await _secureStorage.delete(key: _refreshTokenKey);
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
    if (isIsolated) {
      await _secureStorage.delete(key: _scopedKey('synthetic_session'));
      // 幂等delete成功只证明删除调用已完成，不推断原记录存在。
      _recordAuth(RehearsalSuccessfulOperation.delete);
      return;
    }
    final prefs = await _prefsFactory();
    final rememberedAvatarUrl =
        prefs.getString(_rememberedAvatarUrlKey)?.trim() ?? '';
    final activeSessionIsAnonymous =
        (prefs.getString(_accountStateKey) ?? '').trim() == 'anonymous';
    final rememberedRefreshToken =
        await _secureStorage.read(key: _rememberedRefreshTokenKey) ?? '';
    final preserveRememberedExplicitCredential =
        !manualLogout &&
        activeSessionIsAnonymous &&
        rememberedRefreshToken.trim().isNotEmpty;
    await _secureStorage.delete(key: _accessTokenKey);
    await _secureStorage.delete(key: _refreshTokenKey);
    if (!preserveRememberedExplicitCredential) {
      await _secureStorage.delete(key: _rememberedRefreshTokenKey);
      // 彻底退出或显式会话失效时清除本机完整手机号。
      await _secureStorage.delete(key: _rememberedLoginIdentifierKey);
    }
    await prefs.remove(_ownerIdKey);
    await prefs.remove(_activePersonaIdKey);
    await prefs.remove(_accountStateKey);
    await prefs.remove(_identityOriginKey);
    await prefs.remove(_lastRefreshAtKey);
    await prefs.remove(_lastForegroundAuthCheckAtKey);
    if (!preserveRememberedExplicitCredential) {
      await prefs.remove(_quickLoginExpiresAtKey);
      await prefs.remove(_sessionRememberTtlKey);
    }
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
    if (isIsolated) {
      await _secureStorage.write(key: _launchPromptDismissedKey, value: 'true');
      _recordAuth(RehearsalSuccessfulOperation.write);
      return;
    }
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

  Future<String> _ensureIsolatedInstallId() async {
    final existing = await _secureStorage.read(key: _installIdKey);
    requireCurrentStorage();
    if (existing != null) {
      _installObserver?.recordSuccess(
        RehearsalSuccessfulOperation.read,
        fence: requireCurrentStorage,
      );
    }
    if (existing != null && existing.trim().isNotEmpty) return existing;
    final generated = const Uuid().v4();
    await _secureStorage.write(key: _installIdKey, value: generated);
    requireCurrentStorage();
    _installObserver?.recordSuccess(
      RehearsalSuccessfulOperation.write,
      fence: requireCurrentStorage,
    );
    return generated;
  }

  Future<String> _ensureInstallId(SharedPreferences prefs) async {
    final existing = prefs.getString(_installIdKey);
    if (existing != null && existing.trim().isNotEmpty) {
      return existing;
    }
    final generated = const Uuid().v4();
    final saved = await prefs.setString(_installIdKey, generated);
    requireCurrentStorage();
    if (!saved) throw StateError('install identity persistence failed');
    return generated;
  }

  static String _activePersonaIdFromResult(AuthSessionGrant result) =>
      result.activePersona?.personaId.trim() ?? '';

  static AuthRememberedLoginMethod _rememberedLoginMethodFromRaw(String? raw) {
    final normalized = raw?.trim() ?? '';
    for (final method in AuthRememberedLoginMethod.values) {
      if (method.name == normalized) {
        return method;
      }
    }
    return AuthRememberedLoginMethod.unknown;
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

  final FutureOr<String?> Function() _readAccessToken;

  @override
  Future<String?> getAccessToken() async {
    final token = (await _readAccessToken())?.trim() ?? '';
    return token.isEmpty ? null : token;
  }
}

/// 启动owner注入同一纯内存observer；读取它不得构造auth/pending store。
final rehearsalStorageObserverProvider = Provider<RehearsalStorageObserver?>(
  (ref) => null,
);

final authSessionStoreProvider = Provider<AuthSessionStore>((ref) {
  final space = CloudRuntimeConfig.rehearsalSpace;
  final store = space?.isIsolated == true
      ? AuthSessionStore.isolated(
          namespace: RehearsalStorageNamespace(space!),
          currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
          observer: ref.read(rehearsalStorageObserverProvider),
        )
      : AuthSessionStore(
          storageNamespace:
              '${CloudRuntimeConfig.launchTarget}|${CloudRuntimeConfig.appEnvironment}',
        );
  ref.onDispose(store.dispose);
  return store;
});

final authSessionControllerProvider =
    NotifierProvider<AuthSessionController, AuthSessionState>(
      AuthSessionController.new,
    );

/// Isolated restore 完成后由启动组合根观察；默认不采集。
final syntheticSessionRestoredObserverProvider =
    Provider<Future<void> Function(AuthSessionState)?>((ref) => null);
