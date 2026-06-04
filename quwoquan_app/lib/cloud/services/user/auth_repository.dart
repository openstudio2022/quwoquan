import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/owner_credential_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

/// 一次发码的结果（脱敏号码 + 有效期；调试码仅非生产返回）。
class OtpSendResultData {
  const OtpSendResultData({
    required this.maskedPhone,
    required this.expiresInSeconds,
    required this.deliveryStatus,
    this.requestId,
    this.challengeId,
    this.debugCode,
  });

  factory OtpSendResultData.fromMap(Map<String, dynamic> map) {
    return OtpSendResultData(
      maskedPhone: (map['maskedPhone'] as String?) ?? '',
      expiresInSeconds: (map['expiresInSeconds'] as num?)?.toInt() ?? 0,
      deliveryStatus: (map['deliveryStatus'] as String?) ?? 'queued',
      requestId: map['requestId'] as String?,
      challengeId: map['challengeId'] as String?,
      debugCode: map['debugCode'] as String?,
    );
  }

  final String maskedPhone;
  final int expiresInSeconds;
  final String deliveryStatus;
  final String? requestId;
  final String? challengeId;
  final String? debugCode;

  bool get isDebugCodeVisible =>
      debugCode != null &&
      debugCode!.isNotEmpty &&
      (deliveryStatus == 'debug' || deliveryStatus == 'pass_through');
}

/// AuthRepository: 登录、凭证管理、分身管理。
abstract class AuthRepository {
  /// 下发手机号验证码（发码冷却 + 每小时配额）。
  Future<OtpSendResultData> sendOtp({required String phone});

  /// 手机号/微信/Apple 登录，首次自动创建用户与默认分身。
  /// 手机号登录需附带 [otpCode]。
  Future<AuthLoginResultDto> login({
    required String credentialType,
    required String credentialKey,
    String? otpCode,
    String? displayLabel,
  });

  /// 运营商一键登录。App 只上传授权 token，真实手机号由服务端置换。
  Future<AuthLoginResultDto> loginOneTap({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    required String agreementVersion,
    required String privacyVersion,
  });

  /// 基于安装标识的匿名/游客恢复。
  Future<AuthLoginResultDto> loginAnonymous({
    required String installId,
    required String deviceFingerprintHash,
    required String platform,
    required String appVersion,
  });

  Future<AuthLoginResultDto> refreshToken(String refreshToken);

  Future<void> logout({String? refreshToken, String? deviceId});

  /// 绑定新凭证到当前账号。
  Future<void> bindCredential({
    required String credentialType,
    required String credentialKey,
    String? displayLabel,
  });

  /// 解绑凭证（最后一个凭证禁止解绑）。
  Future<void> unbindCredential(String credentialType);

  /// 列出当前账号绑定的所有凭证。
  Future<List<OwnerCredentialRowDto>> listCredentials();

  /// 列出当前账号的所有分身。
  Future<List<PersonaManagementItemViewData>> listPersonas();

  /// 创建新分身。
  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String isolationLevel = 'open',
  });

  /// 激活指定分身（自动停用其他）。
  Future<void> activatePersona(String subAccountId);

  /// 删除分身（最后一个禁止删除）。
  Future<void> deletePersona(String subAccountId);
}

class MockAuthRepository implements AuthRepository {
  @override
  Future<OtpSendResultData> sendOtp({required String phone}) async {
    await Future.delayed(const Duration(milliseconds: 200));
    return OtpSendResultData(
      maskedPhone: _maskPhone(phone),
      expiresInSeconds: 300,
      deliveryStatus: 'debug',
      requestId: 'mock_otp_request',
      challengeId: 'mock_otp_challenge',
      debugCode: '000000',
    );
  }

  static String _maskPhone(String phone) {
    final trimmed = phone.trim();
    if (trimmed.length <= 7) {
      return trimmed;
    }
    return '${trimmed.substring(0, 3)}****${trimmed.substring(trimmed.length - 4)}';
  }

  @override
  Future<AuthLoginResultDto> login({
    required String credentialType,
    required String credentialKey,
    String? otpCode,
    String? displayLabel,
  }) async {
    await Future.delayed(const Duration(milliseconds: 300));
    return AuthLoginResultDto.fromMap(<String, dynamic>{
      'accessToken': 'mock_token_${credentialKey.hashCode}',
      'refreshToken': 'mock_refresh',
      'ownerId': 'mock_owner_id',
      'activeSub': <String, dynamic>{'subAccountId': 'mock_sub_id'},
      'subAccountCount': 1,
    });
  }

  @override
  Future<AuthLoginResultDto> loginOneTap({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    required String agreementVersion,
    required String privacyVersion,
  }) async {
    await Future.delayed(const Duration(milliseconds: 300));
    return AuthLoginResultDto.fromMap(<String, dynamic>{
      'accessToken': 'mock_one_tap_token_${carrierToken.hashCode}',
      'refreshToken': 'mock_one_tap_refresh',
      'ownerId': 'mock_owner_id',
      'activeSub': <String, dynamic>{'subAccountId': 'mock_sub_id'},
      'subAccountCount': 1,
      'accountState': 'active',
      'identityOrigin': 'phone',
    });
  }

  @override
  Future<AuthLoginResultDto> loginAnonymous({
    required String installId,
    required String deviceFingerprintHash,
    required String platform,
    required String appVersion,
  }) async {
    await Future.delayed(const Duration(milliseconds: 200));
    return AuthLoginResultDto.fromMap(<String, dynamic>{
      'accessToken': 'mock_guest_token_${installId.hashCode}',
      'refreshToken': 'mock_guest_refresh',
      'ownerId': 'mock_guest_owner_id',
      'activeSub': <String, dynamic>{'subAccountId': 'mock_guest_sub_id'},
      'subAccountCount': 1,
      'accountState': 'anonymous',
      'identityOrigin': 'anonymous_device',
    });
  }

  @override
  Future<AuthLoginResultDto> refreshToken(String refreshToken) async {
    return AuthLoginResultDto.fromMap(<String, dynamic>{
      'accessToken': 'mock_refreshed_token_${refreshToken.hashCode}',
      'refreshToken': 'mock_refreshed_refresh',
      'ownerId': 'mock_owner_id',
      'activeSub': <String, dynamic>{'subAccountId': 'mock_sub_id'},
      'subAccountCount': 1,
      'accountState': 'active',
      'identityOrigin': 'phone',
    });
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
  Future<void> unbindCredential(String credentialType) async {}

  @override
  Future<List<OwnerCredentialRowDto>> listCredentials() async {
    return [
      OwnerCredentialRowDto.fromMap(<String, dynamic>{
        'id': 'mock_cred_1',
        'credentialType': 'phone',
        'displayLabel': '138****0001',
        'isActive': true,
        'boundAt': DateTime.now().toIso8601String(),
      }),
    ];
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    return [
      PersonaManagementItemViewData.fromMap(<String, dynamic>{
        'id': 'mock_persona_1',
        'subAccountId': 'mock_persona_1',
        'displayName': '默认分身',
        'isolationLevel': 'open',
        'isPrimary': true,
        'isActive': true,
      }),
    ];
  }

  @override
  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String isolationLevel = 'open',
  }) async {
    return PersonaManagementItemViewData.fromMap(<String, dynamic>{
      'id': 'mock_persona_new',
      'subAccountId': 'mock_persona_new',
      'displayName': displayName,
      'isolationLevel': isolationLevel,
      'isPrimary': false,
      'isActive': false,
    });
  }

  @override
  Future<void> activatePersona(String subAccountId) async {}

  @override
  Future<void> deletePersona(String subAccountId) async {}
}

class RemoteAuthRepository implements AuthRepository {
  RemoteAuthRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _client = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  String _loginPathForCredentialType(String credentialType) {
    switch (credentialType.trim().toLowerCase()) {
      case 'phone':
        return UserApiMetadata.loginWithPhonePath;
      case 'wechat':
        return UserApiMetadata.loginWithWechatPath;
      case 'apple':
        return UserApiMetadata.loginWithApplePath;
      default:
        throw ArgumentError.value(
          credentialType,
          'credentialType',
          'Unsupported credential type',
        );
    }
  }

  String _loginPageIdForCredentialType(String credentialType) {
    switch (credentialType.trim().toLowerCase()) {
      case 'phone':
        return UserRequestPageIds.loginWithPhone;
      case 'wechat':
        return UserRequestPageIds.loginWithWechat;
      case 'apple':
        return UserRequestPageIds.loginWithApple;
      default:
        throw ArgumentError.value(
          credentialType,
          'credentialType',
          'Unsupported credential type',
        );
    }
  }

  AuthLoginResultDto _authResultFromResponse(Object? resp, String context) {
    return AuthLoginResultDto.fromMap(
      CloudResponseDecoder.asObject(resp, context: context),
    );
  }

  @override
  Future<OtpSendResultData> sendOtp({required String phone}) async {
    final context = UserRequestPageIds.sendOtp;
    final resp = await _client.postJson(
      _uri(UserApiMetadata.sendOtpPath),
      headers: CloudRequestHeaders.forPage(context),
      body: <String, dynamic>{'phone': phone},
    );
    return OtpSendResultData.fromMap(
      CloudResponseDecoder.asObject(resp, context: context),
    );
  }

  @override
  Future<AuthLoginResultDto> login({
    required String credentialType,
    required String credentialKey,
    String? otpCode,
    String? displayLabel,
  }) async {
    final isPhone = credentialType.trim().toLowerCase() == 'phone';
    final body = <String, dynamic>{
      'credentialType': credentialType,
      'credentialKey': credentialKey,
      if (isPhone) 'phone': credentialKey,
      if (otpCode != null && otpCode.isNotEmpty) 'otpCode': otpCode,
    };
    if (displayLabel != null) {
      body['displayLabel'] = displayLabel;
    }
    final resp = await _client.postJson(
      _uri(_loginPathForCredentialType(credentialType)),
      headers: CloudRequestHeaders.forPage(
        _loginPageIdForCredentialType(credentialType),
      ),
      body: body,
    );
    return _authResultFromResponse(
      resp,
      _loginPageIdForCredentialType(credentialType),
    );
  }

  @override
  Future<AuthLoginResultDto> loginOneTap({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    required String agreementVersion,
    required String privacyVersion,
  }) async {
    final context = UserRequestPageIds.loginOneTap;
    final resp = await _client.postJson(
      _uri(UserApiMetadata.loginOneTapPath),
      headers: CloudRequestHeaders.forPage(context),
      body: <String, dynamic>{
        'vendor': vendor,
        'carrierToken': carrierToken,
        'deviceId': deviceId,
        'platform': platform,
        'agreementVersion': agreementVersion,
        'privacyVersion': privacyVersion,
      },
    );
    return _authResultFromResponse(resp, context);
  }

  @override
  Future<AuthLoginResultDto> loginAnonymous({
    required String installId,
    required String deviceFingerprintHash,
    required String platform,
    required String appVersion,
  }) async {
    final context = UserRequestPageIds.loginAnonymous;
    final resp = await _client.postJson(
      _uri(UserApiMetadata.loginAnonymousPath),
      headers: CloudRequestHeaders.forPage(context),
      body: <String, dynamic>{
        'installId': installId,
        'deviceFingerprintHash': deviceFingerprintHash,
        'platform': platform,
        'appVersion': appVersion,
      },
    );
    return _authResultFromResponse(resp, context);
  }

  @override
  Future<AuthLoginResultDto> refreshToken(String refreshToken) async {
    final context = UserRequestPageIds.refreshToken;
    final resp = await _client.postJson(
      _uri(UserApiMetadata.refreshTokenPath),
      headers: CloudRequestHeaders.forPage(context),
      body: <String, dynamic>{'refreshToken': refreshToken},
    );
    return _authResultFromResponse(resp, context);
  }

  @override
  Future<void> logout({String? refreshToken, String? deviceId}) async {
    await _client.postJson(
      _uri(UserApiMetadata.logoutPath),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.logout),
      body: <String, dynamic>{
        if (refreshToken != null && refreshToken.isNotEmpty)
          'refreshToken': refreshToken,
        if (deviceId != null && deviceId.isNotEmpty) 'deviceId': deviceId,
      },
    );
  }

  @override
  Future<void> bindCredential({
    required String credentialType,
    required String credentialKey,
    String? displayLabel,
  }) async {
    final body = <String, dynamic>{
      'credentialType': credentialType,
      'credentialKey': credentialKey,
    };
    if (displayLabel != null) {
      body['displayLabel'] = displayLabel;
    }
    await _client.postJson(
      _uri(UserApiMetadata.bindCredentialPath),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.bindCredential),
      body: body,
    );
  }

  @override
  Future<void> unbindCredential(String credentialType) async {
    await _client.deleteJson(
      _uri(
        UserApiMetadata.unbindCredentialPath(credentialType: credentialType),
      ),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.unbindCredential),
    );
  }

  @override
  Future<List<OwnerCredentialRowDto>> listCredentials() async {
    final resp = await _client.getJson(
      _uri(UserApiMetadata.listCredentialsPath),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listCredentials),
    );
    final data = CloudResponseDecoder.asObject(
      resp,
      context: UserRequestPageIds.listCredentials,
    );
    return CloudResponseDecoder.mapList(
      data,
      'credentials',
    ).map(OwnerCredentialRowDto.fromMap).toList(growable: false);
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    final resp = await _client.getJson(
      _uri(UserApiMetadata.listPersonasPath),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listPersonas),
    );
    final data = CloudResponseDecoder.asObject(
      resp,
      context: UserRequestPageIds.listPersonas,
    );
    return CloudResponseDecoder.mapList(
      data,
      'items',
    ).map(PersonaManagementItemViewData.fromMap).toList(growable: false);
  }

  @override
  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String isolationLevel = 'open',
  }) async {
    final resp = await _client.postJson(
      _uri(UserApiMetadata.createPersonaPath),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.createPersona),
      body: {'displayName': displayName, 'isolationLevel': isolationLevel},
    );
    return PersonaManagementItemViewData.fromMap(
      CloudResponseDecoder.asObject(
        resp,
        context: UserRequestPageIds.createPersona,
      ),
    );
  }

  @override
  Future<void> activatePersona(String subAccountId) async {
    await _client.postJson(
      _uri(UserApiMetadata.activatePersonaPath(subAccountId: subAccountId)),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.activatePersona),
      body: {},
    );
  }

  @override
  Future<void> deletePersona(String subAccountId) async {
    await _client.deleteJson(
      _uri(UserApiMetadata.deleteEmptyPersonaPath(subAccountId: subAccountId)),
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.deleteEmptyPersona,
      ),
    );
  }
}
