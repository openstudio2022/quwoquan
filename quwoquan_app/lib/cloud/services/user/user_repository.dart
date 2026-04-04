import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

/// User 域 Repository：owner-plane 子账号管理、活动身份上下文与用户设置。
abstract class UserRepository {
  Future<List<PersonaManagementItemViewData>> listSubAccounts();
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary();
  Future<ActivePersonaContextViewData> getActivePersonaContext();
  Future<PersonaManagementItemViewData> createSubAccount({
    required String displayName,
    String isolationLevel = 'open',
  });
  Future<PersonaManagementItemViewData> updateSubAccount(
    String subAccountId, {
    String? displayName,
    String? bio,
    String? avatarUrl,
    String? isolationLevel,
    String? profileVisibility,
  });
  Future<void> activateSubAccount(String subAccountId);
  Future<PersonaLifecycleGuardViewData> getSubAccountLifecycleGuard(
    String subAccountId,
  );
  Future<void> retireSubAccount(String subAccountId);
  Future<void> deleteEmptySubAccount(String subAccountId);

  Future<Map<String, dynamic>> getNotificationSettings();
  Future<Map<String, dynamic>> getPrivacySettings();
}

class MockUserRepository implements UserRepository {
  static const List<Map<String, dynamic>> _mockSubAccounts =
      <Map<String, dynamic>>[
        <String, dynamic>{
          'subAccountId': 'owner_primary',
          'profileSubjectId': 'user_001',
          'displayName': '主账号',
          'avatarUrl': 'https://i.pravatar.cc/150?u=user_001',
          'isolationLevel': 'open',
          'profileVisibility': 'public',
          'isPrimary': true,
          'isActive': true,
        },
        <String, dynamic>{
          'subAccountId': 'persona_photo',
          'profileSubjectId': 'user_001_photo',
          'displayName': '摄影分身',
          'avatarUrl': 'https://i.pravatar.cc/150?u=user_001_photo',
          'isolationLevel': 'semi',
          'profileVisibility': 'public',
          'isPrimary': false,
          'isActive': false,
          'hasAttributedHistory': true,
        },
      ];

  @override
  Future<void> activateSubAccount(String subAccountId) async {}

  @override
  Future<PersonaManagementItemViewData> createSubAccount({
    required String displayName,
    String isolationLevel = 'open',
  }) async {
    return PersonaManagementItemViewData.fromMap(<String, dynamic>{
      'subAccountId': 'persona_${displayName.hashCode.abs()}',
      'profileSubjectId': 'subject_${displayName.hashCode.abs()}',
      'displayName': displayName,
      'isolationLevel': isolationLevel,
      'profileVisibility': 'public',
      'isPrimary': false,
      'isActive': false,
    });
  }

  @override
  Future<void> deleteEmptySubAccount(String subAccountId) async {}

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return ActivePersonaContextViewData.fromMap(_mockSubAccounts.first);
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    return PersonaManagementSummaryViewData.fromMap(<String, dynamic>{
      'items': _mockSubAccounts,
      'quota': <String, dynamic>{
        'usedSubAccounts': _mockSubAccounts.length,
        'maxSubAccounts': 5,
      },
      'activeContext': _mockSubAccounts.first,
    });
  }

  @override
  Future<PersonaLifecycleGuardViewData> getSubAccountLifecycleGuard(
    String subAccountId,
  ) async {
    return PersonaLifecycleGuardViewData.fromMap(<String, dynamic>{
      'subAccountId': subAccountId,
      'canDelete': subAccountId != 'owner_primary',
      'canRetire': subAccountId != 'owner_primary',
      'requiredAction': '',
      'reasonCode': subAccountId == 'owner_primary' ? 'primary_guard' : '',
      'message': subAccountId == 'owner_primary' ? '主账号不可删除' : '',
    });
  }

  @override
  Future<Map<String, dynamic>> getNotificationSettings() async {
    return <String, dynamic>{'enablePush': true};
  }

  @override
  Future<Map<String, dynamic>> getPrivacySettings() async {
    return <String, dynamic>{'profileVisibility': 'public'};
  }

  @override
  Future<List<PersonaManagementItemViewData>> listSubAccounts() async {
    return _mockSubAccounts
        .map(PersonaManagementItemViewData.fromMap)
        .toList(growable: false);
  }

  @override
  Future<void> retireSubAccount(String subAccountId) async {}

  @override
  Future<PersonaManagementItemViewData> updateSubAccount(
    String subAccountId, {
    String? displayName,
    String? bio,
    String? avatarUrl,
    String? isolationLevel,
    String? profileVisibility,
  }) async {
    return PersonaManagementItemViewData.fromMap(<String, dynamic>{
      'subAccountId': subAccountId,
      'profileSubjectId': subAccountId,
      'displayName': displayName ?? '已更新分身',
      'avatarUrl': avatarUrl ?? '',
      'isolationLevel': isolationLevel ?? 'open',
      'profileVisibility': profileVisibility ?? 'public',
      'isPrimary': false,
      'isActive': false,
    });
  }
}

class RemoteUserRepository implements UserRepository {
  RemoteUserRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Map<String, dynamic> _asObject(
    dynamic decoded, {
    required String context,
  }) {
    return CloudResponseDecoder.asObject(decoded, context: context);
  }

  List<Map<String, dynamic>> _extractItems(
    dynamic decoded, {
    required String context,
  }) {
    if (decoded is List) {
      return decoded.whereType<Map>().map((item) {
        return item.cast<String, dynamic>();
      }).toList(growable: false);
    }
    final object = _asObject(decoded, context: context);
    final rawItems =
        (object['items'] as List?) ??
        (object['subAccounts'] as List?) ??
        (object['personas'] as List?) ??
        const <dynamic>[];
    return rawItems.whereType<Map>().map((item) {
      return item.cast<String, dynamic>();
    }).toList(growable: false);
  }

  @override
  Future<List<PersonaManagementItemViewData>> listSubAccounts() async {
    final uri = _uri(UserApiMetadata.listSubAccountsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listSubAccounts),
    );
    return _extractItems(
      decoded,
      context: UserRequestPageIds.listSubAccounts,
    ).map(PersonaManagementItemViewData.fromMap).toList(growable: false);
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    final uri = _uri(UserApiMetadata.getPersonaManagementSummaryPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getPersonaManagementSummary,
      ),
    );
    final object = _asObject(
      decoded,
      context: UserRequestPageIds.getPersonaManagementSummary,
    );
    return PersonaManagementSummaryViewData.fromMap(object);
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    final uri = _uri(UserApiMetadata.getActivePersonaContextPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getActivePersonaContext,
      ),
    );
    final object = _asObject(
      decoded,
      context: UserRequestPageIds.getActivePersonaContext,
    );
    return ActivePersonaContextViewData.fromMap(object);
  }

  @override
  Future<PersonaManagementItemViewData> createSubAccount({
    required String displayName,
    String isolationLevel = 'open',
  }) async {
    final uri = _uri(UserApiMetadata.createSubAccountPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.createSubAccount),
      body: <String, dynamic>{
        'displayName': displayName,
        'isolationLevel': isolationLevel,
      },
    );
    final object = _asObject(
      decoded,
      context: UserRequestPageIds.createSubAccount,
    );
    return PersonaManagementItemViewData.fromMap(object);
  }

  @override
  Future<PersonaManagementItemViewData> updateSubAccount(
    String subAccountId, {
    String? displayName,
    String? bio,
    String? avatarUrl,
    String? isolationLevel,
    String? profileVisibility,
  }) async {
    final uri = _uri(
      UserApiMetadata.updateSubAccountPath(subAccountId: subAccountId),
    );
    final body = <String, dynamic>{};
    if (displayName != null) body['displayName'] = displayName;
    if (bio != null) body['bio'] = bio;
    if (avatarUrl != null) body['avatarUrl'] = avatarUrl;
    if (isolationLevel != null) body['isolationLevel'] = isolationLevel;
    if (profileVisibility != null) body['profileVisibility'] = profileVisibility;
    final decoded = await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.updateSubAccount),
      body: body,
    );
    final object = _asObject(
      decoded,
      context: UserRequestPageIds.updateSubAccount,
    );
    return PersonaManagementItemViewData.fromMap(object);
  }

  @override
  Future<void> activateSubAccount(String subAccountId) async {
    final uri = _uri(
      UserApiMetadata.activateSubAccountPath(subAccountId: subAccountId),
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.activateSubAccount,
      ),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<PersonaLifecycleGuardViewData> getSubAccountLifecycleGuard(
    String subAccountId,
  ) async {
    final uri = _uri(
      UserApiMetadata.getSubAccountLifecycleGuardPath(
        subAccountId: subAccountId,
      ),
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getSubAccountLifecycleGuard,
      ),
    );
    final object = _asObject(
      decoded,
      context: UserRequestPageIds.getSubAccountLifecycleGuard,
    );
    return PersonaLifecycleGuardViewData.fromMap(object);
  }

  @override
  Future<void> retireSubAccount(String subAccountId) async {
    final uri = _uri(
      UserApiMetadata.retireSubAccountPath(subAccountId: subAccountId),
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.retireSubAccount),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> deleteEmptySubAccount(String subAccountId) async {
    final uri = _uri(
      UserApiMetadata.deleteEmptySubAccountPath(subAccountId: subAccountId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.deleteEmptySubAccount,
      ),
    );
  }

  @override
  Future<Map<String, dynamic>> getNotificationSettings() async {
    final uri = _uri(UserApiMetadata.getNotificationSettingsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getNotificationSettings,
      ),
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: UserRequestPageIds.getNotificationSettings,
    );
  }

  @override
  Future<Map<String, dynamic>> getPrivacySettings() async {
    final uri = _uri(UserApiMetadata.getPrivacySettingsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.getPrivacySettings),
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: UserRequestPageIds.getPrivacySettings,
    );
  }
}

