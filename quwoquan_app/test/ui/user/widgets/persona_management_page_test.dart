import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_setting_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/persona_management_page.dart';

class _StubUserRepository implements UserRepository {
  _StubUserRepository(this._items);

  final List<Map<String, dynamic>> _items;
  int syncAppliedCount = 0;
  int deleteCount = 0;

  @override
  Future<void> activatePersona(String personaId) async {
    for (final item in _items) {
      item['isActive'] = item['subAccountId'] == personaId;
    }
  }

  @override
  Future<int> applyPersonaProfileSync(
    String personaId, {
    required List<String> fieldsMask,
    String applyScope = 'all_sub_accounts',
    List<String> syncTargetIds = const <String>[],
  }) async {
    syncAppliedCount++;
    return syncTargetIds.isEmpty ? 1 : syncTargetIds.length;
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
      'profileSubjectId': 'created_persona',
      'displayName': displayName,
      'userHandle': userHandle ?? '',
      'phone': '13800000000',
      'email': '',
      'isolationLevel': isolationLevel,
      'profileVisibility': 'public',
      'isPrimary': false,
      'isActive': false,
      'status': 'active',
      'inheritsProfileFromOwner': true,
      'overriddenProfileFields': const <String>[],
    };
    _items.add(created);
    return PersonaManagementItemViewData.fromMap(created);
  }

  @override
  Future<void> deleteEmptyPersona(String personaId) async {
    deleteCount++;
    _items.removeWhere((item) => item['subAccountId'] == personaId);
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    final active = _items.firstWhere((item) => item['isActive'] == true);
    return ActivePersonaContextViewData.fromMap(active);
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) async {
    return PersonaLifecycleGuardViewData(
      subAccountId: personaId,
      canDelete: personaId != 'persona_primary',
      canRetire: personaId != 'persona_primary',
      requiredAction: '',
      reasonCode: '',
      message: '',
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
      activeContext: ActivePersonaContextViewData.fromMap(
        _items.firstWhere((item) => item['isActive'] == true),
      ),
    );
  }

  @override
  Future<UserSettingDto> getNotificationSettings() async {
    return UserSettingDto.fromJson(<String, dynamic>{
      'userId': '',
      'enablePush': true,
    });
  }

  @override
  Future<UserSettingDto> getPrivacySettings() async {
    return UserSettingDto.fromJson(<String, dynamic>{
      'userId': '',
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
  Future<void> retirePersona(String personaId) async {
    final index = _items.indexWhere(
      (item) => item['subAccountId'] == personaId,
    );
    if (index == -1) return;
    _items[index] = <String, dynamic>{
      ..._items[index],
      'status': 'retired',
      'retiredAt': DateTime(2026, 4, 23).toIso8601String(),
      'isActive': false,
    };
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
    final index = _items.indexWhere(
      (item) => item['subAccountId'] == personaId,
    );
    final updated = Map<String, dynamic>.from(_items[index]);
    if (displayName != null) updated['displayName'] = displayName;
    if (userHandle != null) updated['userHandle'] = userHandle;
    if (phone != null) updated['phone'] = phone;
    if (email != null) updated['email'] = email;
    updated['inheritsProfileFromOwner'] = false;
    updated['overriddenProfileFields'] =
        fieldsMask ??
        <String>[
          if (displayName != null) 'displayName',
          if (userHandle != null) 'userHandle',
          if (phone != null) 'phone',
          if (email != null) 'email',
        ];
    _items[index] = updated;
    return PersonaManagementItemViewData.fromMap(updated);
  }
}

Widget _wrap(_StubUserRepository repo) {
  return ProviderScope(
    overrides: [userRepositoryProvider.overrideWithValue(repo)],
    child: const CupertinoApp(home: PersonaManagementPage()),
  );
}

List<Map<String, dynamic>> _seed() {
  return <Map<String, dynamic>>[
    <String, dynamic>{
      'subAccountId': 'persona_primary',
      'profileSubjectId': 'persona_primary',
      'displayName': '主分身',
      'userHandle': 'main_handle',
      'phone': '13800000000',
      'email': 'main@example.com',
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
      'profileSubjectId': 'persona_photo',
      'displayName': '摄影分身',
      'userHandle': 'photo_handle',
      'phone': '13800000000',
      'email': 'photo@example.com',
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
  group('PersonaManagementPage', () {
    testWidgets('展示分身资料字段', (tester) async {
      final repo = _StubUserRepository(_seed());
      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.text('主分身'), findsWidgets);
      expect(find.textContaining('用户号: main_handle'), findsOneWidget);
      expect(find.textContaining('手机号: 13800000000'), findsWidgets);
    });

    testWidgets('编辑资料后出现同步建议', (tester) async {
      final repo = _StubUserRepository(_seed());
      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.profileEditLabel).first);
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(CupertinoTextField).at(1),
        'new_handle',
      );
      await tester.tap(find.text(UITextConstants.confirm));
      await tester.pumpAndSettle();

      expect(
        find.text(UITextConstants.personaSyncSuggestionTitle),
        findsOneWidget,
      );
    });

    testWidgets('同步建议可执行应用', (tester) async {
      final repo = _StubUserRepository(_seed());
      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.profileEditLabel).first);
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(CupertinoTextField).at(2),
        '13900000000',
      );
      await tester.tap(find.text(UITextConstants.confirm));
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.personaSyncApplyAll));
      await tester.pumpAndSettle();

      expect(repo.syncAppliedCount, 1);
    });

    testWidgets('已退役分身展示退役态并隐藏删除按钮', (tester) async {
      final items = _seed();
      items[1] = <String, dynamic>{
        ...items[1],
        'status': 'retired',
        'retiredAt': DateTime(2026, 4, 23).toIso8601String(),
      };
      final repo = _StubUserRepository(items);
      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.personaRetired), findsWidgets);
      expect(find.text(UITextConstants.personaDelete), findsNothing);
    });
  });
}
