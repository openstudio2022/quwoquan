import 'package:quwoquan_app/application/user/persona/persona_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/active_persona_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_profile_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

import '../fakes/persona_lifecycle_test_support.dart';

/// Persona Query/Command 的测试替身。
///
/// 读写共享同一份内存状态，确保 local_contract 能验证「命令成功后读投影可见」，
/// 而不是分别维护两套互不一致的 fixture。
final class MockPersonaFacets
    implements PersonaQuery, contracts.PersonaManagementCommandWriter {
  MockPersonaFacets({List<Map<String, Object?>>? seed})
    : _items = (seed ?? _defaultSeed())
          .map(Map<String, Object?>.from)
          .toList(growable: true);

  final List<Map<String, Object?>> _items;
  int _version = 1;

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async =>
      _items.map(_view).toList(growable: false);

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    final active = _items.firstWhere((item) => item['isActive'] == true);
    return PersonaManagementSummaryViewData(
      items: _items.map(_view).toList(growable: false),
      quota: PersonaManagementQuotaViewData(
        maxPersonas: 5,
        usedPersonas: _items.length,
      ),
      activeContext: _activeContextView(active),
    );
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return _activeContextView(
      _items.firstWhere((item) => item['isActive'] == true),
    );
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) async {
    final item = _item(personaId);
    final isPrimary = item['isPrimary'] == true;
    final isRetired = item['status'] == 'retired';
    final isActive = item['isActive'] == true;
    final activePersonaCount = _items
        .where((candidate) => candidate['status'] != 'retired')
        .length;
    final reason = isPrimary
        ? 'blocked_primary_persona'
        : isRetired
        ? 'blocked_retired_persona'
        : activePersonaCount <= 1
        ? 'blocked_last_persona'
        : isActive
        ? 'blocked_active_persona'
        : 'allowed';
    return PersonaLifecycleGuardViewData(
      personaId: personaId,
      requestedAction: 'retire',
      allowed: reason == 'allowed',
      reason: reason,
      requiresSuccessor: reason == 'blocked_active_persona',
    );
  }

  @override
  Future<PersonaProfileViewData> getPersonaProfile(String personaId) async {
    final item = _item(personaId);
    return PersonaProfileViewData.fromPersonaProfileWire(
      PersonaProfileWireDto.fromMap(<String, dynamic>{
        ...item,
        'ownerUserId': 'owner-test',
        'subjectType': 'persona',
        'nickname': item['displayName'],
        'status': item['status'] ?? 'active',
      }),
    );
  }

  @override
  Future<contracts.PersonaManagementItem> createPersona(
    contracts.CreatePersonaCommand command,
  ) async {
    final id = 'persona-test-${++_version}';
    final item = <String, Object?>{
      'personaId': id,
      'displayName': command.displayName,
      'userHandle': 'qw_$id',
      'avatarUrl': command.avatarUrl ?? '',
      'backgroundUrl': '',
      'bio': '',
      'isolationLevel': command.isolationLevel ?? 'open',
      'profileVisibility': 'public',
      'isPrimary': false,
      'isActive': false,
      'status': 'active',
      'inheritsProfileFromOwner': true,
      'overriddenProfileFields': const <String>[],
      'updatedAt': _now(),
    };
    _items.add(item);
    return _contract(item);
  }

  @override
  Future<contracts.PersonaManagementItem> updatePersona(
    contracts.UpdatePersonaCommand command,
  ) async {
    final item = _item(command.personaId);
    if (command.displayName != null) {
      item['displayName'] = command.displayName;
    }
    if (command.avatarUrl != null) item['avatarUrl'] = command.avatarUrl;
    if (command.backgroundUrl != null) {
      item['backgroundUrl'] = command.backgroundUrl;
    }
    if (command.isolationLevel != null) {
      item['isolationLevel'] = command.isolationLevel;
    }
    item['inheritsProfileFromOwner'] = false;
    item['overriddenProfileFields'] = command.fieldsMask ?? const <String>[];
    item['updatedAt'] = _now();
    _version++;
    return _contract(item);
  }

  @override
  Future<contracts.PersonaProfileSyncResult> applyPersonaProfileSync(
    contracts.ApplyPersonaProfileSyncCommand command,
  ) async {
    _item(command.personaId);
    final targets = command.syncTargetIds ?? const <String>[];
    _version++;
    return contracts.PersonaProfileSyncResult(
      status: 'ok',
      appliedCount: targets.isEmpty ? _items.length - 1 : targets.length,
      fieldsMask: command.fieldsMask ?? const <String>[],
    );
  }

  @override
  Future<contracts.PersonaLifecycleGuard> retirePersona(
    contracts.RetirePersonaCommand command,
  ) async {
    final item = _item(command.personaId);
    final guard = await getPersonaLifecycleGuard(command.personaId);
    if (!guard.allowed) {
      throw personaLifecycleGuardExceptionForReason(guard.reason);
    }
    item['status'] = 'retired';
    item['isActive'] = false;
    item['retiredAt'] = _now();
    _version++;
    return contracts.PersonaLifecycleGuard(
      personaId: command.personaId,
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
    final target = _item(command.personaId);
    if (target['status'] == 'retired') {
      throw personaLifecycleGuardExceptionForReason('blocked_retired_persona');
    }
    for (final item in _items) {
      item['isActive'] = identical(item, target);
    }
    _version++;
    return contracts.ActivePersonaContext(
      ownerUserId: 'owner-test',
      personaId: command.personaId,
      isolationLevel: target['isolationLevel']! as String,
      profileVisibility: target['profileVisibility']! as String,
      contextVersion: _version,
      personaSnapshotVersion: _version,
      explicitOverride: true,
      switchedAt: _now(),
    );
  }

  Map<String, Object?> _item(String id) {
    if (id.trim().isEmpty) throw ArgumentError.value(id, 'personaId');
    for (final item in _items) {
      if (item['personaId'] == id) return item;
    }
    throw StateError('persona not found');
  }

  PersonaManagementItemViewData _view(Map<String, Object?> item) =>
      PersonaManagementItemViewData.fromPersonaManagementItemWire(
        PersonaManagementItemWireDto.fromMap(Map<String, dynamic>.from(item)),
      );

  contracts.PersonaManagementItem _contract(Map<String, Object?> item) =>
      contracts.decodePersonaManagementItem(item);

  ActivePersonaContextViewData _activeContextView(Map<String, Object?> item) =>
      ActivePersonaContextViewData.fromActivePersonaContextWire(
        ActivePersonaContextWireDto.fromMap(<String, dynamic>{
          'ownerUserId': 'owner-test',
          'personaId': item['personaId'],
          'subjectType': 'persona',
          'displayName': item['displayName'],
          'avatarUrl': item['avatarUrl'],
          'avatarVersion': 1,
          'personaContextVersion': 'ctx-$_version',
          'personaSnapshotVersion': _version,
          'sourceSurfaceId': 'test.persona',
          'explicitOverride': item['inheritsProfileFromOwner'] != true,
          'isPrimary': item['isPrimary'],
        }),
      );

  static List<Map<String, Object?>> _defaultSeed() => <Map<String, Object?>>[
    <String, Object?>{
      'personaId': 'persona_primary',
      'displayName': '主分身',
      'userHandle': 'main_handle',
      'avatarUrl': 'media/avatar/s/mock/user/primary/v1/avatar.png',
      'backgroundUrl': '',
      'bio': '',
      'isolationLevel': 'open',
      'profileVisibility': 'public',
      'isPrimary': true,
      'isActive': true,
      'status': 'active',
      'inheritsProfileFromOwner': true,
      'overriddenProfileFields': const <String>[],
      'updatedAt': _now(),
    },
    <String, Object?>{
      'personaId': 'persona_photo',
      'displayName': '摄影分身',
      'userHandle': 'photo_handle',
      'avatarUrl': 'media/avatar/s/mock/user/photo/v1/avatar.png',
      'backgroundUrl': '',
      'bio': '',
      'isolationLevel': 'semi',
      'profileVisibility': 'friends',
      'isPrimary': false,
      'isActive': false,
      'status': 'active',
      'inheritsProfileFromOwner': false,
      'overriddenProfileFields': const <String>['displayName'],
      'updatedAt': _now(),
    },
  ];

  static String _now() => DateTime.utc(2026, 7, 20).toIso8601String();
}
