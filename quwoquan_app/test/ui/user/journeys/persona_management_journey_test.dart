import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_setting_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/persona_management_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _JourneyUserRepository implements UserRepository {
  _JourneyUserRepository(List<Map<String, dynamic>> seed)
    : _items = seed
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: true);

  final List<Map<String, dynamic>> _items;
  int syncAppliedCount = 0;
  int _revision = 1;

  String get activeSubAccountId => _items
      .firstWhere((item) => item['isActive'] == true)['subAccountId']
      .toString();

  Map<String, dynamic> persona(String subAccountId) =>
      _items.firstWhere((item) => item['subAccountId'] == subAccountId);

  @override
  Future<void> activatePersona(String subAccountId) async {
    for (final item in _items) {
      item['isActive'] = item['subAccountId'] == subAccountId;
    }
    _revision++;
  }

  @override
  Future<int> applyPersonaProfileSync(
    String subAccountId, {
    required List<String> fieldsMask,
    String applyScope = 'all_sub_accounts',
    List<String> syncTargetIds = const <String>[],
  }) async {
    syncAppliedCount++;
    final source = persona(subAccountId);
    final targets = syncTargetIds.isEmpty
        ? _items.where((item) => item['subAccountId'] != subAccountId)
        : _items.where((item) => syncTargetIds.contains(item['subAccountId']));
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
    _revision++;
    return syncTargetIds.isEmpty ? _items.length - 1 : syncTargetIds.length;
  }

  @override
  Future<PersonaManagementItemViewData> createPersona({
    required String displayName,
    String? userHandle,
    String isolationLevel = 'open',
    String? purposeHint,
  }) async {
    final created = <String, dynamic>{
      'subAccountId': 'created_persona',
      'displayName': displayName,
      'userHandle': userHandle ?? '',
      'phone': '',
      'email': '',
      'avatarUrl': 'media/avatar/s/mock/user/created_persona/v1/avatar.png',
      'avatarVersion': 1,
      'isolationLevel': isolationLevel,
      'profileVisibility': 'public',
      'isPrimary': false,
      'isActive': false,
      'status': 'active',
      'inheritsProfileFromOwner': true,
      'overriddenProfileFields': const <String>[],
    };
    _items.add(created);
    _revision++;
    return PersonaManagementItemViewData.fromMap(created);
  }

  @override
  Future<void> deleteEmptyPersona(String subAccountId) async {
    _items.removeWhere((item) => item['subAccountId'] == subAccountId);
    _revision++;
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    final active = persona(activeSubAccountId);
    return ActivePersonaContextViewData.fromMap(<String, dynamic>{
      'ownerUserId': 'owner_persona',
      'subAccountId': active['subAccountId'],
      'subjectType': 'persona',
      'displayName': active['displayName'],
      'avatarUrl': active['avatarUrl'],
      'avatarVersion': active['avatarVersion'],
      'personaContextVersion': 'ctx_$_revision',
      'personaSnapshotVersion': _revision,
      'sourceSurfaceId': 'journey.persona_management',
      'explicitOverride':
          !(active['inheritsProfileFromOwner'] as bool? ?? false),
      'isPrimary': active['isPrimary'] == true,
    });
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String subAccountId,
  ) async {
    final isPrimary = subAccountId == 'persona_primary';
    return PersonaLifecycleGuardViewData(
      subAccountId: subAccountId,
      canDelete: !isPrimary,
      canRetire: !isPrimary,
      requiredAction: '',
      reasonCode: isPrimary ? 'blocked_primary_persona' : '',
      message: isPrimary ? '主分身不可删除' : '',
    );
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    return PersonaManagementSummaryViewData(
      items: _items
          .map(PersonaManagementItemViewData.fromMap)
          .toList(growable: false),
      quota: PersonaManagementQuotaViewData(
        maxSubAccounts: 5,
        usedSubAccounts: _items.length,
      ),
      activeContext: await getActivePersonaContext(),
    );
  }

  @override
  Future<UserSettingDto> getNotificationSettings() async {
    return UserSettingDto.fromJson(<String, dynamic>{
      'userId': 'owner_persona',
      'enablePush': true,
    });
  }

  @override
  Future<UserSettingDto> getPrivacySettings() async {
    return UserSettingDto.fromJson(<String, dynamic>{
      'userId': 'owner_persona',
      'profileVisibility': 'public',
    });
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    return _items
        .map(PersonaManagementItemViewData.fromMap)
        .toList(growable: false);
  }

  @override
  Future<void> retirePersona(String subAccountId) async {
    final target = persona(subAccountId);
    target['status'] = 'retired';
    target['retiredAt'] = DateTime.utc(2026, 6, 21, 12).toIso8601String();
    target['isActive'] = false;
    _revision++;
  }

  @override
  Future<PersonaManagementItemViewData> updatePersona(
    String subAccountId, {
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
    final target = persona(subAccountId);
    final changedFields = <String>[
      if (displayName != null) 'displayName',
      if (userHandle != null) 'userHandle',
      if (phone != null) 'phone',
      if (email != null) 'email',
    ];
    if (displayName != null) target['displayName'] = displayName;
    if (userHandle != null) target['userHandle'] = userHandle;
    if (phone != null) target['phone'] = phone;
    if (email != null) target['email'] = email;
    if (avatarUrl != null) target['avatarUrl'] = avatarUrl;
    if (isolationLevel != null) target['isolationLevel'] = isolationLevel;
    target['inheritsProfileFromOwner'] = false;
    target['overriddenProfileFields'] = changedFields;
    target['updatedAt'] = DateTime.utc(2026, 6, 21, 12).toIso8601String();
    _revision++;
    return PersonaManagementItemViewData.fromMap(target);
  }
}

Widget _wrap(_JourneyUserRepository repo) {
  return ProviderScope(
    overrides: [userRepositoryProvider.overrideWithValue(repo)],
    child: const CupertinoApp(home: PersonaManagementPage()),
  );
}

List<Map<String, dynamic>> _seed() {
  return <Map<String, dynamic>>[
    <String, dynamic>{
      'subAccountId': 'persona_primary',
      'displayName': '主分身',
      'userHandle': 'main_handle',
      'phone': '13800000000',
      'email': 'main@example.com',
      'avatarUrl': 'media/avatar/s/mock/user/persona_primary/v1/avatar.png',
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
      'subAccountId': 'persona_photo',
      'displayName': '摄影分身',
      'userHandle': 'photo_handle',
      'phone': '13800000000',
      'email': 'photo@example.com',
      'avatarUrl': 'media/avatar/s/mock/user/persona_photo/v1/avatar.png',
      'avatarVersion': 2,
      'isPrimary': false,
      'isActive': false,
      'isolationLevel': 'semi',
      'profileVisibility': 'public',
      'inheritsProfileFromOwner': false,
      'status': 'active',
      'overriddenProfileFields': const <String>['email'],
    },
  ];
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('分身管理页支持编辑、同步建议应用与切换当前分身', (tester) async {
    final repo = _JourneyUserRepository(_seed());
    await tester.pumpWidget(_wrap(repo));
    await tester.pumpAndSettle();

    expect(repo.activeSubAccountId, 'persona_primary');

    final primaryStatus = find.byKey(
      const ValueKey<String>('persona-status-persona_primary'),
    );
    final photoStatus = find.byKey(
      const ValueKey<String>('persona-status-persona_photo'),
    );

    expect(
      find.descendant(
        of: primaryStatus,
        matching: find.text(UITextConstants.personaCurrentUsing),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: photoStatus,
        matching: find.text(UITextConstants.personaCurrentUsing),
      ),
      findsNothing,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('persona-edit-persona_primary')),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(CupertinoTextField).at(1),
      'main_synced',
    );
    await tester.tap(find.text(UITextConstants.confirm));
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.personaSyncSuggestionTitle),
      findsOneWidget,
    );

    await tester.tap(find.text(UITextConstants.personaSyncApplyAll));
    await tester.pumpAndSettle();

    expect(repo.syncAppliedCount, 1);
    expect(repo.persona('persona_photo')['userHandle'], 'main_synced');
    expect(find.text(UITextConstants.personaSyncSuggestionTitle), findsNothing);

    await tester.tap(
      find.byKey(const ValueKey<String>('persona-activate-persona_photo')),
    );
    await tester.pumpAndSettle();

    expect(repo.activeSubAccountId, 'persona_photo');
    expect(
      find.descendant(
        of: primaryStatus,
        matching: find.text(UITextConstants.personaCurrentUsing),
      ),
      findsNothing,
    );
    expect(
      find.descendant(
        of: photoStatus,
        matching: find.text(UITextConstants.personaCurrentUsing),
      ),
      findsOneWidget,
    );
  });
}
