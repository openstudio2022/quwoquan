import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_management_view_data_mapper.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

import 'persona_lifecycle_test_support.dart';

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
    return personaProfileViewDataFromWire(_profileContract(item));
  }

  @override
  Future<contracts.PersonaManagementItemView> createPersona(
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
  Future<contracts.PersonaManagementItemView> updatePersona(
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
  Future<contracts.PersonaLifecycleGuardView> retirePersona(
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
    return contracts.PersonaLifecycleGuardView(
      personaId: command.personaId,
      requestedAction: contracts.PersonaLifecycleAction.retire,
      allowed: true,
      reason: contracts.PersonaLifecycleGuardReason.allowed,
      requiresSuccessor: false,
    );
  }

  @override
  Future<contracts.ActivePersonaContextView> activatePersona(
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
    return _activeContextContract(target, explicitOverride: true);
  }

  Map<String, Object?> _item(String id) {
    if (id.trim().isEmpty) throw ArgumentError.value(id, 'personaId');
    for (final item in _items) {
      if (item['personaId'] == id) return item;
    }
    throw StateError('persona not found');
  }

  PersonaManagementItemViewData _view(Map<String, Object?> item) =>
      personaManagementItemViewDataFromWire(_contract(item));

  contracts.PersonaManagementItemView _contract(Map<String, Object?> item) =>
      contracts.PersonaManagementItemView(
        personaId: item['personaId']! as String,
        displayName: item['displayName']! as String,
        userHandle: item['userHandle']! as String,
        avatarUrl: item['avatarUrl']! as String,
        backgroundUrl: item['backgroundUrl']! as String,
        bio: item['bio']! as String,
        isolationLevel: contracts.IsolationLevel.fromWire(
          item['isolationLevel'],
          'PersonaManagementItemView.isolationLevel',
        ),
        isPrimary: item['isPrimary']! as bool,
        isActive: item['isActive']! as bool,
        status: contracts.PersonaStatus.fromWire(
          item['status'],
          'PersonaManagementItemView.status',
        ),
        retiredAt: _optionalDate(item['retiredAt']),
        inheritsProfileFromOwner: item['inheritsProfileFromOwner']! as bool,
        overriddenProfileFields:
            (item['overriddenProfileFields']! as List<Object?>).cast<String>(),
        lastProfileSyncAt: _optionalDate(item['lastProfileSyncAt']),
        lastProfileSyncSource: item['lastProfileSyncSource'] as String?,
        profileVisibility: contracts.ProfileVisibility.fromWire(
          item['profileVisibility'],
          'PersonaManagementItemView.profileVisibility',
        ),
        purposeHint: item['purposeHint'] as String?,
        updatedAt: _requiredDate(item['updatedAt']),
        lastActivatedAt: _optionalDate(item['lastActivatedAt']),
      );

  contracts.PersonaProfileView _profileContract(Map<String, Object?> item) =>
      contracts.PersonaProfileView(
        personaId: item['personaId']! as String,
        subjectType: contracts.ProfileOwnerKind.persona,
        userHandle: item['userHandle']! as String,
        displayName: item['displayName']! as String,
        nicknameCustomized: item['inheritsProfileFromOwner'] != true,
        avatarUrl: item['avatarUrl']! as String,
        backgroundUrl: item['backgroundUrl']! as String,
        bio: item['bio']! as String,
        identityTags: const <String>[],
        followerCount: 0,
        followingCount: 0,
        postCount: 0,
        circleCount: 0,
        likeCount: 0,
        profileVisibility: contracts.ProfileVisibility.fromWire(
          item['profileVisibility'],
          'PersonaProfileView.profileVisibility',
        ),
        isolationLevel: contracts.IsolationLevel.fromWire(
          item['isolationLevel'],
          'PersonaProfileView.isolationLevel',
        ),
        inheritsFromOwner: item['inheritsProfileFromOwner']! as bool,
        overriddenFields: (item['overriddenProfileFields']! as List<Object?>)
            .cast<String>(),
        updatedAt: _requiredDate(item['updatedAt']),
      );

  ActivePersonaContextViewData _activeContextView(Map<String, Object?> item) =>
      activePersonaContextViewDataFromWire(
        _activeContextContract(
          item,
          explicitOverride: item['inheritsProfileFromOwner'] != true,
        ),
      );

  contracts.ActivePersonaContextView _activeContextContract(
    Map<String, Object?> item, {
    required bool explicitOverride,
  }) => contracts.ActivePersonaContextView(
    ownerUserId: 'owner-test',
    personaId: item['personaId']! as String,
    subjectType: contracts.ProfileOwnerKind.persona,
    displayName: item['displayName']! as String,
    avatarUrl: item['avatarUrl']! as String,
    avatarVersion: 1,
    isPrimary: item['isPrimary']! as bool,
    isolationLevel: contracts.IsolationLevel.fromWire(
      item['isolationLevel'],
      'ActivePersonaContextView.isolationLevel',
    ),
    profileVisibility: contracts.ProfileVisibility.fromWire(
      item['profileVisibility'],
      'ActivePersonaContextView.profileVisibility',
    ),
    contextVersion: _version,
    personaSnapshotVersion: _version,
    sourceSurfaceId: 'test.persona',
    explicitOverride: explicitOverride,
    switchedAt: _requiredDate(item['updatedAt']),
  );

  static DateTime _requiredDate(Object? value) => switch (value) {
    DateTime date => date,
    String text => DateTime.parse(text),
    _ => throw StateError('expected a canonical timestamp'),
  };

  static DateTime? _optionalDate(Object? value) =>
      value == null ? null : _requiredDate(value);

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
