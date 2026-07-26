import 'dart:convert';

import 'package:quwoquan_app/cloud/runtime/generated/user/active_persona_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_lifecycle_guard_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_summary_wire_dto.g.dart';
import 'package:quwoquan_app/application/user/persona/persona_query.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

import 'alpha_user_profile_repository.dart';

/// 与网关 `ListSubAccounts` 同形 JSON，经 `jsonDecode` 再走 Wire → View（与 Remote 对齐）。
const String _kMockPersonasWireJson = r'''
[
  {"subAccountId":"persona_primary","displayName":"主分身","userHandle":"main_handle","phone":"13800000000","email":"main@example.com","avatarUrl":"media/avatar/s/mock/user/user_001/v1/avatar.png","avatarVersion":1,"isolationLevel":"open","profileVisibility":"public","isPrimary":true,"isActive":true,"inheritsProfileFromOwner":true,"overriddenProfileFields":[]},
  {"subAccountId":"persona_photo","displayName":"摄影分身","userHandle":"photo_handle","phone":"13800000000","email":"photo@example.com","avatarUrl":"media/avatar/s/mock/user/user_001_photo/v1/avatar.png","avatarVersion":1,"isolationLevel":"semi","profileVisibility":"public","isPrimary":false,"isActive":false,"inheritsProfileFromOwner":false,"overriddenProfileFields":["email"]}
]
''';

List<Map<String, dynamic>> _decodeMockPersonasWire() {
  final decoded = jsonDecode(_kMockPersonasWireJson);
  if (decoded is! List) {
    return <Map<String, dynamic>>[];
  }
  // growable：persona 命令 mock 会原位更新 seed。
  return decoded
      .whereType<Map>()
      .map((e) => Map<String, dynamic>.from(e))
      .toList();
}

Map<String, dynamic> _mockActivePersonaContextWire() {
  // `resolveMockUserProfileWire` 是 mock 当前用户资料的唯一解析入口，内部已按
  // override → shared contract seed → _defaultProfile 顺序回退。avatarUrl 在
  // 未配置 prefab 头像的运行态回退到 persona seed，保证契约（非空）不漂移。
  final profile = resolveMockUserProfileWire(kMockCurrentSubAccountId);
  final seedAvatarUrl = _decodeMockPersonasWire()
      .firstWhere(
        (item) => item['isPrimary'] == true,
        orElse: () => const <String, dynamic>{},
      )['avatarUrl']
      ?.toString();
  final avatarUrl = profile.avatarUrl.isNotEmpty
      ? profile.avatarUrl
      : (seedAvatarUrl ?? '');
  return <String, dynamic>{
    'ownerUserId': kMockCurrentOwnerId,
    'subAccountId': kMockCurrentSubAccountId,
    'subjectType': profile.subjectType.isNotEmpty
        ? profile.subjectType
        : 'user',
    'displayName': profile.displayName,
    'avatarUrl': avatarUrl,
    'avatarVersion': profile.avatarVersion > 0 ? profile.avatarVersion : 1,
    'personaContextVersion':
        profile.updatedAt?.millisecondsSinceEpoch.toString() ?? 'mock-static',
    'personaSnapshotVersion': 1,
    'sourceSurfaceId': 'mock.user_repository',
    'explicitOverride': false,
    'isPrimary': true,
  };
}

class AlphaPersonaFacet
    implements PersonaQuery, contracts.PersonaManagementCommandWriter {
  static final List<Map<String, dynamic>> _mockPersonas =
      _decodeMockPersonasWire();

  static List<Map<String, dynamic>> _personaItemsWithCurrentProfile() {
    final active = _mockActivePersonaContextWire();
    return _mockPersonas
        .map((item) {
          if (item['isPrimary'] != true) {
            return Map<String, dynamic>.from(item);
          }
          return <String, dynamic>{
            ...item,
            'subAccountId': active['subAccountId'],
            'userId': active['subAccountId'],
            'displayName': active['displayName'],
            'avatarUrl': active['avatarUrl'],
            'avatarVersion': active['avatarVersion'],
            'isPrimary': true,
            'inheritsProfileFromOwner': true,
          };
        })
        .toList(growable: false);
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return ActivePersonaContextViewData.fromActivePersonaContextWire(
      ActivePersonaContextWireDto.fromMap(_mockActivePersonaContextWire()),
    );
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    final items = _personaItemsWithCurrentProfile();
    return PersonaManagementSummaryViewData.fromPersonaManagementSummaryWire(
      PersonaManagementSummaryWireDto.fromMap(<String, dynamic>{
        'items': items,
        'quota': <String, dynamic>{
          'usedSubAccounts': _mockPersonas.length,
          'maxSubAccounts': 5,
        },
        'activeContext': _mockActivePersonaContextWire(),
      }),
    );
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String subAccountId,
  ) async {
    final index = _indexOf(subAccountId);
    final target = _personas[index];
    final activePersonaCount = _personas
        .where((item) => item['status'] != 'retired')
        .length;
    final reason = target['isPrimary'] == true
        ? 'blocked_primary_persona'
        : target['status'] == 'retired'
        ? 'blocked_retired_persona'
        : activePersonaCount <= 1
        ? 'blocked_last_persona'
        : target['isActive'] == true
        ? 'blocked_active_persona'
        : 'allowed';
    return PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
      PersonaLifecycleGuardWireDto.fromMap(<String, dynamic>{
        'subAccountId': subAccountId,
        'requestedAction': 'retire',
        'allowed': reason == 'allowed',
        'reason': reason,
        'requiresSuccessor': reason == 'blocked_active_persona',
      }),
    );
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    return _personaItemsWithCurrentProfile()
        .map(
          (m) => PersonaManagementItemViewData.fromPersonaManagementItemWire(
            PersonaManagementItemWireDto.fromMap(m),
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<SubAccountProfileViewData> getSubAccountProfile(
    String subAccountId,
  ) async {
    final wire = resolveMockUserProfileWire(subAccountId);
    return SubAccountProfileViewData.fromSubAccountProfileWire(wire);
  }

  /// Persona 生命周期命令与查询共享同一份内存 seed；receipt 与 Remote 同形。
  List<Map<String, dynamic>> get _personas => _mockPersonas;

  @override
  Future<contracts.PersonaManagementItem> createPersona(
    contracts.CreatePersonaCommand command,
  ) async {
    final generatedSubAccountId =
        'persona_${command.displayName.hashCode.abs()}';
    final generatedHandle = 'qw${generatedSubAccountId.hashCode.abs()}';
    final item = <String, dynamic>{
      'subAccountId': generatedSubAccountId,
      'displayName': command.displayName,
      'userHandle': generatedHandle,
      'phone': _personas.first['phone'] ?? '',
      'email': _personas.first['email'] ?? '',
      'isolationLevel': command.isolationLevel ?? 'open',
      'profileVisibility': 'public',
      'isPrimary': false,
      'isActive': false,
      'status': 'active',
      'inheritsProfileFromOwner': true,
      'overriddenProfileFields': const <String>[],
      'updatedAt': DateTime.now().toUtc().toIso8601String(),
    };
    _personas.add(item);
    return contracts.decodePersonaManagementItem(item);
  }

  @override
  Future<contracts.PersonaManagementItem> updatePersona(
    contracts.UpdatePersonaCommand command,
  ) async {
    final index = _indexOf(command.subAccountId);
    final previous = _personas[index];
    final next = <String, dynamic>{
      ...previous,
      'displayName': command.displayName ?? previous['displayName'],
      'phone': command.phone ?? previous['phone'] ?? '',
      'email': command.email ?? previous['email'] ?? '',
      'avatarUrl': command.avatarUrl ?? previous['avatarUrl'] ?? '',
      'isolationLevel':
          command.isolationLevel ?? previous['isolationLevel'] ?? 'open',
      'inheritsProfileFromOwner': false,
      'overriddenProfileFields': command.fieldsMask ?? const <String>[],
      'updatedAt': DateTime.now().toUtc().toIso8601String(),
    };
    _personas[index] = next;
    return contracts.decodePersonaManagementItem(next);
  }

  @override
  Future<contracts.PersonaProfileSyncResult> applyPersonaProfileSync(
    contracts.ApplyPersonaProfileSyncCommand command,
  ) async {
    final targets = command.syncTargetIds ?? const <String>[];
    return contracts.PersonaProfileSyncResult(
      status: 'ok',
      appliedCount: targets.isEmpty ? 1 : targets.length,
      fieldsMask: command.fieldsMask ?? const <String>[],
    );
  }

  @override
  Future<contracts.PersonaLifecycleGuard> retirePersona(
    contracts.RetirePersonaCommand command,
  ) async {
    final index = _indexOf(command.subAccountId);
    if (_personas[index]['isPrimary'] == true) {
      throw StateError('primary persona cannot be retired');
    }
    _personas[index] = <String, dynamic>{
      ..._personas[index],
      'isActive': false,
      'status': 'retired',
      'retiredAt': DateTime.now().toUtc().toIso8601String(),
    };
    return contracts.PersonaLifecycleGuard(
      subAccountId: command.subAccountId,
      requestedAction: 'retire',
      allowed: true,
      reason: 'allowed',
      requiresSuccessor: false,
    );
  }

  @override
  Future<contracts.ActivePersonaContext> activatePersona(
    contracts.ActivatePersonaCommand command,
  ) async {
    final index = _indexOf(command.subAccountId);
    for (var i = 0; i < _personas.length; i++) {
      _personas[i] = <String, dynamic>{..._personas[i], 'isActive': i == index};
    }
    return contracts.ActivePersonaContext(
      ownerUserId: kMockCurrentOwnerId,
      subAccountId: command.subAccountId,
      isolationLevel: (_personas[index]['isolationLevel'] as String?) ?? 'open',
      profileVisibility:
          (_personas[index]['profileVisibility'] as String?) ?? 'public',
      contextVersion: 1,
      personaSnapshotVersion: 1,
      explicitOverride: true,
      switchedAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  int _indexOf(String subAccountId) {
    final index = _personas.indexWhere(
      (item) => item['subAccountId'] == subAccountId,
    );
    if (index < 0) {
      throw StateError('persona not found');
    }
    return index;
  }
}
