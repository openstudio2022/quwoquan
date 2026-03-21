import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/sub_account_management_page.dart';

class _StubUserRepository implements UserRepository {
  _StubUserRepository({
    this.accounts = const <PersonaManagementItemViewData>[],
    this.activeContext,
  });

  final List<PersonaManagementItemViewData> accounts;
  final ActivePersonaContextViewData? activeContext;

  @override
  Future<void> activateSubAccount(String subAccountId) async {}

  @override
  Future<void> activatePersona(String personaId) => activateSubAccount(personaId);

  @override
  Future<PersonaManagementItemViewData> createSubAccount({
    required String displayName,
    String isolationLevel = 'open',
  }) async {
    return PersonaManagementItemViewData.fromMap(<String, dynamic>{
      'subAccountId': 'new_id',
      'profileSubjectId': 'subject_new_id',
      'displayName': displayName,
      'isolationLevel': isolationLevel,
      'profileVisibility': 'public',
      'isPrimary': false,
      'isActive': false,
    });
  }

  @override
  Future<void> deleteEmptySubAccount(String subAccountId) async {}

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return activeContext ??
        ActivePersonaContextViewData.fallback(
          profileSubjectId: 'user_001',
          ownerUserId: 'user_001',
          displayName: '主账号',
          avatarUrl: '',
        );
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    return PersonaManagementSummaryViewData(
      items: accounts,
      quota: PersonaManagementQuotaViewData(
        maxSubAccounts: 5,
        usedSubAccounts: accounts.length,
      ),
      activeContext: activeContext,
    );
  }

  @override
  Future<PersonaLifecycleGuardViewData> getSubAccountLifecycleGuard(
    String subAccountId,
  ) async {
    return PersonaLifecycleGuardViewData(
      subAccountId: subAccountId,
      canDelete: subAccountId != 'owner_primary',
      canRetire: subAccountId != 'owner_primary',
      requiredAction: '',
      reasonCode: '',
      message: '',
    );
  }

  @override
  Future<Map<String, dynamic>> getNotificationSettings() async {
    return <String, dynamic>{'enablePush': true};
  }

  @override
  Future<Map<String, dynamic>> getPrivacySettings() async {
    return <String, dynamic>{'profileVisibility': 'public'};
  }

  @override
  Future<List<PersonaManagementItemViewData>> listSubAccounts() async {
    return accounts;
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() => listSubAccounts();

  @override
  Future<void> retireSubAccount(String subAccountId) async {}

  @override
  Future<PersonaManagementItemViewData> updateSubAccount(
    String subAccountId, {
    String? displayName,
    String? bio,
    String? avatarUrl,
    String? isolationLevel,
    String? profileVisibility,
  }) async {
    return PersonaManagementItemViewData.fromMap(<String, dynamic>{
      'subAccountId': subAccountId,
      'profileSubjectId': subAccountId,
      'displayName': displayName ?? '更新后',
      'isolationLevel': isolationLevel ?? 'open',
      'profileVisibility': profileVisibility ?? 'public',
      'isPrimary': false,
      'isActive': false,
    });
  }
}

Widget _wrap(UserRepository repo) {
  return ProviderScope(
    overrides: [
      userRepositoryProvider.overrideWithValue(repo),
    ],
    child: const CupertinoApp(
      home: SubAccountManagementPage(),
    ),
  );
}

PersonaManagementItemViewData _item({
  required String subAccountId,
  required String displayName,
  String isolationLevel = 'open',
  bool isPrimary = false,
  bool isActive = false,
}) {
  return PersonaManagementItemViewData.fromMap(<String, dynamic>{
    'subAccountId': subAccountId,
    'profileSubjectId': 'subject_$subAccountId',
    'displayName': displayName,
    'isolationLevel': isolationLevel,
    'profileVisibility': 'public',
    'isPrimary': isPrimary,
    'isActive': isActive,
  });
}

void main() {
  group('SubAccountManagementPage — T2 Widget 测试', () {
    testWidgets('空列表显示暂无子账号提示', (tester) async {
      await tester.pumpWidget(_wrap(_StubUserRepository()));
      await tester.pumpAndSettle();

      expect(find.text('暂无子账号'), findsOneWidget);
    });

    testWidgets('列出子账号时展示 displayName', (tester) async {
      final repo = _StubUserRepository(
        accounts: <PersonaManagementItemViewData>[
          _item(
            subAccountId: 'owner_primary',
            displayName: '主账号',
            isPrimary: true,
            isActive: true,
          ),
          _item(
            subAccountId: 'persona_anon',
            displayName: '匿名号',
            isolationLevel: 'strict',
          ),
        ],
      );

      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.text('主账号'), findsAtLeastNWidgets(1));
      expect(find.text('匿名号'), findsOneWidget);
    });

    testWidgets('活跃子账号显示 check_mark_circled_solid 图标', (tester) async {
      final repo = _StubUserRepository(
        accounts: <PersonaManagementItemViewData>[
          _item(
            subAccountId: 'owner_primary',
            displayName: '当前激活',
            isPrimary: true,
            isActive: true,
          ),
        ],
      );

      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.byIcon(CupertinoIcons.check_mark_circled_solid), findsOneWidget);
    });

    testWidgets('strict 隔离子账号显示 lock_shield_fill 图标', (tester) async {
      final repo = _StubUserRepository(
        accounts: <PersonaManagementItemViewData>[
          _item(
            subAccountId: 'persona_strict',
            displayName: '严格隔离号',
            isolationLevel: 'strict',
          ),
        ],
      );

      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.byIcon(CupertinoIcons.lock_shield_fill), findsOneWidget);
      expect(find.text('严格隔离 · 不出现在通讯录发现'), findsOneWidget);
    });

    testWidgets('显示正确的隔离级别描述文案', (tester) async {
      final repo = _StubUserRepository(
        accounts: <PersonaManagementItemViewData>[
          _item(
            subAccountId: 'persona_open',
            displayName: '公开号',
            isolationLevel: 'open',
            isActive: true,
          ),
          _item(
            subAccountId: 'persona_semi',
            displayName: '半隐',
            isolationLevel: 'semi',
          ),
        ],
      );

      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.text('公开 · 可被通讯录发现'), findsOneWidget);
      expect(find.text('半隐私 · 仅好友可发现'), findsOneWidget);
    });

    testWidgets('导航栏显示创建按钮', (tester) async {
      await tester.pumpWidget(_wrap(_StubUserRepository()));
      await tester.pumpAndSettle();

      expect(find.byIcon(CupertinoIcons.add), findsOneWidget);
    });
  });
}
