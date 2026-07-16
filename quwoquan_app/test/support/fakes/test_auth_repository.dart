import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/one_tap_login_hint_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/owner_credential_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

/// Test-only AuthRepository double. Production and alpha composition must not
/// import this library; alpha owns a separate contract-fixture adapter.
class TestAuthRepository implements AuthRepository {
  static const ownerId = 'fixture_user_current';
  static const subAccountId = 'fixture_sub_current';

  @override
  Future<OtpSendResultData> sendOtp({
    required String phone,
    String? deviceId,
    String? platform,
    String? appVersion,
    String? sourceOperation,
  }) async {
    return OtpSendResultData(
      maskedPhone: phone.length > 7
          ? '${phone.substring(0, 3)}****${phone.substring(phone.length - 4)}'
          : phone,
      expiresInSeconds: 300,
      deliveryStatus: 'queued',
      requestId: 'test_otp_request',
      challengeId: 'test_otp_challenge',
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
  }) async => loginResult(identityOrigin: credentialType);

  @override
  Future<AuthLoginResultDto> loginOneTap({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) async => loginResult(identityOrigin: 'phone');

  @override
  Future<OneTapLoginHintDto> resolveOneTapLoginHint({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
  }) async {
    return OneTapLoginHintDto.fromMap(const <String, dynamic>{
      'state': 'registered',
      'maskedPhone': '180****3909',
      'registered': true,
      'expiresInSeconds': 60,
      'providerRequestId': 'test_hint',
    });
  }

  @override
  Future<AuthLoginResultDto> loginWechat({
    required String wechatCode,
    required String deviceId,
    required String platform,
  }) async => loginResult(identityOrigin: 'wechat');

  @override
  Future<AuthLoginResultDto> loginAlipay({
    required String alipayAuthCode,
    required String deviceId,
    required String platform,
  }) async => loginResult(identityOrigin: 'alipay');

  @override
  Future<AuthLoginResultDto> loginQq({
    required String qqAuthCode,
    required String deviceId,
    required String platform,
  }) async => loginResult(identityOrigin: 'qq');

  @override
  Future<AuthLoginResultDto> loginAnonymous({
    required String installId,
    required String deviceFingerprintHash,
    required String platform,
    required String appVersion,
  }) async => loginResult(identityOrigin: 'anonymous_device');

  @override
  Future<AuthLoginResultDto> refreshToken(String refreshToken) async {
    return loginResult(identityOrigin: 'phone');
  }

  @override
  Future<void> logout({String? refreshToken, String? deviceId}) async {}

  @override
  Future<void> bindCredential({
    required String credentialType,
    required String credentialKey,
    String? displayLabel,
  }) async {}

  @override
  Future<void> bindPhoneWithOtp({
    required String phone,
    required String otpCode,
    String? displayLabel,
  }) async {}

  @override
  Future<void> bindCarrierPhone({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? displayLabel,
  }) async {}

  @override
  Future<void> unbindCredential(String credentialType) async {}

  @override
  Future<List<OwnerCredentialRowDto>> listCredentials() async {
    return <OwnerCredentialRowDto>[
      OwnerCredentialRowDto.fromMap(const <String, dynamic>{
        'id': 'test_credential',
        'credentialType': 'phone',
        'displayLabel': '180****3909',
        'isActive': true,
        'boundAt': '2026-01-01T00:00:00Z',
      }),
    ];
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    return <PersonaManagementItemViewData>[
      PersonaManagementItemViewData.fromPersonaManagementItemWire(
        PersonaManagementItemWireDto(
          subAccountId: subAccountId,
          displayName: '测试用户',
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
        subAccountId: 'test_persona',
        displayName: displayName,
        isolationLevel: isolationLevel,
      ),
    );
  }

  @override
  Future<void> activatePersona(String subAccountId) async {}

  @override
  Future<void> deletePersona(String subAccountId) async {}

  AuthLoginResultDto loginResult({required String identityOrigin}) {
    return AuthLoginResultDto.fromMap(<String, dynamic>{
      'accessToken': 'test_access_token',
      'refreshToken': 'test_refresh_token',
      'ownerId': ownerId,
      'activeSub': const <String, dynamic>{'subAccountId': subAccountId},
      'subAccountCount': 1,
      'accountState': identityOrigin == 'anonymous_device'
          ? 'anonymous'
          : 'active',
      'identityOrigin': identityOrigin,
    });
  }
}
