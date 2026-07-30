// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-002
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/user/persona/persona_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/active_persona_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/persona_management_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../support/fakes/persona_lifecycle_test_support.dart';

/// 读投影与命令 writer 共享的旅程状态：命令产生的变更必须能被
/// 下一次读投影观察到（命令-读一体性）。
class _JourneyPersonaStore {
  _JourneyPersonaStore(List<Map<String, dynamic>> seed)
    : items = seed
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: true);

  final List<Map<String, dynamic>> items;
  int syncAppliedCount = 0;
  int revision = 1;

  String get activePersonaId => items
      .firstWhere((item) => item['isActive'] == true)['personaId']
      .toString();

  Map<String, dynamic> persona(String personaId) =>
      items.firstWhere((item) => item['personaId'] == personaId);
}

class _JourneyUserRepository implements PersonaQuery {
  _JourneyUserRepository(this.store);

  final _JourneyPersonaStore store;

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    final active = store.persona(store.activePersonaId);
    return ActivePersonaContextViewData.fromActivePersonaContextWire(
      ActivePersonaContextWireDto.fromMap(<String, dynamic>{
        'ownerUserId': 'owner_persona',
        'personaId': active['personaId'],
        'subjectType': 'persona',
        'displayName': active['displayName'],
        'avatarUrl': active['avatarUrl'],
        'avatarVersion': active['avatarVersion'],
        'personaContextVersion': 'ctx_${store.revision}',
        'personaSnapshotVersion': store.revision,
        'sourceSurfaceId': 'journey.persona_management',
        'explicitOverride':
            !(active['inheritsProfileFromOwner'] as bool? ?? false),
        'isPrimary': active['isPrimary'] == true,
      }),
    );
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) async {
    final target = store.persona(personaId);
    final isPrimary = target['isPrimary'] == true;
    final isRetired = target['status'] == 'retired';
    final isActive = target['isActive'] == true;
    final activePersonaCount = store.items
        .where((item) => item['status'] != 'retired')
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
  Future<PersonaProfileViewData> getPersonaProfile(String personaId) =>
      throw UnsupportedError('not used by persona management journey');

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    return PersonaManagementSummaryViewData(
      items: store.items
          .map(
            (item) =>
                PersonaManagementItemViewData.fromPersonaManagementItemWire(
                  PersonaManagementItemWireDto.fromMap(item),
                ),
          )
          .toList(growable: false),
      quota: PersonaManagementQuotaViewData(
        maxPersonas: 5,
        usedPersonas: store.items.length,
      ),
      activeContext: await getActivePersonaContext(),
    );
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    return store.items
        .map(
          (item) => PersonaManagementItemViewData.fromPersonaManagementItemWire(
            PersonaManagementItemWireDto.fromMap(item),
          ),
        )
        .toList(growable: false);
  }
}

class _JourneyPersonaCommandWriter
    implements contracts.PersonaManagementCommandWriter {
  _JourneyPersonaCommandWriter(this.store);

  final _JourneyPersonaStore store;

  @override
  Future<contracts.PersonaManagementItem> createPersona(
    contracts.CreatePersonaCommand command,
  ) async {
    final created = <String, dynamic>{
      'personaId': 'created_persona',
      'displayName': command.displayName,
      'userHandle': 'qw_created_persona',
      'avatarUrl': 'media/avatar/s/mock/user/created_persona/v1/avatar.png',
      'avatarVersion': 1,
      'isolationLevel': command.isolationLevel ?? 'open',
      'profileVisibility': 'public',
      'isPrimary': false,
      'isActive': false,
      'status': 'active',
      'inheritsProfileFromOwner': true,
      'overriddenProfileFields': const <String>[],
      'updatedAt': DateTime.utc(2026, 6, 21, 12).toIso8601String(),
    };
    store.items.add(created);
    store.revision++;
    return contracts.decodePersonaManagementItem(created);
  }

  @override
  Future<contracts.PersonaManagementItem> updatePersona(
    contracts.UpdatePersonaCommand command,
  ) async {
    final target = store.persona(command.personaId);
    final changedFields = <String>[
      if (command.displayName != null) 'displayName',
    ];
    if (command.displayName != null) {
      target['displayName'] = command.displayName;
    }
    if (command.avatarUrl != null) target['avatarUrl'] = command.avatarUrl;
    if (command.isolationLevel != null) {
      target['isolationLevel'] = command.isolationLevel;
    }
    target['inheritsProfileFromOwner'] = false;
    target['overriddenProfileFields'] = changedFields;
    target['updatedAt'] = DateTime.utc(2026, 6, 21, 12).toIso8601String();
    store.revision++;
    return contracts.decodePersonaManagementItem(target);
  }

  @override
  Future<contracts.PersonaProfileSyncResult> applyPersonaProfileSync(
    contracts.ApplyPersonaProfileSyncCommand command,
  ) async {
    store.syncAppliedCount++;
    final source = store.persona(command.personaId);
    final syncTargetIds = command.syncTargetIds ?? const <String>[];
    final fieldsMask = command.fieldsMask ?? const <String>[];
    final targets = syncTargetIds.isEmpty
        ? store.items.where((item) => item['personaId'] != command.personaId)
        : store.items.where(
            (item) => syncTargetIds.contains(item['personaId']),
          );
    for (final target in targets) {
      for (final field in fieldsMask) {
        target[field] = source[field];
      }
      target['inheritsProfileFromOwner'] = false;
      target['overriddenProfileFields'] = fieldsMask;
      target['lastProfileSyncAt'] = DateTime.utc(
        2026,
        6,
        21,
        12,
      ).toIso8601String();
      target['lastProfileSyncSource'] = 'manual_sync';
    }
    store.revision++;
    return contracts.PersonaProfileSyncResult(
      status: 'ok',
      appliedCount: syncTargetIds.isEmpty
          ? store.items.length - 1
          : syncTargetIds.length,
      fieldsMask: fieldsMask,
    );
  }

  @override
  Future<contracts.PersonaLifecycleGuard> retirePersona(
    contracts.RetirePersonaCommand command,
  ) async {
    final target = store.persona(command.personaId);
    final guard = await _JourneyUserRepository(
      store,
    ).getPersonaLifecycleGuard(command.personaId);
    if (!guard.allowed) {
      throw personaLifecycleGuardExceptionForReason(guard.reason);
    }
    target['status'] = 'retired';
    target['retiredAt'] = DateTime.utc(2026, 6, 21, 12).toIso8601String();
    target['isActive'] = false;
    store.revision++;
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
    final target = store.persona(command.personaId);
    if (target['status'] == 'retired') {
      throw personaLifecycleGuardExceptionForReason('blocked_retired_persona');
    }
    for (final item in store.items) {
      item['isActive'] = item['personaId'] == command.personaId;
    }
    store.revision++;
    return contracts.ActivePersonaContext(
      ownerUserId: 'owner_persona',
      personaId: command.personaId,
      isolationLevel: 'open',
      profileVisibility: 'public',
      contextVersion: store.revision,
      personaSnapshotVersion: store.revision,
      explicitOverride: true,
      switchedAt: DateTime.utc(2026, 6, 21, 12).toIso8601String(),
    );
  }
}

Widget _wrap(_JourneyPersonaStore store) {
  return ProviderScope(
    overrides: [
      personaQueryProvider.overrideWith(
        (ref, surface) => _JourneyUserRepository(store),
      ),
      personaCommandWriterProvider.overrideWithValue(
        _JourneyPersonaCommandWriter(store),
      ),
    ],
    child: const CupertinoApp(home: PersonaManagementPage()),
  );
}

List<Map<String, dynamic>> _seed() {
  return <Map<String, dynamic>>[
    <String, dynamic>{
      'personaId': 'persona_primary',
      'displayName': '主分身',
      'userHandle': 'main_handle',
      'avatarUrl':
          'media/avatar/s/mock/user/persona/persona_primary/v1/avatar.png',
      'avatarVersion': 1,
      'isPrimary': true,
      'isActive': true,
      'isolationLevel': 'open',
      'profileVisibility': 'public',
      'inheritsProfileFromOwner': true,
      'status': 'active',
      'overriddenProfileFields': const <String>[],
    },
    <String, dynamic>{
      'personaId': 'persona_photo',
      'displayName': '摄影分身',
      'userHandle': 'photo_handle',
      'avatarUrl':
          'media/avatar/s/mock/user/persona/persona_photo/v1/avatar.png',
      'avatarVersion': 2,
      'isPrimary': false,
      'isActive': false,
      'isolationLevel': 'semi',
      'profileVisibility': 'public',
      'inheritsProfileFromOwner': false,
      'status': 'active',
      'overriddenProfileFields': const <String>['displayName'],
    },
  ];
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('分身管理页支持编辑、同步建议应用与切换当前分身', (tester) async {
    final store = _JourneyPersonaStore(_seed());
    await tester.pumpWidget(_wrap(store));
    await tester.pumpAndSettle();

    expect(store.activePersonaId, 'persona_primary');

    final primaryStatus = find.byKey(
      const ValueKey<String>('persona-status-persona_primary'),
    );
    final photoStatus = find.byKey(
      const ValueKey<String>('persona-status-persona_photo'),
    );

    expect(
      find.descendant(
        of: primaryStatus,
        matching: find.text(ProfileText.personaCurrentUsing),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: photoStatus,
        matching: find.text(ProfileText.personaCurrentUsing),
      ),
      findsNothing,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('persona-edit-persona_primary')),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(CupertinoTextField).at(0),
      'main_synced',
    );
    await tester.tap(find.text(ProfileText.editProfileSaveAction));
    await tester.pumpAndSettle();

    expect(find.text(ProfileText.personaSyncSuggestionTitle), findsOneWidget);

    await tester.tap(find.text(ProfileText.personaSyncApplyAll));
    await tester.pumpAndSettle();

    expect(store.syncAppliedCount, 1);
    expect(store.persona('persona_photo')['displayName'], 'main_synced');
    expect(store.persona('persona_photo')['userHandle'], 'photo_handle');
    expect(find.text(ProfileText.personaSyncSuggestionTitle), findsNothing);

    await tester.tap(
      find.byKey(const ValueKey<String>('persona-activate-persona_photo')),
    );
    await tester.pumpAndSettle();

    expect(store.activePersonaId, 'persona_photo');
    expect(
      find.descendant(
        of: primaryStatus,
        matching: find.text(ProfileText.personaCurrentUsing),
      ),
      findsNothing,
    );
    expect(
      find.descendant(
        of: photoStatus,
        matching: find.text(ProfileText.personaCurrentUsing),
      ),
      findsOneWidget,
    );
  });

  testWidgets('退役分身保留身份归因且不再暴露重复退役动作', (tester) async {
    final store = _JourneyPersonaStore(_seed());
    await tester.pumpWidget(_wrap(store));
    await tester.pumpAndSettle();

    await tester.tap(find.text(ProfileText.personaRetire));
    await tester.pumpAndSettle();
    await tester.tap(
      find.widgetWithText(CupertinoDialogAction, ProfileText.personaRetire),
    );
    await tester.pumpAndSettle();

    expect(store.items, hasLength(2));
    expect(store.persona('persona_photo')['status'], 'retired');
    expect(
      find.descendant(
        of: find.byKey(const ValueKey<String>('persona-status-persona_photo')),
        matching: find.text(ProfileText.personaRetired),
      ),
      findsOneWidget,
    );
    expect(find.text(ProfileText.personaRetire), findsNothing);
  });
}
