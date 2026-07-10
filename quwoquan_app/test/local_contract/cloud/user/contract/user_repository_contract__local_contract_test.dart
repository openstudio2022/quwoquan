import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_app/core/auth/mock_session_identity.dart';

void main() {
  group('UserRepository — 常规契约', () {
    late UserRepository repo;

    setUp(() {
      repo = MockUserRepository();
    });

    test('listPersonas 返回分身列表', () async {
      final accounts = await repo.listPersonas();
      expect(accounts, isNotEmpty);
      expect(accounts.first.subAccountId, isNotEmpty);
    });

    test('getPersonaManagementSummary 返回 quota 与 items', () async {
      final summary = await repo.getPersonaManagementSummary();
      expect(summary.items, isNotEmpty);
      expect(summary.quota.maxSubAccounts, greaterThan(0));
    });

    test(
      'getPersonaManagementSummary 与 activeContext 显式暴露 avatarVersion',
      () async {
        final summary = await repo.getPersonaManagementSummary();
        expect(summary.items, isNotEmpty);
        final primary = summary.items.first;
        expect(primary.avatarUrl, isNotEmpty);
        expect(primary.avatarVersion, greaterThanOrEqualTo(0));
        expect(summary.activeContext, isNotNull);
        expect(summary.activeContext!.avatarUrl, isNotEmpty);
        expect(summary.activeContext!.avatarVersion, greaterThanOrEqualTo(0));
      },
    );

    test('getActivePersonaContext 返回活动身份上下文', () async {
      final context = await repo.getActivePersonaContext();
      expect(context.subAccountId, isNotEmpty);
    });

    test('getActivePersonaContext 与 canonical 当前 mock 用户对齐', () async {
      final context = await repo.getActivePersonaContext();
      expect(context.subAccountId, kMockCurrentSubAccountId);
      expect(context.ownerUserId, kMockCurrentOwnerId);
      expect(context.displayName, isNotEmpty);
    });

    test('activatePersona 不崩溃', () async {
      await repo.activatePersona('persona_test');
    });

    test('applyPersonaProfileSync 返回已应用数量', () async {
      final count = await repo.applyPersonaProfileSync(
        'persona_test',
        fieldsMask: const <String>['phone', 'email'],
      );
      expect(count, greaterThanOrEqualTo(0));
    });

    test('getNotificationSettings 返回通知设置', () async {
      final settings = await repo.getNotificationSettings();
      expect(settings.enablePush, isTrue);
    });

    test('getPrivacySettings 返回隐私设置', () async {
      final settings = await repo.getPrivacySettings();
      expect(settings.profileVisibility, 'public');
    });
  });

  group('UserRepository — 异常/边界契约', () {
    late UserRepository repo;

    setUp(() {
      repo = MockUserRepository();
    });

    test('activatePersona 空 ID 不崩溃', () async {
      await repo.activatePersona('');
    });

    test('deleteEmptyPersona 空 ID 不崩溃', () async {
      await repo.deleteEmptyPersona('');
    });
  });
}
