import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/one_tap_login_hint_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/owner_credential_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/social_authorization_repository.dart';

/// Alpha contract-fixture adapter. This library is owned by the independent
/// runner and is absent from production dependency resolution.
final class AlphaAuthRepository implements AuthRepository {
  AlphaAuthRepository({DateTime Function()? now}) : _now = now ?? DateTime.now;

  static const _ownerId = 'fixture_user_current';
  static const _subAccountId = 'fixture_sub_current';
  static const _fixedOtpCode = '123456';
  static const _otpTtl = Duration(minutes: 5);
  static const _otpCooldown = Duration(seconds: 60);

  final DateTime Function() _now;
  final Map<String, _AlphaOtpChallenge> _otpChallenges =
      <String, _AlphaOtpChallenge>{};
  int _challengeSerial = 0;

  final List<OwnerCredentialRowDto> _credentials = <OwnerCredentialRowDto>[
    OwnerCredentialRowDto.fromMap(<String, dynamic>{
      'id': 'alpha_credential_phone',
      'credentialType': 'phone',
      'displayLabel': '180****3909',
      'isActive': true,
      'boundAt': '2026-01-01T00:00:00Z',
    }),
  ];

  @override
  Future<OtpSendResultData> sendOtp({
    required String phone,
    String? deviceId,
    String? platform,
    String? appVersion,
    String? sourceOperation,
  }) async {
    final normalizedPhone = phone.trim();
    if (!_isPhone(normalizedPhone)) {
      throw _alphaAuthError(UserErrorCode.invalidArgument);
    }
    final now = _now();
    final existing = _otpChallenges[normalizedPhone];
    if (existing != null && now.difference(existing.sentAt) < _otpCooldown) {
      throw _alphaAuthError(UserErrorCode.otpRateLimited);
    }
    final challengeId = 'alpha_otp_${++_challengeSerial}';
    _otpChallenges[normalizedPhone] = _AlphaOtpChallenge(
      challengeId: challengeId,
      codeDigest: _otpDigest(challengeId, _fixedOtpCode),
      sentAt: now,
      expiresAt: now.add(_otpTtl),
    );
    return OtpSendResultData(
      maskedPhone: _maskPhone(normalizedPhone),
      expiresInSeconds: _otpTtl.inSeconds,
      deliveryStatus: 'delivered',
      retryAfterSeconds: _otpCooldown.inSeconds,
      requestId: 'alpha_otp_request_$_challengeSerial',
      challengeId: challengeId,
    );
  }

  @override
  Future<AuthLoginResultDto> login({
    required String credentialType,
    required String credentialKey,
    String? otpCode,
    String? displayLabel,
    String? deviceId,
    String? platform,
    String? appVersion,
    String? agreementVersion,
    String? privacyVersion,
  }) async {
    if (credentialType.trim().toLowerCase() == 'phone') {
      if ((agreementVersion ?? '').trim().isEmpty ||
          (privacyVersion ?? '').trim().isEmpty) {
        throw _alphaAuthError(UserErrorCode.consentRequired);
      }
      _consumeOtp(credentialKey, otpCode ?? '');
    }
    return _loginResult(identityOrigin: credentialType);
  }

  @override
  Future<AuthLoginResultDto> loginOneTap({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) async => _loginResult(identityOrigin: 'phone', includeHint: true);

  @override
  Future<OneTapLoginHintDto> resolveOneTapLoginHint({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
  }) async {
    return OneTapLoginHintDto.fromMap(<String, dynamic>{
      'state': 'registered',
      'maskedPhone': '180****3909',
      'registered': true,
      'accountHint': const <String, dynamic>{
        'displayName': '独立 Alpha 用户',
        'avatarUrl': '',
        'maskedPhone': '180****3909',
        'identityOrigin': 'phone',
        'nicknameCustomized': true,
      },
      'expiresInSeconds': 60,
      'providerRequestId': 'alpha_one_tap_hint',
    });
  }

  @override
  Future<AuthLoginResultDto> loginWechat({
    required String wechatCode,
    required String deviceId,
    required String platform,
  }) async => _loginResult(identityOrigin: 'wechat');

  @override
  Future<AuthLoginResultDto> loginAlipay({
    required String alipayAuthCode,
    required String deviceId,
    required String platform,
  }) async => _loginResult(identityOrigin: 'alipay');

  @override
  Future<AuthLoginResultDto> loginQq({
    required String qqAuthCode,
    required String deviceId,
    required String platform,
  }) async => _loginResult(identityOrigin: 'qq');

  @override
  Future<AuthLoginResultDto> loginAnonymous({
    required String installId,
    required String deviceFingerprintHash,
    required String platform,
    required String appVersion,
  }) async => _loginResult(identityOrigin: 'anonymous_device');

  @override
  Future<AuthLoginResultDto> refreshToken(String refreshToken) async {
    return _loginResult(identityOrigin: 'phone');
  }

  @override
  Future<void> logout({String? refreshToken, String? deviceId}) async {}

  @override
  Future<void> bindCredential({
    required String credentialType,
    required String credentialKey,
    String? displayLabel,
  }) async {
    _upsertCredential(
      credentialType,
      displayLabel ?? _maskPhone(credentialKey),
    );
  }

  @override
  Future<void> bindPhoneWithOtp({
    required String phone,
    required String otpCode,
    String? displayLabel,
  }) async {
    _consumeOtp(phone, otpCode);
    _upsertCredential('phone', displayLabel ?? _maskPhone(phone));
  }

  @override
  Future<void> bindCarrierPhone({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? displayLabel,
  }) async {
    _upsertCredential('carrier_phone', displayLabel ?? '180****3909');
  }

  @override
  Future<void> unbindCredential(String credentialType) async {
    if (_credentials.length <= 1) {
      throw StateError('alpha fixture cannot remove the last credential');
    }
    _credentials.removeWhere((row) => row.credentialType == credentialType);
  }

  @override
  Future<List<OwnerCredentialRowDto>> listCredentials() async {
    return List<OwnerCredentialRowDto>.unmodifiable(_credentials);
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    return <PersonaManagementItemViewData>[
      PersonaManagementItemViewData.fromPersonaManagementItemWire(
        PersonaManagementItemWireDto(
          subAccountId: _subAccountId,
          displayName: '独立 Alpha 用户',
          isolationLevel: 'open',
          isPrimary: true,
          isActive: true,
        ),
      ),
    ];
  }

  @override
  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String isolationLevel = 'open',
  }) async {
    return PersonaManagementItemViewData.fromPersonaManagementItemWire(
      PersonaManagementItemWireDto(
        subAccountId: 'alpha_persona_secondary',
        displayName: displayName,
        isolationLevel: isolationLevel,
      ),
    );
  }

  @override
  Future<void> activatePersona(String subAccountId) async {}

  @override
  Future<void> deletePersona(String subAccountId) async {}

  AuthLoginResultDto _loginResult({
    required String identityOrigin,
    bool includeHint = false,
  }) {
    return AuthLoginResultDto.fromMap(<String, dynamic>{
      'accessToken': 'alpha_fixture_access_token',
      'refreshToken': 'alpha_fixture_refresh_token',
      'ownerId': _ownerId,
      'activeSub': const <String, dynamic>{'subAccountId': _subAccountId},
      'subAccountCount': 1,
      'accountState': identityOrigin == 'anonymous_device'
          ? 'anonymous'
          : 'active',
      'identityOrigin': identityOrigin,
      if (includeHint)
        'accountHint': const <String, dynamic>{
          'displayName': '独立 Alpha 用户',
          'avatarUrl': '',
          'maskedPhone': '180****3909',
          'identityOrigin': 'phone',
          'nicknameCustomized': true,
        },
    });
  }

  void _upsertCredential(String credentialType, String displayLabel) {
    _credentials.removeWhere((row) => row.credentialType == credentialType);
    _credentials.add(
      OwnerCredentialRowDto.fromMap(<String, dynamic>{
        'id': 'alpha_credential_$credentialType',
        'credentialType': credentialType,
        'displayLabel': displayLabel,
        'isActive': true,
        'boundAt': '2026-01-01T00:00:00Z',
      }),
    );
  }

  static String _maskPhone(String phone) {
    final value = phone.trim();
    if (value.length <= 7) return value;
    return '${value.substring(0, 3)}****${value.substring(value.length - 4)}';
  }

  void _consumeOtp(String rawPhone, String rawCode) {
    final phone = rawPhone.trim();
    final code = rawCode.trim();
    final challenge = _otpChallenges[phone];
    if (challenge == null ||
        challenge.consumed ||
        !_now().isBefore(challenge.expiresAt)) {
      throw _alphaAuthError(UserErrorCode.otpExpired);
    }
    if (_otpDigest(challenge.challengeId, code) != challenge.codeDigest) {
      challenge.failureCount += 1;
      if (challenge.failureCount >= 5) {
        throw _alphaAuthError(UserErrorCode.loginLocked);
      }
      throw _alphaAuthError(UserErrorCode.otpMismatch);
    }
    challenge.consumed = true;
  }

  static bool _isPhone(String phone) => RegExp(r'^1\d{10}$').hasMatch(phone);

  static String _otpDigest(String challengeId, String code) {
    return sha256.convert(utf8.encode('$challengeId:$code')).toString();
  }

  static CloudException _alphaAuthError(UserErrorCode code) {
    return CloudErrorMapper.fromStatusCode(
      code.httpStatus,
      body: jsonEncode(<String, String>{
        'code': code.code,
        'userMessage': code.defaultMessage,
      }),
    );
  }
}

final class _AlphaOtpChallenge {
  _AlphaOtpChallenge({
    required this.challengeId,
    required this.codeDigest,
    required this.sentAt,
    required this.expiresAt,
  });

  final String challengeId;
  final String codeDigest;
  final DateTime sentAt;
  final DateTime expiresAt;
  int failureCount = 0;
  bool consumed = false;
}

final class AlphaSocialAuthorizationRepository
    implements SocialAuthorizationRepository {
  const AlphaSocialAuthorizationRepository();

  @override
  Future<SocialAuthorizationRequest> createAlipayAuthorizationRequest() async {
    return SocialAuthorizationRequest(
      payload: 'alpha-fixture-alipay-authorization',
      expiresAt: DateTime.now().toUtc().add(const Duration(minutes: 5)),
    );
  }
}
