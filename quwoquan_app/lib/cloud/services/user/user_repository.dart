import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/active_persona_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_lifecycle_guard_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_summary_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_setting_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

UserSettingDto _userSettingDtoFromWire(Map<String, dynamic> json) {
  final m = Map<String, dynamic>.from(json);
  m.putIfAbsent('userId', () => '');
  return UserSettingDto.fromJson(m);
}

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

  Future<UserSettingDto> getNotificationSettings();
  Future<UserSettingDto> getPrivacySettings();
}

/// 与网关 `ListSubAccounts` 同形 JSON，经 `jsonDecode` 再走 Wire → View（与 Remote 对齐）。
const String _kMockSubAccountsWireJson = r'''
[
  {"subAccountId":"owner_primary","profileSubjectId":"user_001","displayName":"主账号","avatarUrl":"https://i.pravatar.cc/150?u=user_001","isolationLevel":"open","profileVisibility":"public","isPrimary":true,"isActive":true},
  {"subAccountId":"persona_photo","profileSubjectId":"user_001_photo","displayName":"摄影分身","avatarUrl":"https://i.pravatar.cc/150?u=user_001_photo","isolationLevel":"semi","profileVisibility":"public","isPrimary":false,"isActive":false,"hasAttributedHistory":true}
]
''';

List<Map<String, dynamic>> _decodeMockSubAccountsWire() {
  final decoded = jsonDecode(_kMockSubAccountsWireJson);
  if (decoded is! List) {
    return const <Map<String, dynamic>>[];
  }
  return decoded
      .whereType<Map>()
      .map((e) => Map<String, dynamic>.from(e))
      .toList(growable: false);
}

class MockUserRepository implements UserRepository {
  static final List<Map<String, dynamic>> _mockSubAccounts =
      _decodeMockSubAccountsWire();

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
  Future<UserSettingDto> getNotificationSettings() async {
    return _userSettingDtoFromWire(<String, dynamic>{'enablePush': true});
  }

  @override
  Future<UserSettingDto> getPrivacySettings() async {
    return _userSettingDtoFromWire(
      <String, dynamic>{'profileVisibility': 'public'},
    );
  }

  @override
  Future<List<PersonaManagementItemViewData>> listSubAccounts() async {
    return _mockSubAccounts
        .map(
          (m) => PersonaManagementItemViewData.fromPersonaManagementItemWire(
            PersonaManagementItemWireDto.fromMap(m),
          ),
        )
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

  @override
  Future<List<PersonaManagementItemViewData>> listSubAccounts() async {
    final uri = _uri(UserApiMetadata.listSubAccountsPath);
    final items = await _httpClient.getJsonItemList(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listSubAccounts),
      context: UserRequestPageIds.listSubAccounts,
    );
    return items
        .map(
          (m) => PersonaManagementItemViewData.fromPersonaManagementItemWire(
            PersonaManagementItemWireDto.fromMap(m),
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    final uri = _uri(UserApiMetadata.getPersonaManagementSummaryPath);
    final object = await _httpClient.getJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getPersonaManagementSummary,
      ),
      context: UserRequestPageIds.getPersonaManagementSummary,
    );
    return PersonaManagementSummaryViewData.fromPersonaManagementSummaryWire(
      PersonaManagementSummaryWireDto.fromMap(object),
    );
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    final uri = _uri(UserApiMetadata.getActivePersonaContextPath);
    final object = await _httpClient.getJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getActivePersonaContext,
      ),
      context: UserRequestPageIds.getActivePersonaContext,
    );
    return ActivePersonaContextViewData.fromActivePersonaContextWire(
      ActivePersonaContextWireDto.fromMap(object),
    );
  }

  @override
  Future<PersonaManagementItemViewData> createSubAccount({
    required String displayName,
    String isolationLevel = 'open',
  }) async {
    final uri = _uri(UserApiMetadata.createSubAccountPath);
    final object = await _httpClient.postJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.createSubAccount),
      body: <String, dynamic>{
        'displayName': displayName,
        'isolationLevel': isolationLevel,
      },
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
    final object = await _httpClient.patchJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.updateSubAccount),
      body: body,
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
    final object = await _httpClient.getJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getSubAccountLifecycleGuard,
      ),
      context: UserRequestPageIds.getSubAccountLifecycleGuard,
    );
    return PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
      PersonaLifecycleGuardWireDto.fromMap(object),
    );
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
  Future<UserSettingDto> getNotificationSettings() async {
    final uri = _uri(UserApiMetadata.getNotificationSettingsPath);
    final object = await _httpClient.getJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getNotificationSettings,
      ),
      context: UserRequestPageIds.getNotificationSettings,
    );
    return _userSettingDtoFromWire(object);
  }

  @override
  Future<UserSettingDto> getPrivacySettings() async {
    final uri = _uri(UserApiMetadata.getPrivacySettingsPath);
    final object = await _httpClient.getJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.getPrivacySettings),
      context: UserRequestPageIds.getPrivacySettings,
    );
    return _userSettingDtoFromWire(object);
  }
}

