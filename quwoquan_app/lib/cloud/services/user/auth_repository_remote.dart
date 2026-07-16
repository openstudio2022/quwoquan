part of 'auth_repository.dart';

class RemoteAuthRepository implements AuthRepository {
  RemoteAuthRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _client = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Map<String, String> _headersForOperation(String operationId) {
    final pageId = UserRequestPageIds.operationToPageId[operationId];
    if (pageId == null || pageId.isEmpty) {
      throw StateError('Missing generated request page id for $operationId');
    }
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: pageId,
      operationId: operationId,
      clientPageId: pageId,
    );
  }

  String _loginPathForCredentialType(String credentialType) {
    switch (credentialType.trim().toLowerCase()) {
      case 'phone':
        return UserApiMetadata.loginWithPhonePath;
      case 'wechat':
        return UserApiMetadata.loginWithWechatPath;
      case 'alipay':
        return UserApiMetadata.loginWithAlipayPath;
      case 'qq':
        return UserApiMetadata.loginWithQqPath;
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
      case 'alipay':
        return UserRequestPageIds.loginWithAlipay;
      case 'qq':
        return UserRequestPageIds.loginWithQq;
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
  Future<OtpSendResultData> sendOtp({
    required String phone,
    String? deviceId,
    String? platform,
    String? appVersion,
    String? sourceOperation,
  }) async {
    final context = UserRequestPageIds.sendOtp;
    final resp = await _client.postJson(
      _uri(UserApiMetadata.sendOtpPath),
      headers: _headersForOperation(UserApiMetadata.sendOtpOperation),
      body: <String, dynamic>{
        'phone': phone,
        if (deviceId != null && deviceId.isNotEmpty) 'deviceId': deviceId,
        if (platform != null && platform.isNotEmpty) 'platform': platform,
        if (appVersion != null && appVersion.isNotEmpty)
          'appVersion': appVersion,
        if (sourceOperation != null && sourceOperation.isNotEmpty)
          'sourceOperation': sourceOperation,
      },
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
    String? deviceId,
    String? platform,
    String? appVersion,
    String? agreementVersion,
    String? privacyVersion,
  }) async {
    final normalizedType = credentialType.trim().toLowerCase();
    final body = switch (normalizedType) {
      'phone' => <String, dynamic>{
        'phone': credentialKey,
        if (otpCode != null && otpCode.isNotEmpty) 'otpCode': otpCode,
        if (deviceId != null && deviceId.isNotEmpty) 'deviceId': deviceId,
        if (platform != null && platform.isNotEmpty) 'platform': platform,
        if (appVersion != null && appVersion.isNotEmpty)
          'appVersion': appVersion,
        if (agreementVersion != null && agreementVersion.isNotEmpty)
          'agreementVersion': agreementVersion,
        if (privacyVersion != null && privacyVersion.isNotEmpty)
          'privacyVersion': privacyVersion,
      },
      'wechat' => <String, dynamic>{
        'wechatCode': credentialKey,
        if (deviceId != null && deviceId.isNotEmpty) 'deviceId': deviceId,
        if (platform != null && platform.isNotEmpty) 'platform': platform,
      },
      'alipay' => <String, dynamic>{
        'alipayAuthCode': credentialKey,
        if (deviceId != null && deviceId.isNotEmpty) 'deviceId': deviceId,
        if (platform != null && platform.isNotEmpty) 'platform': platform,
      },
      'qq' => <String, dynamic>{
        'qqAuthCode': credentialKey,
        if (deviceId != null && deviceId.isNotEmpty) 'deviceId': deviceId,
        if (platform != null && platform.isNotEmpty) 'platform': platform,
      },
      _ => throw ArgumentError.value(
        credentialType,
        'credentialType',
        'Unsupported credential type',
      ),
    };
    if (displayLabel != null) {
      body['displayLabel'] = displayLabel;
    }
    final resp = await _client.postJson(
      _uri(_loginPathForCredentialType(credentialType)),
      headers: _headersForOperation(switch (normalizedType) {
        'phone' => UserApiMetadata.loginWithPhoneOperation,
        'wechat' => UserApiMetadata.loginWithWechatOperation,
        'alipay' => UserApiMetadata.loginWithAlipayOperation,
        'qq' => UserApiMetadata.loginWithQqOperation,
        _ => throw StateError('Unsupported credential type'),
      }),
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
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) async {
    final context = UserRequestPageIds.loginOneTap;
    final resp = await _client.postJson(
      _uri(UserApiMetadata.loginOneTapPath),
      headers: _headersForOperation(UserApiMetadata.loginOneTapOperation),
      body: <String, dynamic>{
        'vendor': vendor,
        'carrierToken': carrierToken,
        'deviceId': deviceId,
        'platform': platform,
        if (appVersion != null && appVersion.isNotEmpty)
          'appVersion': appVersion,
        'agreementVersion': agreementVersion,
        'privacyVersion': privacyVersion,
      },
    );
    return _authResultFromResponse(resp, context);
  }

  @override
  Future<OneTapLoginHintDto> resolveOneTapLoginHint({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
  }) async {
    final context = UserRequestPageIds.resolveOneTapLoginHint;
    final resp = await _client.postJson(
      _uri(UserApiMetadata.resolveOneTapLoginHintPath),
      headers: _headersForOperation(
        UserApiMetadata.resolveOneTapLoginHintOperation,
      ),
      body: <String, dynamic>{
        'vendor': vendor,
        'carrierToken': carrierToken,
        'deviceId': deviceId,
        'platform': platform,
        if (appVersion != null && appVersion.isNotEmpty)
          'appVersion': appVersion,
      },
    );
    return OneTapLoginHintDto.fromMap(
      CloudResponseDecoder.asObject(resp, context: context),
    );
  }

  @override
  Future<AuthLoginResultDto> loginWechat({
    required String wechatCode,
    required String deviceId,
    required String platform,
  }) async {
    final context = UserRequestPageIds.loginWithWechat;
    final resp = await _client.postJson(
      _uri(UserApiMetadata.loginWithWechatPath),
      headers: _headersForOperation(UserApiMetadata.loginWithWechatOperation),
      body: <String, dynamic>{
        'wechatCode': wechatCode,
        'deviceId': deviceId,
        'platform': platform,
      },
    );
    return _authResultFromResponse(resp, context);
  }

  @override
  Future<AuthLoginResultDto> loginAlipay({
    required String alipayAuthCode,
    required String deviceId,
    required String platform,
  }) async {
    final context = UserRequestPageIds.loginWithAlipay;
    final resp = await _client.postJson(
      _uri(UserApiMetadata.loginWithAlipayPath),
      headers: _headersForOperation(UserApiMetadata.loginWithAlipayOperation),
      body: <String, dynamic>{
        'alipayAuthCode': alipayAuthCode,
        'deviceId': deviceId,
        'platform': platform,
      },
    );
    return _authResultFromResponse(resp, context);
  }

  @override
  Future<AuthLoginResultDto> loginQq({
    required String qqAuthCode,
    required String deviceId,
    required String platform,
  }) async {
    final context = UserRequestPageIds.loginWithQq;
    final resp = await _client.postJson(
      _uri(UserApiMetadata.loginWithQqPath),
      headers: _headersForOperation(UserApiMetadata.loginWithQqOperation),
      body: <String, dynamic>{
        'qqAuthCode': qqAuthCode,
        'deviceId': deviceId,
        'platform': platform,
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
      headers: _headersForOperation(UserApiMetadata.loginAnonymousOperation),
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
      headers: _headersForOperation(UserApiMetadata.refreshTokenOperation),
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
  Future<void> bindPhoneWithOtp({
    required String phone,
    required String otpCode,
    String? displayLabel,
  }) async {
    await _client.postJson(
      _uri(UserApiMetadata.bindPhoneCredentialPath),
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.bindPhoneCredential,
      ),
      body: <String, dynamic>{
        'phone': phone,
        'otpCode': otpCode,
        if (displayLabel != null && displayLabel.isNotEmpty)
          'displayLabel': displayLabel,
      },
    );
  }

  @override
  Future<void> bindCarrierPhone({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? displayLabel,
  }) async {
    await _client.postJson(
      _uri(UserApiMetadata.bindCarrierPhoneCredentialPath),
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.bindCarrierPhoneCredential,
      ),
      body: <String, dynamic>{
        'vendor': vendor,
        'carrierToken': carrierToken,
        'deviceId': deviceId,
        'platform': platform,
        if (displayLabel != null && displayLabel.isNotEmpty)
          'displayLabel': displayLabel,
      },
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
