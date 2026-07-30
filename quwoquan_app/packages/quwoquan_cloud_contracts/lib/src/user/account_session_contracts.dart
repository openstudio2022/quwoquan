import '../operation_request_payload.dart';
part '../generated/requests/user/account_session_contracts.requests.g.dart';

/// AccountSession 聚合登录/刷新/登出命令的 pure contracts。
/// 真相源：quwoquan_service/services/user-service/contracts/account/account_session/{service,fields}.yaml。
/// 六路登录 bootstrap 无 bearer；refresh rotation 重放触发 lineage 吊销。

/// Alpha/test 对齐 USER.AUTH.token_expired 的强类型边界信号。
///
/// production Remote 由 runtime mapper 抛出携带 RuntimeFailure 的 CloudException。
final class AccountSessionTokenExpiredException implements Exception {
  const AccountSessionTokenExpiredException();
}

/// 登录响应中的激活分身摘要（wire: activePersona envelope）。
final class ActivePersonaEnvelope {
  const ActivePersonaEnvelope({required this.personaId});

  final String personaId;
}

/// 登录响应中的既有账号提示（wire: accountHint，用于快速登录确认 UI）。
final class AccountHintSnapshot {
  const AccountHintSnapshot({
    required this.displayName,
    required this.nicknameCustomized,
    required this.avatarUrl,
    required this.avatarAssetId,
    required this.maskedPhone,
    required this.identityOrigin,
  });

  final String displayName;
  final bool nicknameCustomized;
  final String avatarUrl;
  final String avatarAssetId;
  final String maskedPhone;
  final String identityOrigin;
}

/// 六路登录的统一会话签发结果。
final class AuthSessionGrant {
  const AuthSessionGrant({
    required this.accessToken,
    required this.refreshToken,
    required this.ownerId,
    required this.accountState,
    required this.identityOrigin,
    required this.logicalShard,
    required this.anonymousRetentionPolicy,
    required this.personaCount,
    required this.sessionRememberTtlSeconds,
    this.activePersona,
    this.accountHint,
  });

  final String accessToken;
  final String refreshToken;
  final String ownerId;
  final String accountState;
  final String identityOrigin;
  final int logicalShard;
  final String anonymousRetentionPolicy;
  final int personaCount;

  /// 快速登录有效期（秒）；0 表示云端未下发，端侧用默认值兜底。
  final int sessionRememberTtlSeconds;
  final ActivePersonaEnvelope? activePersona;
  final AccountHintSnapshot? accountHint;
}

enum FederatedLoginStatus { authenticated, phoneBindingRequired }

/// 社交登录的单轨判别结果。首次社交身份需要绑定手机号时不得携带 session。
final class FederatedLoginOutcome {
  const FederatedLoginOutcome.authenticated(AuthSessionGrant session)
    : status = FederatedLoginStatus.authenticated,
      session = session,
      bindingTicket = null,
      provider = null,
      expiresInSeconds = 0;

  const FederatedLoginOutcome.phoneBindingRequired({
    required String bindingTicket,
    required String provider,
    required int expiresInSeconds,
  }) : status = FederatedLoginStatus.phoneBindingRequired,
       session = null,
       bindingTicket = bindingTicket,
       provider = provider,
       expiresInSeconds = expiresInSeconds;

  final FederatedLoginStatus status;
  final AuthSessionGrant? session;
  final String? bindingTicket;
  final String? provider;
  final int expiresInSeconds;
}

final class TokenRefreshGrant {
  const TokenRefreshGrant({
    required this.accessToken,
    required this.refreshToken,
    required this.sessionRememberTtlSeconds,
  });

  final String accessToken;
  final String refreshToken;
  final int sessionRememberTtlSeconds;
}

final class LogoutAck {
  const LogoutAck({required this.revoked});

  final bool revoked;
}

/// 登录 bootstrap 子 Facet；仅包含不依赖既有 bearer session 的登录命令。
abstract interface class AccountSessionLoginCommandWriter {
  Future<AuthSessionGrant> loginWithPhone(LoginWithPhoneCommand command);

  Future<FederatedLoginOutcome> loginWithWechat(LoginWithWechatCommand command);

  Future<FederatedLoginOutcome> loginWithAlipay(LoginWithAlipayCommand command);

  Future<FederatedLoginOutcome> loginWithQq(LoginWithQqCommand command);

  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command);

  Future<AuthSessionGrant> loginAnonymous(LoginAnonymousCommand command);
}

/// 已签发会话的生命周期子 Facet。
abstract interface class AccountSessionLifecycleCommandWriter {
  Future<TokenRefreshGrant> refreshToken(RefreshTokenCommand command);

  Future<LogoutAck> logout(LogoutCommand command);
}

/// 组合装配边界。
///
/// 业务消费者应依赖上面的 login 或 lifecycle 子 Facet；该接口仅供需要同时装配
/// 两组能力的 composition root 使用，且总方法数仍小于 10。
abstract interface class AccountSessionCommandWriter
    implements
        AccountSessionLoginCommandWriter,
        AccountSessionLifecycleCommandWriter {}

AuthSessionGrant decodeAuthSessionGrant(Object? value) {
  final map = _object(value, 'AuthSessionGrant');
  return AuthSessionGrant(
    accessToken: _string(map, 'accessToken'),
    refreshToken: _string(map, 'refreshToken'),
    ownerId: _string(map, 'ownerId'),
    accountState: _stringOr(map, 'accountState', ''),
    identityOrigin: _stringOr(map, 'identityOrigin', ''),
    logicalShard: _intOr(map, 'logicalShard', 0),
    anonymousRetentionPolicy: _stringOr(map, 'anonymousRetentionPolicy', ''),
    personaCount: _intOr(map, 'personaCount', 0),
    sessionRememberTtlSeconds: _intOr(map, 'sessionRememberTtlSeconds', 0),
    activePersona: _activePersona(map['activePersona']),
    accountHint: _accountHint(map['accountHint']),
  );
}

FederatedLoginOutcome decodeFederatedLoginOutcome(Object? value) {
  final map = _object(value, 'FederatedLoginOutcome');
  final rawStatus = _string(map, 'status');
  switch (rawStatus) {
    case 'authenticated':
      if (map['bindingTicket'] != null) {
        throw const FormatException(
          'authenticated federated outcome must not include bindingTicket',
        );
      }
      return FederatedLoginOutcome.authenticated(
        decodeAuthSessionGrant(map['session']),
      );
    case 'phoneBindingRequired':
      if (map['session'] != null) {
        throw const FormatException(
          'phoneBindingRequired outcome must not include session',
        );
      }
      final expiresInSeconds = _intOr(map, 'expiresInSeconds', 0);
      if (expiresInSeconds <= 0) {
        throw const FormatException(
          'phoneBindingRequired.expiresInSeconds must be positive',
        );
      }
      return FederatedLoginOutcome.phoneBindingRequired(
        bindingTicket: _string(map, 'bindingTicket'),
        provider: _string(map, 'provider'),
        expiresInSeconds: expiresInSeconds,
      );
    default:
      throw FormatException('unsupported federated login status: $rawStatus');
  }
}

TokenRefreshGrant decodeTokenRefreshGrant(Object? value) {
  final map = _object(value, 'TokenRefreshGrant');
  return TokenRefreshGrant(
    accessToken: _string(map, 'accessToken'),
    refreshToken: _string(map, 'refreshToken'),
    sessionRememberTtlSeconds: _intOr(map, 'sessionRememberTtlSeconds', 0),
  );
}

LogoutAck decodeLogoutAck(Object? value) {
  if (value == null) return const LogoutAck(revoked: true);
  final map = _object(value, 'LogoutAck');
  final revoked = map['revoked'];
  return LogoutAck(revoked: revoked is bool ? revoked : true);
}

ActivePersonaEnvelope? _activePersona(Object? value) {
  if (value == null) return null;
  final map = _object(value, 'activePersona');
  final personaId = map['personaId'];
  if (personaId is! String || personaId.trim().isEmpty) {
    return null;
  }
  return ActivePersonaEnvelope(personaId: personaId.trim());
}

AccountHintSnapshot? _accountHint(Object? value) {
  if (value == null) return null;
  final map = _object(value, 'accountHint');
  return AccountHintSnapshot(
    displayName: _stringOr(map, 'displayName', ''),
    nicknameCustomized: map['nicknameCustomized'] is bool
        ? map['nicknameCustomized']! as bool
        : false,
    avatarUrl: _stringOr(map, 'avatarUrl', ''),
    avatarAssetId: _stringOr(map, 'avatarAssetId', ''),
    maskedPhone: _stringOr(map, 'maskedPhone', ''),
    identityOrigin: _stringOr(map, 'identityOrigin', ''),
  );
}

Map<String, Object?> _object(Object? value, String label) {
  if (value is! Map) {
    throw FormatException('$label must be an object');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

String _stringOr(Map<String, Object?> map, String key, String fallback) {
  final value = map[key];
  if (value is String) return value.trim();
  return fallback;
}

int _intOr(Map<String, Object?> map, String key, int fallback) {
  final value = map[key];
  if (value is int) return value;
  if (value is num) return value.toInt();
  return fallback;
}
