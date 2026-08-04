/// L1a Contract Tests: 内容互动相关 Mock 契约（Block / Report）。
///
/// 内容点赞由 pure-contract [ContentPostReactionFacet] 承载；本文件只覆盖
/// Block / Report，不维护聚合 Content Repository 的反应接口。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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

  group('ContentReportCommandWriter alpha 契约', () {
    test('createReport 记录到 submitted', () async {
      final repo = _reportRepo();
      await repo.createReport(
        CreateContentReportCommand(
          targetId: 'post_1',
          targetType: ReportTargetType.post,
          reason: ReportReason.spam,
          description: '广告',
        ),
      );
      expect(repo.submitted.length, equals(1));
      expect(repo.submitted.first.reason, ReportReason.spam);
      expect(repo.submitted.first.description, equals('广告'));
    });

    test('description 为 null 时不写入 submitted map', () async {
      final repo = _reportRepo();
      await repo.createReport(
        CreateContentReportCommand(
          targetId: 'post_2',
          targetType: ReportTargetType.post,
          reason: ReportReason.other,
        ),
      );
      expect(repo.submitted.first.description, isNull);
    });
  });
}

_MockBlock _blockRepo() => _MockBlock();
_MockReport _reportRepo() => _MockReport();

// ignore: avoid_implementing_value_types
class _MockBlock {
  final Set<String> _set = {};
  Future<void> blockUser(String id) async => _set.add(id);
  Future<void> unblockUser(String id) async => _set.remove(id);
  bool isBlocked(String id) => _set.contains(id);
}

class _MockReport implements ContentReportCommandWriter {
  final List<CreateContentReportCommand> submitted = [];

  @override
  Future<void> createReport(CreateContentReportCommand command) async {
    submitted.add(command);
  }
}
