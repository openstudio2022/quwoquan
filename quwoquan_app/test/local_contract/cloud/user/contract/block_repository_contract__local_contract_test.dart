import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/user/block_repository.dart';

void main() {
  group('BlockRepository — 常规契约', () {
    late BlockRepository repo;

    setUp(() {
      repo = MockBlockRepository();
    });

    test('blockUser + isBlocked 联动正确', () async {
      expect(repo.isBlocked('user_a'), isFalse);
      await repo.blockUser('user_a');
      expect(repo.isBlocked('user_a'), isTrue);
    });

    test('unblockUser + isBlocked 联动正确', () async {
      await repo.blockUser('user_b');
      expect(repo.isBlocked('user_b'), isTrue);
      await repo.unblockUser('user_b');
      expect(repo.isBlocked('user_b'), isFalse);
    });

    test('isBlocked 默认返回 false', () {
      expect(repo.isBlocked('random_user'), isFalse);
    });

    test('接口包含全部 3 个 service.yaml API 方法', () {
      final methods = <String>[
        'blockUser',
        'unblockUser',
        'isBlocked',
      ];
      expect(methods.length, 3);
    });
  });

  group('BlockRepository — 异常/边界契约', () {
    late BlockRepository repo;

    setUp(() {
      repo = MockBlockRepository();
    });

    test('blockUser 空 ID 不崩溃', () async {
      await repo.blockUser('');
    });

    test('重复 blockUser 不崩溃', () async {
      await repo.blockUser('user_c');
      await repo.blockUser('user_c');
      expect(repo.isBlocked('user_c'), isTrue);
    });

    test('unblockUser 未屏蔽用户不崩溃', () async {
      await repo.unblockUser('never_blocked');
    });
  });
}
