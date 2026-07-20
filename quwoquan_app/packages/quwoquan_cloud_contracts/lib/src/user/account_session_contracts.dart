import '../operation_request_payload.dart';

/// AccountSession 聚合登录/刷新/登出命令的 pure contracts。
/// 真相源：contracts/metadata/user/account_session/{service,fields}.yaml。
/// 六路登录 bootstrap 无 bearer；refresh rotation 重放触发 lineage 吊销。

/// Alpha/test 对齐 USER.AUTH.token_expired 的强类型边界信号。
///
/// production Remote 由 runtime mapper 抛出携带 RuntimeFailure 的 CloudException。
final class AccountSessionTokenExpiredException implements Exception {
  const AccountSessionTokenExpiredException();
}

final class LoginWithPhoneCommand {
  LoginWithPhoneCommand({
    required String phone,
    required String otpCode,
    required String deviceId,
    required String platform,
    required String appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : phone = _required(phone, 'phone'),
       otpCode = _required(otpCode, 'otpCode'),
       deviceId = _required(deviceId, 'deviceId'),
       platform = _required(platform, 'platform'),
       appVersion = _required(appVersion, 'appVersion'),
       agreementVersion = _required(agreementVersion, 'agreementVersion'),
       privacyVersion = _required(privacyVersion, 'privacyVersion');

  final String phone;
  final String otpCode;
  final String deviceId;
  final String platform;
  final String appVersion;
  final String agreementVersion;
  final String privacyVersion;
}

final class LoginWithWechatCommand {
  LoginWithWechatCommand({
    required String wechatCode,
    required String deviceId,
    required String platform,
    this.appVersion,
  }) : wechatCode = _required(wechatCode, 'wechatCode'),
       deviceId = _required(deviceId, 'deviceId'),
       platform = _required(platform, 'platform');

  final String wechatCode;
  final String deviceId;
  final String platform;
  final String? appVersion;
}

final class LoginWithAlipayCommand {
  LoginWithAlipayCommand({
    required String alipayAuthCode,
    required String deviceId,
    required String platform,
    this.appVersion,
  }) : alipayAuthCode = _required(alipayAuthCode, 'alipayAuthCode'),
       deviceId = _required(deviceId, 'deviceId'),
       platform = _required(platform, 'platform');

  final String alipayAuthCode;
  final String deviceId;
  final String platform;
  final String? appVersion;
}

final class LoginWithQqCommand {
  LoginWithQqCommand({
    required String qqAuthCode,
    required String deviceId,
    required String platform,
    this.appVersion,
  }) : qqAuthCode = _required(qqAuthCode, 'qqAuthCode'),
       deviceId = _required(deviceId, 'deviceId'),
       platform = _required(platform, 'platform');

  final String qqAuthCode;
  final String deviceId;
  final String platform;
  final String? appVersion;
}

final class LoginOneTapCommand {
  LoginOneTapCommand({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    this.appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : vendor = _required(vendor, 'vendor'),
       carrierToken = _required(carrierToken, 'carrierToken'),
       deviceId = _required(deviceId, 'deviceId'),
       platform = _required(platform, 'platform'),
       agreementVersion = _required(agreementVersion, 'agreementVersion'),
       privacyVersion = _required(privacyVersion, 'privacyVersion');

  final String vendor;
  final String carrierToken;
  final String deviceId;
  final String platform;
  final String? appVersion;
  final String agreementVersion;
  final String privacyVersion;
}

final class LoginAnonymousCommand {
  LoginAnonymousCommand({
    required String installId,
    required String deviceFingerprintHash,
    required String platform,
    required String appVersion,
  }) : installId = _required(installId, 'installId'),
       deviceFingerprintHash = _required(
         deviceFingerprintHash,
         'deviceFingerprintHash',
       ),
       platform = _required(platform, 'platform'),
       appVersion = _required(appVersion, 'appVersion');

  final String installId;
  final String deviceFingerprintHash;
  final String platform;
  final String appVersion;
}

final class RefreshTokenCommand {
  RefreshTokenCommand({required String refreshToken})
    : refreshToken = _required(refreshToken, 'refreshToken');

  final String refreshToken;
}

final class LogoutCommand {
  LogoutCommand({this.refreshToken, this.deviceId});

  final String? refreshToken;
  final String? deviceId;
}

/// 登录响应中的激活分身摘要（wire: activeSub envelope）。
final class ActivePersonaEnvelope {
  const ActivePersonaEnvelope({required this.subAccountId});

  final String subAccountId;
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
    required this.subAccountCount,
    required this.sessionRememberTtlSeconds,
    this.activeSub,
    this.accountHint,
  });

  final String accessToken;
  final String refreshToken;
  final String ownerId;
  final String accountState;
  final String identityOrigin;
  final int logicalShard;
  final String anonymousRetentionPolicy;
  final int subAccountCount;

  /// 快速登录有效期（秒）；0 表示云端未下发，端侧用默认值兜底。
  final int sessionRememberTtlSeconds;
  final ActivePersonaEnvelope? activeSub;
  final AccountHintSnapshot? accountHint;
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

  Future<AuthSessionGrant> loginWithWechat(LoginWithWechatCommand command);

  Future<AuthSessionGrant> loginWithAlipay(LoginWithAlipayCommand command);

  Future<AuthSessionGrant> loginWithQq(LoginWithQqCommand command);

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

CloudOperationRequestPayload encodeLoginWithPhoneCommand(
  LoginWithPhoneCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'phone': command.phone,
    'otpCode': command.otpCode,
    'deviceId': command.deviceId,
    'platform': command.platform,
    'appVersion': command.appVersion,
    'agreementVersion': command.agreementVersion,
    'privacyVersion': command.privacyVersion,
  },
);

CloudOperationRequestPayload encodeLoginWithWechatCommand(
  LoginWithWechatCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'wechatCode': command.wechatCode,
    'deviceId': command.deviceId,
    'platform': command.platform,
    if (command.appVersion != null) 'appVersion': command.appVersion,
  },
);

CloudOperationRequestPayload encodeLoginWithAlipayCommand(
  LoginWithAlipayCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'alipayAuthCode': command.alipayAuthCode,
    'deviceId': command.deviceId,
    'platform': command.platform,
    if (command.appVersion != null) 'appVersion': command.appVersion,
  },
);

CloudOperationRequestPayload encodeLoginWithQqCommand(
  LoginWithQqCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'qqAuthCode': command.qqAuthCode,
    'deviceId': command.deviceId,
    'platform': command.platform,
    if (command.appVersion != null) 'appVersion': command.appVersion,
  },
);

CloudOperationRequestPayload encodeLoginOneTapCommand(
  LoginOneTapCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'vendor': command.vendor,
    'carrierToken': command.carrierToken,
    'deviceId': command.deviceId,
    'platform': command.platform,
    if (command.appVersion != null) 'appVersion': command.appVersion,
    'agreementVersion': command.agreementVersion,
    'privacyVersion': command.privacyVersion,
  },
);

CloudOperationRequestPayload encodeLoginAnonymousCommand(
  LoginAnonymousCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'installId': command.installId,
    'deviceFingerprintHash': command.deviceFingerprintHash,
    'platform': command.platform,
    'appVersion': command.appVersion,
  },
);

CloudOperationRequestPayload encodeRefreshTokenCommand(
  RefreshTokenCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{'refreshToken': command.refreshToken},
);

CloudOperationRequestPayload encodeLogoutCommand(LogoutCommand command) =>
    CloudOperationRequestPayload(
      body: <String, Object?>{
        if (command.refreshToken != null) 'refreshToken': command.refreshToken,
        if (command.deviceId != null) 'deviceId': command.deviceId,
      },
    );

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
    subAccountCount: _intOr(map, 'subAccountCount', 0),
    sessionRememberTtlSeconds: _intOr(map, 'sessionRememberTtlSeconds', 0),
    activeSub: _activePersona(map['activeSub']),
    accountHint: _accountHint(map['accountHint']),
  );
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
  final map = _object(value, 'activeSub');
  final subAccountId = map['subAccountId'];
  if (subAccountId is! String || subAccountId.trim().isEmpty) {
    return null;
  }
  return ActivePersonaEnvelope(subAccountId: subAccountId.trim());
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

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}
