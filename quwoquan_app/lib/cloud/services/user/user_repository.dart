import 'dart:convert';

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
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/auth/mock_session_identity.dart';

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
    String isolationLevel = 'open',
    String? purposeHint,
  });
  Future<PersonaManagementItemViewData> updatePersona(
    String subAccountId, {
    String? displayName,
    String? phone,
    String? email,
    String? avatarUrl,
    String? isolationLevel,
    String? purposeHint,
    String? applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  });
  Future<void> activatePersona(String subAccountId);
  Future<int> applyPersonaProfileSync(
    String subAccountId, {
    required List<String> fieldsMask,
    String applyScope = 'all_sub_accounts',
    List<String> syncTargetIds = const <String>[],
  });
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String subAccountId,
  );
  Future<void> retirePersona(String subAccountId);
  Future<void> deleteEmptyPersona(String subAccountId);

  Future<UserSettingDto> getNotificationSettings();
  Future<UserSettingDto> getPrivacySettings();
}

/// 与网关 `ListSubAccounts` 同形 JSON，经 `jsonDecode` 再走 Wire → View（与 Remote 对齐）。
const String _kMockPersonasWireJson = r'''
[
  {"subAccountId":"persona_primary","displayName":"主分身","userHandle":"main_handle","phone":"13800000000","email":"main@example.com","avatarUrl":"media/avatar/s/mock/user/user_001/v1/avatar.png","avatarVersion":1,"isolationLevel":"open","profileVisibility":"public","isPrimary":true,"isActive":true,"inheritsProfileFromOwner":true,"overriddenProfileFields":[]},
  {"subAccountId":"persona_photo","displayName":"摄影分身","userHandle":"photo_handle","phone":"13800000000","email":"photo@example.com","avatarUrl":"media/avatar/s/mock/user/user_001_photo/v1/avatar.png","avatarVersion":1,"isolationLevel":"semi","profileVisibility":"public","isPrimary":false,"isActive":false,"hasAttributedHistory":true,"inheritsProfileFromOwner":false,"overriddenProfileFields":["email"]}
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

Map<String, dynamic> _mockActivePersonaContextWire() {
  final profile = resolveMockUserProfileWire(kMockCurrentSubAccountId);
  return <String, dynamic>{
    'ownerUserId': profile.ownerUserId.isNotEmpty
        ? profile.ownerUserId
        : kMockCurrentOwnerId,
    'subAccountId': profile.subAccountId.isNotEmpty
        ? profile.subAccountId
        : kMockCurrentSubAccountId,
    'subjectType': profile.subjectType.isNotEmpty
        ? profile.subjectType
        : 'user',
    'displayName': profile.displayName,
    'avatarUrl': profile.avatarUrl,
    'avatarVersion': profile.avatarVersion,
    'personaContextVersion':
        profile.updatedAt?.millisecondsSinceEpoch.toString() ?? 'mock-static',
    'personaSnapshotVersion': 1,
    'sourceSurfaceId': 'mock.user_repository',
    'explicitOverride': false,
    'isPrimary': true,
  };
}

List<Map<String, dynamic>> _mockPersonaItemsWithCurrentProfile() {
  final active = _mockActivePersonaContextWire();
  return _decodeMockPersonasWire()
      .asMap()
      .entries
      .map((entry) {
        final index = entry.key;
        final item = entry.value;
        if (index != 0) {
          return item;
        }
        return <String, dynamic>{
          ...item,
          'subAccountId': active['subAccountId'],
          'userId': active['subAccountId'],
          'displayName': active['displayName'],
          'avatarUrl': active['avatarUrl'],
          'avatarVersion': active['avatarVersion'],
          'isPrimary': true,
          'isActive': true,
          'inheritsProfileFromOwner': true,
        };
      })
      .toList(growable: false);
}

class MockUserRepository implements UserRepository {
  static final List<Map<String, dynamic>> _mockPersonas =
      _decodeMockPersonasWire();

  @override
  Future<void> activatePersona(String subAccountId) async {}

  @override
  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String isolationLevel = 'open',
    String? purposeHint,
  }) async {
    final generatedSubAccountId = 'persona_${displayName.hashCode.abs()}';
    final generatedHandle = 'qw${generatedSubAccountId.hashCode.abs()}';
    return PersonaManagementItemViewData.fromMap(<String, dynamic>{
      'subAccountId': generatedSubAccountId,
      'displayName': displayName,
      'userHandle': generatedHandle,
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
    String subAccountId, {
    required List<String> fieldsMask,
    String applyScope = 'all_sub_accounts',
    List<String> syncTargetIds = const <String>[],
  }) async {
    return syncTargetIds.isEmpty ? 1 : syncTargetIds.length;
  }

  @override
  Future<void> deleteEmptyPersona(String subAccountId) async {}

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return ActivePersonaContextViewData.fromMap(
      _mockActivePersonaContextWire(),
    );
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    final items = _mockPersonaItemsWithCurrentProfile();
    return PersonaManagementSummaryViewData.fromMap(<String, dynamic>{
      'items': items,
      'quota': <String, dynamic>{
        'usedSubAccounts': _mockPersonas.length,
        'maxSubAccounts': 5,
      },
      'activeContext': _mockActivePersonaContextWire(),
    });
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String subAccountId,
  ) async {
    return PersonaLifecycleGuardViewData.fromMap(<String, dynamic>{
      'subAccountId': subAccountId,
      'canDelete': subAccountId != 'persona_primary',
      'canRetire': subAccountId != 'persona_primary',
      'requiredAction': '',
      'reasonCode': subAccountId == 'persona_primary' ? 'primary_guard' : '',
      'message': subAccountId == 'persona_primary' ? '主分身不可删除' : '',
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
    return _mockPersonaItemsWithCurrentProfile()
        .map(
          (m) => PersonaManagementItemViewData.fromPersonaManagementItemWire(
            PersonaManagementItemWireDto.fromMap(m),
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<void> retirePersona(String subAccountId) async {}

  @override
  Future<PersonaManagementItemViewData> updatePersona(
    String subAccountId, {
    String? displayName,
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
      'subAccountId': subAccountId,
      'displayName': displayName ?? '已更新分身',
      'userHandle': 'qw${subAccountId.hashCode.abs()}',
      'phone': phone ?? '',
      'email': email ?? '',
      'avatarUrl': avatarUrl ?? '',
      'avatarVersion': avatarUrl == null || avatarUrl.isEmpty ? 0 : 1,
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

typedef UserRemoteMergeRequestContext =
    Future<Map<String, String>> Function(Map<String, String> baseHeaders);

class RemoteUserRepository implements UserRepository {
  RemoteUserRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
    this._mergeRequestContext,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final UserRemoteMergeRequestContext? _mergeRequestContext;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Future<Map<String, String>> _resolveHeaders(String clientPageId) async {
    final base = CloudRequestHeaders.forPage(clientPageId);
    final merger = _mergeRequestContext;
    if (merger == null) {
      return base;
    }
    return merger(base);
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    final uri = _uri(UserApiMetadata.listPersonasPath);
    final items = await _httpClient.getJsonItemList(
      uri,
      headers: await _resolveHeaders(UserRequestPageIds.listPersonas),
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
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
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
    String isolationLevel = 'open',
    String? purposeHint,
  }) async {
    final uri = _uri(UserApiMetadata.createPersonaPath);
    final request = PersonaCreateRequestDto(
      displayName: displayName,
      isolationLevel: isolationLevel,
      purposeHint: purposeHint,
    );
    final object = await _httpClient.postJsonObject(
      uri,
      headers: await _resolveHeaders(UserRequestPageIds.createPersona),
      body: request.toMap(),
      context: UserRequestPageIds.createPersona,
    );
    return PersonaManagementItemViewData.fromPersonaManagementItemWire(
      PersonaManagementItemWireDto.fromMap(object),
    );
  }

  @override
  Future<PersonaManagementItemViewData> updatePersona(
    String subAccountId, {
    String? displayName,
    String? phone,
    String? email,
    String? avatarUrl,
    String? isolationLevel,
    String? purposeHint,
    String? applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  }) async {
    final uri = _uri(
      UserApiMetadata.updatePersonaPath(subAccountId: subAccountId),
    );
    final request = PersonaUpdateRequestDto(
      displayName: displayName,
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
      headers: await _resolveHeaders(UserRequestPageIds.updatePersona),
      body: request.toMap(),
      context: UserRequestPageIds.updatePersona,
    );
    return PersonaManagementItemViewData.fromPersonaManagementItemWire(
      PersonaManagementItemWireDto.fromMap(object),
    );
  }

  @override
  Future<void> activatePersona(String subAccountId) async {
    final uri = _uri(
      UserApiMetadata.activatePersonaPath(subAccountId: subAccountId),
    );
    await _httpClient.postJson(
      uri,
      headers: await _resolveHeaders(UserRequestPageIds.activatePersona),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<int> applyPersonaProfileSync(
    String subAccountId, {
    required List<String> fieldsMask,
    String applyScope = 'all_sub_accounts',
    List<String> syncTargetIds = const <String>[],
  }) async {
    final uri = _uri(
      UserApiMetadata.applyPersonaProfileSyncPath(subAccountId: subAccountId),
    );
    final object = await _httpClient.postJsonObject(
      uri,
      headers: await _resolveHeaders(
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
    String subAccountId,
  ) async {
    final uri = _uri(
      UserApiMetadata.getPersonaLifecycleGuardPath(subAccountId: subAccountId),
    );
    final object = await _httpClient.getJsonObject(
      uri,
      headers: await _resolveHeaders(
        UserRequestPageIds.getPersonaLifecycleGuard,
      ),
      context: UserRequestPageIds.getPersonaLifecycleGuard,
    );
    return PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
      PersonaLifecycleGuardWireDto.fromMap(object),
    );
  }

  @override
  Future<void> retirePersona(String subAccountId) async {
    final uri = _uri(
      UserApiMetadata.retirePersonaPath(subAccountId: subAccountId),
    );
    await _httpClient.postJson(
      uri,
      headers: await _resolveHeaders(UserRequestPageIds.retirePersona),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> deleteEmptyPersona(String subAccountId) async {
    final uri = _uri(
      UserApiMetadata.deleteEmptyPersonaPath(subAccountId: subAccountId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: await _resolveHeaders(UserRequestPageIds.deleteEmptyPersona),
    );
  }

  @override
  Future<UserSettingDto> getNotificationSettings() async {
    final uri = _uri(UserApiMetadata.getNotificationSettingsPath);
    final object = await _httpClient.getJsonObject(
      uri,
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(UserRequestPageIds.getPrivacySettings),
      context: UserRequestPageIds.getPrivacySettings,
    );
    return _userSettingDtoFromWire(object);
  }
}
