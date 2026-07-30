import '../operation_request_payload.dart';
part '../generated/requests/user/authentication_challenge_contracts.requests.g.dart';

/// 一次发码的结果（脱敏号码 + 有效期）；验证码明文不进入端云 response。
final class OtpChallengeIssueResult {
  const OtpChallengeIssueResult({
    required this.maskedPhone,
    required this.expiresInSeconds,
    required this.deliveryStatus,
    required this.retryAfterSeconds,
    this.requestId,
    this.challengeId,
  });

  final String maskedPhone;
  final int expiresInSeconds;
  final String deliveryStatus;
  final int retryAfterSeconds;
  final String? requestId;
  final String? challengeId;
}

final class AlipayAuthorizationGrant {
  const AlipayAuthorizationGrant({
    required this.authorizationPayload,
    required this.expiresAt,
  });

  final String authorizationPayload;
  final String expiresAt;
}

final class OneTapLoginHint {
  const OneTapLoginHint({
    required this.state,
    required this.maskedPhone,
    required this.registered,
    required this.expiresInSeconds,
    this.accountHint,
    this.providerRequestId,
  });

  final String state;
  final String maskedPhone;
  final bool registered;
  final int expiresInSeconds;
  final OneTapAccountHint? accountHint;
  final String? providerRequestId;
}

final class OneTapAccountHint {
  const OneTapAccountHint({
    required this.displayName,
    required this.avatarUrl,
    required this.maskedPhone,
    required this.identityOrigin,
  });

  final String displayName;
  final String avatarUrl;
  final String maskedPhone;
  final String identityOrigin;
}

abstract interface class AuthenticationChallengeCommandWriter {
  Future<OtpChallengeIssueResult> sendOtp(SendOtpCommand command);

  Future<AlipayAuthorizationGrant> createAlipayAuthorizationRequest(
    CreateAlipayAuthorizationRequestCommand command,
  );

  Future<OneTapLoginHint> resolveOneTapLoginHint(
    ResolveOneTapLoginHintCommand command,
  );
}

OtpChallengeIssueResult decodeOtpChallengeIssueResult(Object? value) {
  final map = _object(value, 'OtpChallengeIssueResult');
  return OtpChallengeIssueResult(
    maskedPhone: _stringOr(map, 'maskedPhone', ''),
    expiresInSeconds: _intOr(map, 'expiresInSeconds', 0),
    deliveryStatus: _stringOr(map, 'deliveryStatus', 'queued'),
    retryAfterSeconds: _intOr(map, 'retryAfterSeconds', 0),
    requestId: _optionalString(map, 'requestId'),
    challengeId: _optionalString(map, 'challengeId'),
  );
}

AlipayAuthorizationGrant decodeAlipayAuthorizationGrant(Object? value) {
  final map = _object(value, 'AlipayAuthorizationGrant');
  return AlipayAuthorizationGrant(
    authorizationPayload: _string(map, 'authorizationPayload'),
    expiresAt: _stringOr(map, 'expiresAt', ''),
  );
}

OneTapLoginHint decodeOneTapLoginHint(Object? value) {
  final map = _object(value, 'OneTapLoginHint');
  return OneTapLoginHint(
    state: _stringOr(map, 'state', ''),
    maskedPhone: _stringOr(map, 'maskedPhone', ''),
    registered: map['registered'] is bool ? map['registered']! as bool : false,
    expiresInSeconds: _intOr(map, 'expiresInSeconds', 0),
    accountHint: _oneTapAccountHint(map['accountHint']),
    providerRequestId: _optionalString(map, 'providerRequestId'),
  );
}

OneTapAccountHint? _oneTapAccountHint(Object? value) {
  if (value == null) return null;
  final map = _object(value, 'accountHint');
  return OneTapAccountHint(
    displayName: _stringOr(map, 'displayName', ''),
    avatarUrl: _stringOr(map, 'avatarUrl', ''),
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

String? _optionalString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is String && value.trim().isNotEmpty) return value.trim();
  return null;
}

int _intOr(Map<String, Object?> map, String key, int fallback) {
  final value = map[key];
  if (value is int) return value;
  if (value is num) return value.toInt();
  return fallback;
}
