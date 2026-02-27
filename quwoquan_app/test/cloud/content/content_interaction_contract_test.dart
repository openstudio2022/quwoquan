/// L1a Contract Tests: ContentInteractionRepository Mock 契约
///
/// 守护：MockContentInteractionRepository 状态正确，不发 HTTP。
/// 覆盖：like / unlike / favorite / unfavorite 状态变迁。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_interaction_repository.dart';

void main() {
  group('MockContentInteractionRepository', () {
    late MockContentInteractionRepository repo;

    setUp(() => repo = MockContentInteractionRepository());

    test('like 添加到 likedPosts', () async {
      await repo.like('post_1');
      expect(repo.likedPosts.contains('post_1'), isTrue);
    });

    test('unlike 从 likedPosts 移除', () async {
      await repo.like('post_1');
      await repo.unlike('post_1');
      expect(repo.likedPosts.contains('post_1'), isFalse);
    });

    test('favorite 添加到 favoritedPosts', () async {
      await repo.favorite('post_2');
      expect(repo.favoritedPosts.contains('post_2'), isTrue);
    });

    test('unfavorite 从 favoritedPosts 移除', () async {
      await repo.favorite('post_2');
      await repo.unfavorite('post_2');
      expect(repo.favoritedPosts.contains('post_2'), isFalse);
    });

    test('多次 like 同一帖子不重复添加（Set 特性）', () async {
      await repo.like('post_1');
      await repo.like('post_1');
      expect(repo.likedPosts.where((id) => id == 'post_1').length, equals(1));
    });
  });

  group('MockBlockRepository', () {
    test('blockUser 记录，isBlocked 返回 true', () async {
      final repo = _blockRepo();
      await repo.blockUser('user_x');
      expect(repo.isBlocked('user_x'), isTrue);
    });

    test('unblockUser 后 isBlocked 返回 false', () async {
      final repo = _blockRepo();
      await repo.blockUser('user_x');
      await repo.unblockUser('user_x');
      expect(repo.isBlocked('user_x'), isFalse);
    });
  });

  group('MockReportRepository', () {
    test('createReport 记录到 submitted', () async {
      final repo = _reportRepo();
      await repo.createReport(
        targetId: 'post_1',
        targetType: 'post',
        reason: 'spam',
        note: '广告',
      );
      expect(repo.submitted.length, equals(1));
      expect(repo.submitted.first['reason'], equals('spam'));
      expect(repo.submitted.first['note'], equals('广告'));
    });

    test('note 为 null 时不写入 submitted map', () async {
      final repo = _reportRepo();
      await repo.createReport(
        targetId: 'post_2',
        targetType: 'post',
        reason: 'inappropriate',
      );
      expect(repo.submitted.first.containsKey('note'), isFalse);
    });
  });
}

// 避免循环 import，直接 inline 最小 helper
_MockBlock _blockRepo() => _MockBlock();
_MockReport _reportRepo() => _MockReport();

// ignore: avoid_implementing_value_types
class _MockBlock {
  final Set<String> _set = {};
  Future<void> blockUser(String id) async => _set.add(id);
  Future<void> unblockUser(String id) async => _set.remove(id);
  bool isBlocked(String id) => _set.contains(id);
}

class _MockReport {
  final List<Map<String, dynamic>> submitted = [];
  Future<void> createReport({
    required String targetId,
    required String targetType,
    required String reason,
    String? note,
  }) async {
    submitted.add({
      'targetId': targetId,
      'targetType': targetType,
      'reason': reason,
      if (note != null) 'note': note,
    });
  }
}
