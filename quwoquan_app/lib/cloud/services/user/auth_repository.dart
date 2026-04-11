import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/owner_credential_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

/// AuthRepository: 登录、凭证管理、SubAccount 管理。
abstract class AuthRepository {
  /// 手机号/微信/Apple 登录，首次自动创建 OwnerAccount + 默认 SubAccount。
  Future<AuthLoginResultDto> login({
    required String credentialType,
    required String credentialKey,
    String? displayLabel,
  });

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

  /// 列出当前账号的所有子账号。
  Future<List<PersonaManagementItemViewData>> listSubAccounts();

  /// 创建新子账号。
  Future<PersonaManagementItemViewData> createSubAccount({
    required String displayName,
    String isolationLevel = 'open',
  });

  /// 激活指定子账号（自动停用其他）。
  Future<void> activateSubAccount(String subAccountId);

  /// 删除子账号（最后一个禁止删除）。
  Future<void> deleteSubAccount(String subAccountId);
}

class MockAuthRepository implements AuthRepository {
  @override
  Future<AuthLoginResultDto> login({
    required String credentialType,
    required String credentialKey,
    String? displayLabel,
  }) async {
    await Future.delayed(const Duration(milliseconds: 300));
    return AuthLoginResultDto.fromMap(<String, dynamic>{
      'accessToken': 'mock_token_${credentialKey.hashCode}',
      'refreshToken': 'mock_refresh',
      'ownerId': 'mock_owner_id',
      'activeSub': <String, dynamic>{
        'profileSubjectId': 'mock_sub_id',
        'subAccountId': 'mock_sub_id',
      },
      'subAccountCount': 1,
    });
  }

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
  Future<List<PersonaManagementItemViewData>> listSubAccounts() async {
    return [
      PersonaManagementItemViewData.fromMap(<String, dynamic>{
        'id': 'mock_persona_1',
        'subAccountId': 'mock_sub_id',
        'displayName': '默认账号',
        'isolationLevel': 'open',
        'isPrimary': true,
        'isActive': true,
      }),
    ];
  }

  @override
  Future<PersonaManagementItemViewData> createSubAccount({
    required String displayName,
    String isolationLevel = 'open',
  }) async {
    return PersonaManagementItemViewData.fromMap(<String, dynamic>{
      'id': 'mock_persona_new',
      'subAccountId': 'mock_sub_new',
      'displayName': displayName,
      'isolationLevel': isolationLevel,
      'isPrimary': false,
      'isActive': false,
    });
  }

  @override
  Future<void> activateSubAccount(String subAccountId) async {}

  @override
  Future<void> deleteSubAccount(String subAccountId) async {}
}

class RemoteAuthRepository implements AuthRepository {
  RemoteAuthRepository({CloudHttpClient? httpClient, String? baseUrl})
      : _client = httpClient ?? CloudHttpClient(client: http.Client()),
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

  @override
  Future<AuthLoginResultDto> login({
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
    final resp = await _client.postJson(
      _uri(_loginPathForCredentialType(credentialType)),
      headers: CloudRequestHeaders.forPage(
        _loginPageIdForCredentialType(credentialType),
      ),
      body: body,
    );
    return AuthLoginResultDto.fromMap(
      CloudResponseDecoder.asObject(
        resp,
        context: _loginPageIdForCredentialType(credentialType),
      ),
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
      _uri(UserApiMetadata.unbindCredentialPath(credentialType: credentialType)),
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
    return CloudResponseDecoder.mapList(data, 'credentials')
        .map(OwnerCredentialRowDto.fromMap)
        .toList(growable: false);
  }

  @override
  Future<List<PersonaManagementItemViewData>> listSubAccounts() async {
    final resp = await _client.getJson(
      _uri(UserApiMetadata.listSubAccountsPath),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listSubAccounts),
    );
    final data = CloudResponseDecoder.asObject(
      resp,
      context: UserRequestPageIds.listSubAccounts,
    );
    return CloudResponseDecoder.mapList(data, 'subAccounts')
        .map(PersonaManagementItemViewData.fromMap)
        .toList(growable: false);
  }

  @override
  Future<PersonaManagementItemViewData> createSubAccount({
    required String displayName,
    String isolationLevel = 'open',
  }) async {
    final resp = await _client.postJson(
      _uri(UserApiMetadata.createSubAccountPath),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.createSubAccount),
      body: {'displayName': displayName, 'isolationLevel': isolationLevel},
    );
    return PersonaManagementItemViewData.fromMap(
      CloudResponseDecoder.asObject(
        resp,
        context: UserRequestPageIds.createSubAccount,
      ),
    );
  }

  @override
  Future<void> activateSubAccount(String subAccountId) async {
    await _client.postJson(
      _uri(UserApiMetadata.activateSubAccountPath(subAccountId: subAccountId)),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.activateSubAccount),
      body: {},
    );
  }

  @override
  Future<void> deleteSubAccount(String subAccountId) async {
    await _client.deleteJson(
      _uri(UserApiMetadata.deleteSubAccountPath(subAccountId: subAccountId)),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.deleteSubAccount),
    );
  }
}
