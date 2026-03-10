import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/sub_account_management_page.dart';

// Stub AuthRepository that returns controlled data.
class _StubAuthRepository implements AuthRepository {
  _StubAuthRepository({this.accounts = const []});

  final List<Map<String, dynamic>> accounts;

  @override
  Future<List<Map<String, dynamic>>> listSubAccounts() async => accounts;

  @override
  Future<Map<String, dynamic>> login({
    required String credentialType,
    required String credentialKey,
    String? displayLabel,
  }) async => {};

  @override
  Future<void> bindCredential({
    required String credentialType,
    required String credentialKey,
    String? displayLabel,
  }) async {}

  @override
  Future<void> unbindCredential(String credentialType) async {}

  @override
  Future<List<Map<String, dynamic>>> listCredentials() async => [];

  @override
  Future<Map<String, dynamic>> createSubAccount({
    required String displayName,
    String isolationLevel = 'open',
  }) async => {'subAccountId': 'new_id', 'displayName': displayName};

  @override
  Future<void> activateSubAccount(String subAccountId) async {}

  @override
  Future<void> deleteSubAccount(String subAccountId) async {}
}

Widget _wrap(AuthRepository repo) {
  return ProviderScope(
    overrides: [
      authRepositoryProvider.overrideWithValue(repo),
    ],
    child: const CupertinoApp(
      home: SubAccountManagementPage(),
    ),
  );
}

void main() {
  group('SubAccountManagementPage — T2 Widget 测试', () {
    testWidgets('空列表显示暂无子账号提示', (tester) async {
      await tester.pumpWidget(_wrap(_StubAuthRepository()));
      await tester.pumpAndSettle();

      expect(find.text('暂无子账号'), findsOneWidget);
    });

    testWidgets('列出子账号时展示 displayName', (tester) async {
      final repo = _StubAuthRepository(accounts: [
        {
          'id': 'p1',
          'subAccountId': 'sa1',
          'displayName': '主账号',
          'isolationLevel': 'open',
          'isPrimary': true,
          'isActive': true,
        },
        {
          'id': 'p2',
          'subAccountId': 'sa2',
          'displayName': '匿名号',
          'isolationLevel': 'strict',
          'isPrimary': false,
          'isActive': false,
        },
      ]);

      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.text('主账号'), findsAtLeastNWidgets(1));
      expect(find.text('匿名号'), findsOneWidget);
    });

    testWidgets('活跃子账号显示 check_mark 图标', (tester) async {
      final repo = _StubAuthRepository(accounts: [
        {
          'id': 'p1',
          'subAccountId': 'sa1',
          'displayName': '当前激活',
          'isolationLevel': 'open',
          'isPrimary': true,
          'isActive': true,
        },
      ]);

      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.byIcon(CupertinoIcons.check_mark), findsOneWidget);
    });

    testWidgets('strict 隔离子账号显示 lock_shield_fill 图标', (tester) async {
      final repo = _StubAuthRepository(accounts: [
        {
          'id': 'p1',
          'subAccountId': 'sa1',
          'displayName': '严格隔离号',
          'isolationLevel': 'strict',
          'isPrimary': false,
          'isActive': false,
        },
      ]);

      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.byIcon(CupertinoIcons.lock_shield_fill), findsOneWidget);
      expect(find.text('严格隔离 · 不出现在通讯录发现'), findsOneWidget);
    });

    testWidgets('显示正确的隔离级别描述文案', (tester) async {
      final repo = _StubAuthRepository(accounts: [
        {
          'id': 'p1',
          'subAccountId': 'sa1',
          'displayName': '公开号',
          'isolationLevel': 'open',
          'isPrimary': false,
          'isActive': true,
        },
        {
          'id': 'p2',
          'subAccountId': 'sa2',
          'displayName': '半隐',
          'isolationLevel': 'semi',
          'isPrimary': false,
          'isActive': false,
        },
      ]);

      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.text('公开 · 可被通讯录发现'), findsOneWidget);
      expect(find.text('半隐私 · 仅好友可发现'), findsOneWidget);
    });

    testWidgets('未显示 purposeHint 私有字段', (tester) async {
      final repo = _StubAuthRepository(accounts: [
        {
          'id': 'p1',
          'subAccountId': 'sa1',
          'displayName': '主账号',
          'isolationLevel': 'open',
          'purposeHint': '这是私有字段不该显示',
          'isPrimary': true,
          'isActive': true,
        },
      ]);

      await tester.pumpWidget(_wrap(repo));
      await tester.pumpAndSettle();

      expect(find.text('这是私有字段不该显示'), findsNothing);
    });

    testWidgets('导航栏显示创建按钮', (tester) async {
      await tester.pumpWidget(_wrap(_StubAuthRepository()));
      await tester.pumpAndSettle();

      expect(find.byIcon(CupertinoIcons.add), findsOneWidget);
    });
  });
}
