import 'package:quwoquan_app/user/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

import 'persona_lifecycle_test_support.dart';

/// Persona Facet 的 test-only 强类型种子。
final class TestPersonaSeed {
  const TestPersonaSeed({
    required this.personaId,
    required this.displayName,
    required this.userHandle,
    this.avatarUrl = '',
    this.backgroundUrl = '',
    this.bio = '',
    this.isolationLevel = 'open',
    this.profileVisibility = 'public',
    this.isPrimary = false,
    this.isActive = false,
    this.status = 'active',
    this.inheritsProfileFromOwner = true,
    this.overriddenProfileFields = const <String>[],
    this.hasPublishedContent = false,
    this.retiredAt,
  });

  final String personaId;
  final String displayName;
  final String userHandle;
  final String avatarUrl;
  final String backgroundUrl;
  final String bio;
  final String isolationLevel;
  final String profileVisibility;
  final bool isPrimary;
  final bool isActive;
  final String status;
  final bool inheritsProfileFromOwner;
  final List<String> overriddenProfileFields;
  final bool hasPublishedContent;
  final DateTime? retiredAt;

  TestPersonaSeed copyWith({String? status, DateTime? retiredAt}) {
    return TestPersonaSeed(
      personaId: personaId,
      displayName: displayName,
      userHandle: userHandle,
      avatarUrl: avatarUrl,
      backgroundUrl: backgroundUrl,
      bio: bio,
      isolationLevel: isolationLevel,
      profileVisibility: profileVisibility,
      isPrimary: isPrimary,
      isActive: isActive,
      status: status ?? this.status,
      inheritsProfileFromOwner: inheritsProfileFromOwner,
      overriddenProfileFields: overriddenProfileFields,
      hasPublishedContent: hasPublishedContent,
      retiredAt: retiredAt ?? this.retiredAt,
    );
  }
}

/// PersonaQuery 与 PersonaManagementCommandWriter 的共享内存 typed fake。
///
/// 读写 Facet 共用同一份强类型状态，命令后的读投影会立即反映变更。
final class TestPersonaFacets
    implements PersonaQuery, contracts.PersonaManagementCommandWriter {
  TestPersonaFacets({List<TestPersonaSeed>? seed, this.summaryFailure})
    : _items = (seed ?? defaultSeed())
          .map(_TestPersonaRecord.fromSeed)
          .toList(growable: true);

  final List<_TestPersonaRecord> _items;
  Object? summaryFailure;
  int summaryLoadCount = 0;
  int syncAppliedCount = 0;
  int _version = 1;

  static List<TestPersonaSeed> defaultSeed() {
    return const <TestPersonaSeed>[
      TestPersonaSeed(
        personaId: 'persona_primary',
        displayName: '主分身',
        userHandle: 'main_handle',
        avatarUrl: 'media/avatar/s/mock/user/primary/v1/avatar.png',
        isPrimary: true,
        isActive: true,
      ),
      TestPersonaSeed(
        personaId: 'persona_photo',
        displayName: '摄影分身',
        userHandle: 'photo_handle',
        avatarUrl: 'media/avatar/s/mock/user/photo/v1/avatar.png',
        isolationLevel: 'semi',
        inheritsProfileFromOwner: false,
        overriddenProfileFields: <String>['displayName'],
      ),
    ];
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    return _items.map(_view).toList(growable: false);
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    summaryLoadCount += 1;
    final failure = summaryFailure;
    if (failure != null) {
      throw failure;
    }
    return PersonaManagementSummaryViewData(
      items: _items.map(_view).toList(growable: false),
      quota: PersonaManagementQuotaViewData(
        maxPersonas: 5,
        usedPersonas: _items.length,
      ),
      activeContext: _activeContextView(_activeItem()),
    );
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return _activeContextView(_activeItem());
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) async {
    final item = _item(personaId);
    final activePersonaCount = _items
        .where((candidate) => candidate.status != 'retired')
        .length;
    final reason = item.isPrimary
        ? 'blocked_primary_persona'
        : item.status == 'retired'
        ? 'blocked_retired_persona'
        : activePersonaCount <= 1
        ? 'blocked_last_persona'
        : item.isActive
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
    return PersonaProfileViewData(
      personaId: item.personaId,
      ownerUserId: 'owner-test',
      subjectType: 'persona',
      userHandle: item.userHandle,
      displayName: item.displayName,
      avatarUrl: item.avatarUrl,
      backgroundUrl: item.backgroundUrl,
      bio: item.bio,
      followerCount: 0,
      followingCount: 0,
      postCount: 0,
      circleCount: 0,
      likeCount: 0,
      isolationLevel: item.isolationLevel,
      profileVisibility: item.profileVisibility,
      inheritsFromOwner: item.inheritsProfileFromOwner,
      overriddenFields: item.overriddenProfileFields,
      updatedAt: DateTime.tryParse(item.updatedAt),
    );
  }

  @override
  Future<contracts.PersonaManagementItemView> createPersona(
    contracts.CreatePersonaCommand command,
  ) async {
    final id = 'persona-test-${++_version}';
    final item = _TestPersonaRecord(
      personaId: id,
      displayName: command.displayName,
      userHandle: 'qw_$id',
      avatarUrl: command.avatarUrl ?? '',
      isolationLevel: command.isolationLevel ?? 'open',
      updatedAt: _now(),
    );
    _items.add(item);
    return _contract(item);
  }

  @override
  Future<contracts.PersonaManagementItemView> updatePersona(
    contracts.UpdatePersonaCommand command,
  ) async {
    final item = _item(command.personaId);
    final changedFields = <String>[];
    if (command.displayName != null) {
      item.displayName = command.displayName!;
      changedFields.add('displayName');
    }
    if (command.avatarUrl != null) {
      item.avatarUrl = command.avatarUrl!;
      changedFields.add('avatarUrl');
    }
    if (command.backgroundUrl != null) {
      item.backgroundUrl = command.backgroundUrl!;
      changedFields.add('backgroundUrl');
    }
    if (command.isolationLevel != null) {
      item.isolationLevel = command.isolationLevel!;
    }
    item.inheritsProfileFromOwner = false;
    item.overriddenProfileFields = List<String>.unmodifiable(
      command.fieldsMask ?? changedFields,
    );
    item.updatedAt = _now();
    _version += 1;
    return _contract(item);
  }

  @override
  Future<contracts.PersonaProfileSyncResult> applyPersonaProfileSync(
    contracts.ApplyPersonaProfileSyncCommand command,
  ) async {
    final item = _item(command.personaId);
    final targets = command.syncTargetIds ?? const <String>[];
    syncAppliedCount += 1;
    item.lastProfileSyncAt = DateTime.parse(_now());
    item.lastProfileSyncSource = command.personaId;
    _version += 1;
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
    item.status = 'retired';
    item.isActive = false;
    item.retiredAt = DateTime.parse(_now());
    _version += 1;
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
    if (target.status == 'retired') {
      throw personaLifecycleGuardExceptionForReason('blocked_retired_persona');
    }
    for (final item in _items) {
      item.isActive = identical(item, target);
    }
    target.lastActivatedAt = DateTime.parse(_now());
    _version += 1;
    return contracts.ActivePersonaContextView(
      ownerUserId: 'owner-test',
      personaId: target.personaId,
      subjectType: contracts.ProfileOwnerKind.persona,
      displayName: target.displayName,
      avatarUrl: target.avatarUrl,
      avatarVersion: 1,
      isPrimary: target.isPrimary,
      isolationLevel: contracts.IsolationLevel.fromWire(
        target.isolationLevel,
        'ActivePersonaContextView.isolationLevel',
      ),
      profileVisibility: contracts.ProfileVisibility.fromWire(
        target.profileVisibility,
        'ActivePersonaContextView.profileVisibility',
      ),
      contextVersion: _version,
      personaSnapshotVersion: _version,
      explicitOverride: true,
      switchedAt: DateTime.parse(_now()),
    );
  }

  _TestPersonaRecord _item(String personaId) {
    if (personaId.trim().isEmpty) {
      throw ArgumentError.value(personaId, 'personaId');
    }
    for (final item in _items) {
      if (item.personaId == personaId) {
        return item;
      }
    }
    throw StateError('persona not found');
  }

  _TestPersonaRecord _activeItem() {
    for (final item in _items) {
      if (item.isActive) {
        return item;
      }
    }
    final primary = _primaryItem();
    primary.isActive = true;
    return primary;
  }

  _TestPersonaRecord _primaryItem() {
    for (final item in _items) {
      if (item.isPrimary) {
        return item;
      }
    }
    throw StateError('primary persona not found');
  }

  PersonaManagementItemViewData _view(_TestPersonaRecord item) {
    return PersonaManagementItemViewData(
      personaId: item.personaId,
      displayName: item.displayName,
      userHandle: item.userHandle,
      avatarUrl: item.avatarUrl,
      isolationLevel: item.isolationLevel,
      profileVisibility: item.profileVisibility,
      isPrimary: item.isPrimary,
      isActive: item.isActive,
      status: item.status,
      retiredAt: item.retiredAt,
      hasPublishedContent: item.hasPublishedContent,
      inheritsProfileFromOwner: item.inheritsProfileFromOwner,
      overriddenProfileFields: item.overriddenProfileFields,
      lastProfileSyncAt: item.lastProfileSyncAt,
      lastProfileSyncSource: item.lastProfileSyncSource,
      lastActivatedAt: item.lastActivatedAt,
      subjectType: 'persona',
    );
  }

  ActivePersonaContextViewData _activeContextView(_TestPersonaRecord item) {
    return ActivePersonaContextViewData(
      personaId: item.personaId,
      ownerUserId: 'owner-test',
      subjectType: 'persona',
      displayName: item.displayName,
      avatarUrl: item.avatarUrl,
      avatarVersion: 1,
      contextVersion: _version,
      isPrimary: item.isPrimary,
    );
  }

  contracts.PersonaManagementItemView _contract(_TestPersonaRecord item) {
    return contracts.PersonaManagementItemView(
      personaId: item.personaId,
      displayName: item.displayName,
      userHandle: item.userHandle,
      avatarUrl: item.avatarUrl,
      backgroundUrl: item.backgroundUrl,
      bio: item.bio,
      isolationLevel: contracts.IsolationLevel.fromWire(
        item.isolationLevel,
        'PersonaManagementItemView.isolationLevel',
      ),
      isActive: item.isActive,
      isPrimary: item.isPrimary,
      status: contracts.PersonaStatus.fromWire(
        item.status,
        'PersonaManagementItemView.status',
      ),
      retiredAt: item.retiredAt,
      inheritsProfileFromOwner: item.inheritsProfileFromOwner,
      overriddenProfileFields: item.overriddenProfileFields,
      lastProfileSyncAt: item.lastProfileSyncAt,
      lastProfileSyncSource: item.lastProfileSyncSource,
      profileVisibility: contracts.ProfileVisibility.fromWire(
        item.profileVisibility,
        'PersonaManagementItemView.profileVisibility',
      ),
      updatedAt: DateTime.parse(item.updatedAt),
      lastActivatedAt: item.lastActivatedAt,
    );
  }

  static String _now() => DateTime.utc(2026, 7, 20).toIso8601String();
}

final class _TestPersonaRecord {
  _TestPersonaRecord({
    required this.personaId,
    required this.displayName,
    required this.userHandle,
    this.avatarUrl = '',
    this.backgroundUrl = '',
    this.bio = '',
    this.isolationLevel = 'open',
    this.profileVisibility = 'public',
    this.isPrimary = false,
    this.isActive = false,
    this.status = 'active',
    this.inheritsProfileFromOwner = true,
    this.overriddenProfileFields = const <String>[],
    this.hasPublishedContent = false,
    this.retiredAt,
    required this.updatedAt,
  });

  factory _TestPersonaRecord.fromSeed(TestPersonaSeed seed) {
    return _TestPersonaRecord(
      personaId: seed.personaId,
      displayName: seed.displayName,
      userHandle: seed.userHandle,
      avatarUrl: seed.avatarUrl,
      backgroundUrl: seed.backgroundUrl,
      bio: seed.bio,
      isolationLevel: seed.isolationLevel,
      profileVisibility: seed.profileVisibility,
      isPrimary: seed.isPrimary,
      isActive: seed.isActive,
      status: seed.status,
      inheritsProfileFromOwner: seed.inheritsProfileFromOwner,
      overriddenProfileFields: List<String>.unmodifiable(
        seed.overriddenProfileFields,
      ),
      hasPublishedContent: seed.hasPublishedContent,
      retiredAt: seed.retiredAt,
      updatedAt: DateTime.utc(2026, 7, 20).toIso8601String(),
    );
  }

  final String personaId;
  String displayName;
  final String userHandle;
  String avatarUrl;
  String backgroundUrl;
  final String bio;
  String isolationLevel;
  final String profileVisibility;
  final bool isPrimary;
  bool isActive;
  String status;
  bool inheritsProfileFromOwner;
  List<String> overriddenProfileFields;
  final bool hasPublishedContent;
  DateTime? retiredAt;
  DateTime? lastProfileSyncAt;
  String lastProfileSyncSource = '';
  DateTime? lastActivatedAt;
  String updatedAt;
}
