import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/one_tap_login_hint_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/owner_credential_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

part 'auth_repository_remote.dart';

/// 一次发码的结果（脱敏号码 + 有效期）；验证码不进入端云 response。
class OtpSendResultData {
  const OtpSendResultData({
    required this.maskedPhone,
    required this.expiresInSeconds,
    required this.deliveryStatus,
    this.retryAfterSeconds = 0,
    this.requestId,
    this.challengeId,
  });

  factory OtpSendResultData.fromMap(Map<String, dynamic> map) {
    return OtpSendResultData(
      maskedPhone: (map['maskedPhone'] as String?) ?? '',
      expiresInSeconds: (map['expiresInSeconds'] as num?)?.toInt() ?? 0,
      deliveryStatus: (map['deliveryStatus'] as String?) ?? 'queued',
      retryAfterSeconds: (map['retryAfterSeconds'] as num?)?.toInt() ?? 0,
      requestId: map['requestId'] as String?,
      challengeId: map['challengeId'] as String?,
    );
  }

  final String maskedPhone;
  final int expiresInSeconds;
  final String deliveryStatus;
  final int retryAfterSeconds;
  final String? requestId;
  final String? challengeId;
}

/// 无 bearer 的公开匿名设备引导合同。
///
/// 该操作是 metadata 定义的 public bootstrap，必须在会话初始化之前可调用，
/// 因而不能依赖会话绑定的 HTTP client。
abstract interface class AnonymousLoginGateway {
  Future<AuthLoginResultDto> loginAnonymous({
    required String installId,
    required String deviceFingerprintHash,
    required String platform,
    required String appVersion,
  });
}

/// 登录、凭证与分身能力合同。生产组合根只装配 [RemoteAuthRepository]。
abstract class AuthRepository implements AnonymousLoginGateway {
  Future<OtpSendResultData> sendOtp({
    required String phone,
    String? deviceId,
    String? platform,
    String? appVersion,
    String? sourceOperation,
  });

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
  });

  Future<AuthLoginResultDto> loginOneTap({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  });

  Future<OneTapLoginHintDto> resolveOneTapLoginHint({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
  });

  Future<AuthLoginResultDto> loginWechat({
    required String wechatCode,
    required String deviceId,
    required String platform,
  });

  Future<AuthLoginResultDto> loginAlipay({
    required String alipayAuthCode,
    required String deviceId,
    required String platform,
  });

  Future<AuthLoginResultDto> loginQq({
    required String qqAuthCode,
    required String deviceId,
    required String platform,
  });

  Future<AuthLoginResultDto> refreshToken(String refreshToken);

  Future<void> logout({String? refreshToken, String? deviceId});

  Future<void> bindCredential({
    required String credentialType,
    required String credentialKey,
    String? displayLabel,
  });

  Future<void> bindPhoneWithOtp({
    required String phone,
    required String otpCode,
    String? displayLabel,
  });

  Future<void> bindCarrierPhone({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? displayLabel,
  });

  Future<void> unbindCredential(String credentialType);

  Future<List<OwnerCredentialRowDto>> listCredentials();

  Future<List<PersonaManagementItemViewData>> listPersonas();

  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String isolationLevel = 'open',
  });

  Future<void> activatePersona(String subAccountId);

  Future<void> deletePersona(String subAccountId);
}
