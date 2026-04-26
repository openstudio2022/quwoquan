import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/active_persona_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_create_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_lifecycle_guard_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_summary_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_update_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_setting_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

UserSettingDto _userSettingDtoFromWire(Map<String, dynamic> json) {
  final m = Map<String, dynamic>.from(json);
  m.putIfAbsent('userId', () => '');
  return UserSettingDto.fromJson(m);
}

/// User 域 Repository：分身管理、活动身份上下文与用户设置。
abstract class UserRepository {
  Future<List<PersonaManagementItemViewData>> listPersonas();
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary();
  Future<ActivePersonaContextViewData> getActivePersonaContext();
  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String? userHandle,
    String isolationLevel = 'open',
    String? purposeHint,
  });
  Future<PersonaManagementItemViewData> updatePersona(
    String personaId, {
    String? displayName,
    String? userHandle,
    String? phone,
    String? email,
    String? avatarUrl,
    String? isolationLevel,
    String? purposeHint,
    String? applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  });
  Future<void> activatePersona(String personaId);
  Future<int> applyPersonaProfileSync(
    String personaId, {
    required List<String> fieldsMask,
    String applyScope = 'all_sub_accounts',
    List<String> syncTargetIds = const <String>[],
  });
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  );
  Future<void> retirePersona(String personaId);
  Future<void> deleteEmptyPersona(String personaId);

  Future<UserSettingDto> getNotificationSettings();
  Future<UserSettingDto> getPrivacySettings();
}

/// 与网关 `ListSubAccounts` 同形 JSON，经 `jsonDecode` 再走 Wire → View（与 Remote 对齐）。
const String _kMockPersonasWireJson = r'''
[
  {"personaId":"persona_primary","subAccountId":"persona_primary","profileSubjectId":"persona_primary","displayName":"主分身","userHandle":"main_handle","phone":"13800000000","email":"main@example.com","avatarUrl":"https://i.pravatar.cc/150?u=user_001","isolationLevel":"open","profileVisibility":"public","isPrimary":true,"isActive":true,"inheritsProfileFromOwner":true,"overriddenProfileFields":[]},
  {"personaId":"persona_photo","subAccountId":"persona_photo","profileSubjectId":"persona_photo","displayName":"摄影分身","userHandle":"photo_handle","phone":"13800000000","email":"photo@example.com","avatarUrl":"https://i.pravatar.cc/150?u=user_001_photo","isolationLevel":"semi","profileVisibility":"public","isPrimary":false,"isActive":false,"hasAttributedHistory":true,"inheritsProfileFromOwner":false,"overriddenProfileFields":["email"]}
]
''';

List<Map<String, dynamic>> _decodeMockPersonasWire() {
  final decoded = jsonDecode(_kMockPersonasWireJson);
  if (decoded is! List) {
    return const <Map<String, dynamic>>[];
  }
  return decoded
      .whereType<Map>()
      .map((e) => Map<String, dynamic>.from(e))
      .toList(growable: false);
}

class MockUserRepository implements UserRepository {
  static final List<Map<String, dynamic>> _mockPersonas =
      _decodeMockPersonasWire();

  @override
  Future<void> activatePersona(String personaId) async {}

  @override
  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String? userHandle,
    String isolationLevel = 'open',
    String? purposeHint,
  }) async {
    return PersonaManagementItemViewData.fromMap(<String, dynamic>{
      'personaId': 'persona_${displayName.hashCode.abs()}',
      'subAccountId': 'persona_${displayName.hashCode.abs()}',
      'profileSubjectId': 'persona_${displayName.hashCode.abs()}',
      'displayName': displayName,
      'userHandle': userHandle ?? '',
      'phone': _mockPersonas.first['phone'] ?? '',
      'email': _mockPersonas.first['email'] ?? '',
      'isolationLevel': isolationLevel,
      'profileVisibility': 'public',
      'isPrimary': false,
      'isActive': false,
      'inheritsProfileFromOwner': true,
      'overriddenProfileFields': const <String>[],
    });
  }

  @override
  Future<int> applyPersonaProfileSync(
    String personaId, {
    required List<String> fieldsMask,
    String applyScope = 'all_sub_accounts',
    List<String> syncTargetIds = const <String>[],
  }) async {
    return syncTargetIds.isEmpty ? 1 : syncTargetIds.length;
  }

  @override
  Future<void> deleteEmptyPersona(String personaId) async {}

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return ActivePersonaContextViewData.fromMap(_mockPersonas.first);
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    return PersonaManagementSummaryViewData.fromMap(<String, dynamic>{
      'items': _mockPersonas,
      'quota': <String, dynamic>{
        'usedSubAccounts': _mockPersonas.length,
        'maxSubAccounts': 5,
      },
      'activeContext': _mockPersonas.first,
    });
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) async {
    return PersonaLifecycleGuardViewData.fromMap(<String, dynamic>{
      'personaId': personaId,
      'subAccountId': personaId,
      'canDelete': personaId != 'persona_primary',
      'canRetire': personaId != 'persona_primary',
      'requiredAction': '',
      'reasonCode': personaId == 'persona_primary' ? 'primary_guard' : '',
      'message': personaId == 'persona_primary' ? '主分身不可删除' : '',
    });
  }

  @override
  Future<UserSettingDto> getNotificationSettings() async {
    return _userSettingDtoFromWire(<String, dynamic>{'enablePush': true});
  }

  @override
  Future<UserSettingDto> getPrivacySettings() async {
    return _userSettingDtoFromWire(<String, dynamic>{
      'profileVisibility': 'public',
    });
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    return _mockPersonas
        .map(
          (m) => PersonaManagementItemViewData.fromPersonaManagementItemWire(
            PersonaManagementItemWireDto.fromMap(m),
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<void> retirePersona(String personaId) async {}

  @override
  Future<PersonaManagementItemViewData> updatePersona(
    String personaId, {
    String? displayName,
    String? userHandle,
    String? phone,
    String? email,
    String? avatarUrl,
    String? isolationLevel,
    String? purposeHint,
    String? applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  }) async {
    return PersonaManagementItemViewData.fromMap(<String, dynamic>{
      'personaId': personaId,
      'subAccountId': personaId,
      'profileSubjectId': personaId,
      'displayName': displayName ?? '已更新分身',
      'userHandle': userHandle ?? 'updated_handle',
      'phone': phone ?? '',
      'email': email ?? '',
      'avatarUrl': avatarUrl ?? '',
      'isolationLevel': isolationLevel ?? 'open',
      'profileVisibility': switch (isolationLevel ?? 'open') {
        'strict' => 'private',
        'semi' => 'friends',
        _ => 'public',
      },
      'isPrimary': false,
      'isActive': false,
      'inheritsProfileFromOwner': false,
      'overriddenProfileFields': fieldsMask ?? const <String>[],
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
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    final uri = _uri(UserApiMetadata.listPersonasPath);
    final items = await _httpClient.getJsonItemList(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listPersonas),
      context: UserRequestPageIds.listPersonas,
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
  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String? userHandle,
    String isolationLevel = 'open',
    String? purposeHint,
  }) async {
    final uri = _uri(UserApiMetadata.createPersonaPath);
    final request = PersonaCreateRequestDto(
      displayName: displayName,
      userHandle: userHandle,
      isolationLevel: isolationLevel,
      purposeHint: purposeHint,
    );
    final object = await _httpClient.postJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.createPersona),
      body: request.toMap(),
      context: UserRequestPageIds.createPersona,
    );
    return PersonaManagementItemViewData.fromPersonaManagementItemWire(
      PersonaManagementItemWireDto.fromMap(object),
    );
  }

  @override
  Future<PersonaManagementItemViewData> updatePersona(
    String personaId, {
    String? displayName,
    String? userHandle,
    String? phone,
    String? email,
    String? avatarUrl,
    String? isolationLevel,
    String? purposeHint,
    String? applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  }) async {
    final uri = _uri(UserApiMetadata.updatePersonaPath(personaId: personaId));
    final request = PersonaUpdateRequestDto(
      displayName: displayName,
      userHandle: userHandle,
      phone: phone,
      email: email,
      avatarUrl: avatarUrl,
      isolationLevel: isolationLevel,
      purposeHint: purposeHint,
      applyScope: applyScope,
      syncTargetIds: syncTargetIds,
      fieldsMask: fieldsMask,
    );
    final object = await _httpClient.patchJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.updatePersona),
      body: request.toMap(),
      context: UserRequestPageIds.updatePersona,
    );
    return PersonaManagementItemViewData.fromPersonaManagementItemWire(
      PersonaManagementItemWireDto.fromMap(object),
    );
  }

  @override
  Future<void> activatePersona(String personaId) async {
    final uri = _uri(UserApiMetadata.activatePersonaPath(personaId: personaId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.activatePersona),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<int> applyPersonaProfileSync(
    String personaId, {
    required List<String> fieldsMask,
    String applyScope = 'all_sub_accounts',
    List<String> syncTargetIds = const <String>[],
  }) async {
    final uri = _uri(
      UserApiMetadata.applyPersonaProfileSyncPath(personaId: personaId),
    );
    final object = await _httpClient.postJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.applyPersonaProfileSync,
      ),
      body: <String, dynamic>{
        'applyScope': applyScope,
        'syncTargetIds': syncTargetIds,
        'fieldsMask': fieldsMask,
      },
      context: UserRequestPageIds.applyPersonaProfileSync,
    );
    final value = object['appliedCount'];
    if (value is num) {
      return value.toInt();
    }
    return 0;
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) async {
    final uri = _uri(
      UserApiMetadata.getPersonaLifecycleGuardPath(personaId: personaId),
    );
    final object = await _httpClient.getJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getPersonaLifecycleGuard,
      ),
      context: UserRequestPageIds.getPersonaLifecycleGuard,
    );
    return PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
      PersonaLifecycleGuardWireDto.fromMap(object),
    );
  }

  @override
  Future<void> retirePersona(String personaId) async {
    final uri = _uri(UserApiMetadata.retirePersonaPath(personaId: personaId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.retirePersona),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> deleteEmptyPersona(String personaId) async {
    final uri = _uri(
      UserApiMetadata.deleteEmptyPersonaPath(personaId: personaId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.deleteEmptyPersona,
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
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getPrivacySettings,
      ),
      context: UserRequestPageIds.getPrivacySettings,
    );
    return _userSettingDtoFromWire(object);
  }
}
