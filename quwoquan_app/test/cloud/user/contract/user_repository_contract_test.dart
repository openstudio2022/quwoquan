import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';

void main() {
  group('UserRepository — 常规契约', () {
    late UserRepository repo;

    setUp(() {
      repo = MockUserRepository();
    });

    test('listSubAccounts 返回子账号列表', () async {
      final accounts = await repo.listSubAccounts();
      expect(accounts, isNotEmpty);
      expect(accounts.first.subAccountId, isNotEmpty);
    });

    test('getPersonaManagementSummary 返回 quota 与 items', () async {
      final summary = await repo.getPersonaManagementSummary();
      expect(summary.items, isNotEmpty);
      expect(summary.quota.maxSubAccounts, greaterThan(0));
    });

    test('getActivePersonaContext 返回活动身份上下文', () async {
      final context = await repo.getActivePersonaContext();
      expect(context.profileSubjectId, isNotEmpty);
    });

    test('activateSubAccount 不崩溃', () async {
      await repo.activateSubAccount('persona_test');
    });

    test('getNotificationSettings 返回通知设置', () async {
      final settings = await repo.getNotificationSettings();
      expect(settings, isA<Map<String, dynamic>>());
      expect(settings.containsKey('enablePush'), isTrue);
    });

    test('getPrivacySettings 返回隐私设置', () async {
      final settings = await repo.getPrivacySettings();
      expect(settings, isA<Map<String, dynamic>>());
      expect(settings.containsKey('profileVisibility'), isTrue);
    });
  });

  group('UserRepository — 异常/边界契约', () {
    late UserRepository repo;

    setUp(() {
      repo = MockUserRepository();
    });

    test('activateSubAccount 空 ID 不崩溃', () async {
      await repo.activateSubAccount('');
    });

    test('deleteEmptySubAccount 空 ID 不崩溃', () async {
      await repo.deleteEmptySubAccount('');
    });
  });
}
