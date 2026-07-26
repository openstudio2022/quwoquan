import 'package:quwoquan_app/application/user/persona/persona_query.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

import 'persona_lifecycle_test_support.dart';

/// Persona Facet 的 test-only 强类型种子。
final class TestPersonaSeed {
  const TestPersonaSeed({
    required this.subAccountId,
    required this.displayName,
    required this.userHandle,
    this.phone = '',
    this.email = '',
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

  final String subAccountId;
  final String displayName;
  final String userHandle;
  final String phone;
  final String email;
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
      subAccountId: subAccountId,
      displayName: displayName,
      userHandle: userHandle,
      phone: phone,
      email: email,
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
        subAccountId: 'persona_primary',
        displayName: '主分身',
        userHandle: 'main_handle',
        phone: '13800000000',
        email: 'main@example.com',
        avatarUrl: 'media/avatar/s/mock/user/primary/v1/avatar.png',
        isPrimary: true,
        isActive: true,
      ),
      TestPersonaSeed(
        subAccountId: 'persona_photo',
        displayName: '摄影分身',
        userHandle: 'photo_handle',
        phone: '13800000000',
        email: 'photo@example.com',
        avatarUrl: 'media/avatar/s/mock/user/photo/v1/avatar.png',
        isolationLevel: 'semi',
        inheritsProfileFromOwner: false,
        overriddenProfileFields: <String>['email'],
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
        maxSubAccounts: 5,
        usedSubAccounts: _items.length,
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
    String subAccountId,
  ) async {
    final item = _item(subAccountId);
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
      subAccountId: subAccountId,
      requestedAction: 'retire',
      allowed: reason == 'allowed',
      reason: reason,
      requiresSuccessor: reason == 'blocked_active_persona',
    );
  }

  @override
  Future<SubAccountProfileViewData> getSubAccountProfile(
    String subAccountId,
  ) async {
    final item = _item(subAccountId);
    return SubAccountProfileViewData(
      subAccountId: item.subAccountId,
      ownerUserId: 'owner-test',
      subjectType: 'persona',
      userHandle: item.userHandle,
      username: item.userHandle,
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
  Future<contracts.PersonaManagementItem> createPersona(
    contracts.CreatePersonaCommand command,
  ) async {
    final id = 'persona-test-${++_version}';
    final item = _TestPersonaRecord(
      subAccountId: id,
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
  Future<contracts.PersonaManagementItem> updatePersona(
    contracts.UpdatePersonaCommand command,
  ) async {
    final item = _item(command.subAccountId);
    final changedFields = <String>[];
    if (command.displayName != null) {
      item.displayName = command.displayName!;
      changedFields.add('displayName');
    }
    if (command.phone != null) {
      item.phone = command.phone!;
      changedFields.add('phone');
    }
    if (command.email != null) {
      item.email = command.email!;
      changedFields.add('email');
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
    final item = _item(command.subAccountId);
    final targets = command.syncTargetIds ?? const <String>[];
    syncAppliedCount += 1;
    item.lastProfileSyncAt = DateTime.parse(_now());
    item.lastProfileSyncSource = command.subAccountId;
    _version += 1;
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
    final item = _item(command.subAccountId);
    final guard = await getPersonaLifecycleGuard(command.subAccountId);
    if (!guard.allowed) {
      throw personaLifecycleGuardExceptionForReason(guard.reason);
    }
    item.status = 'retired';
    item.isActive = false;
    item.retiredAt = DateTime.parse(_now());
    _version += 1;
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
    final target = _item(command.subAccountId);
    if (target.status == 'retired') {
      throw personaLifecycleGuardExceptionForReason('blocked_retired_persona');
    }
    for (final item in _items) {
      item.isActive = identical(item, target);
    }
    target.lastActivatedAt = DateTime.parse(_now());
    _version += 1;
    return contracts.ActivePersonaContext(
      ownerUserId: 'owner-test',
      subAccountId: target.subAccountId,
      isolationLevel: target.isolationLevel,
      profileVisibility: target.profileVisibility,
      contextVersion: _version,
      personaSnapshotVersion: _version,
      explicitOverride: true,
      switchedAt: _now(),
    );
  }

  _TestPersonaRecord _item(String subAccountId) {
    if (subAccountId.trim().isEmpty) {
      throw ArgumentError.value(subAccountId, 'subAccountId');
    }
    for (final item in _items) {
      if (item.subAccountId == subAccountId) {
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
      subAccountId: item.subAccountId,
      displayName: item.displayName,
      userHandle: item.userHandle,
      phone: item.phone,
      email: item.email,
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
      subAccountId: item.subAccountId,
      ownerUserId: 'owner-test',
      subjectType: 'persona',
      displayName: item.displayName,
      avatarUrl: item.avatarUrl,
      avatarVersion: 1,
      contextVersion: _version,
      isPrimary: item.isPrimary,
    );
  }

  contracts.PersonaManagementItem _contract(_TestPersonaRecord item) {
    return contracts.PersonaManagementItem(
      subAccountId: item.subAccountId,
      displayName: item.displayName,
      userHandle: item.userHandle,
      phone: item.phone,
      email: item.email,
      avatarUrl: item.avatarUrl,
      backgroundUrl: item.backgroundUrl,
      bio: item.bio,
      isolationLevel: item.isolationLevel,
      isActive: item.isActive,
      isPrimary: item.isPrimary,
      status: item.status,
      retiredAt: item.retiredAt?.toIso8601String(),
      inheritsProfileFromOwner: item.inheritsProfileFromOwner,
      overriddenProfileFields: item.overriddenProfileFields,
      lastProfileSyncAt: item.lastProfileSyncAt?.toIso8601String(),
      lastProfileSyncSource: item.lastProfileSyncSource,
      profileVisibility: item.profileVisibility,
      updatedAt: item.updatedAt,
      lastActivatedAt: item.lastActivatedAt?.toIso8601String(),
    );
  }

  static String _now() => DateTime.utc(2026, 7, 20).toIso8601String();
}

final class _TestPersonaRecord {
  _TestPersonaRecord({
    required this.subAccountId,
    required this.displayName,
    required this.userHandle,
    this.phone = '',
    this.email = '',
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
      subAccountId: seed.subAccountId,
      displayName: seed.displayName,
      userHandle: seed.userHandle,
      phone: seed.phone,
      email: seed.email,
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

  final String subAccountId;
  String displayName;
  final String userHandle;
  String phone;
  String email;
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
