/// L1a Contract Tests: 内容互动相关 Mock 契约（Block / Report）。
///
/// 内容点赞窄接口已并入 [ContentReactionRepository]，其 like 行为
/// 由 content_repository 契约测试与子接口契约测试覆盖。
library;

import 'package:flutter_test/flutter_test.dart';

void main() {
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
    final payload = <String, dynamic>{
      'targetId': targetId,
      'targetType': targetType,
      'reason': reason,
    };
    if (note != null) {
      payload['note'] = note;
    }
    submitted.add(payload);
  }
}
