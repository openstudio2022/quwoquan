import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';

/// 交集统一体验 · Mock 契约（T1/T2）：
/// - 我的交集聚合摘要：总数 / 5 维度 / 自上次新增（freshAt > 已读水位）。
/// - 打开列表（visit）即推进已读水位 → 该维度（或全部）未读清零。
/// - campus/travel 频道有专属交集；事实优先 + 概率补充。
/// - 曝光上报写跨会话冷却集 → 同对象不再下发（推荐窗口）。
/// - 事实 vs 概率分通道：interest affinity 标 intersectionClass=affinity + confidenceLabel。
void main() {
  group('MockIntersectionRepository 我的交集摘要/清零', () {
    test('摘要含 5 维度，初始全部计入未读新增', () async {
      final repo = MockIntersectionRepository();
      final summary = await repo.getMyIntersectionSummary();

      expect(summary.totalCount, 6);
      expect(summary.dimensions.length, 5);
      // 无已读水位时，所有带 freshAt 的交集都算新增。
      expect(summary.totalNewCount, greaterThan(0));
      expect(summary.totalNewCount, summary.totalCount);
    });

    test('打开全部列表（visit 空维度）→ 全部未读清零', () async {
      final repo = MockIntersectionRepository();
      await repo.markIntersectionsVisited();
      final summary = await repo.getMyIntersectionSummary();

      expect(summary.totalNewCount, 0);
      for (final tally in summary.dimensions) {
        expect(tally.newCount, 0, reason: '${tally.dimension} 应已清零');
      }
    });

    test('仅访问某维度 → 仅该维度清零，其余维度未读保留', () async {
      final repo = MockIntersectionRepository();
      await repo.markIntersectionsVisited(dimension: 'relationship');
      final summary = await repo.getMyIntersectionSummary();

      final rel = summary.dimensions.firstWhere(
        (t) => t.dimension == 'relationship',
      );
      expect(rel.newCount, 0);
      expect(summary.totalNewCount, greaterThan(0));
    });

    test('分维度列表：自上次新增在前', () async {
      final repo = MockIntersectionRepository();
      final items = await repo.listMyIntersections(dimension: 'relationship');
      expect(items.length, 2);
      expect(items.every((r) => r.dimension == 'relationship'), isTrue);
    });

    test('我的交集列表下发可展示交集点，摘要数字由列表派生', () async {
      final repo = MockIntersectionRepository();
      final items = await repo.listMyIntersections();
      expect(items, isNotEmpty);
      expect(items.every((r) => r.displayText.trim().isNotEmpty), isTrue);
      expect(items.every((r) => r.intersectionPoints.isNotEmpty), isTrue);
      expect(
        items.every((r) => r.totalPointCount == r.intersectionPoints.length),
        isTrue,
      );
    });
  });

  group('MockIntersectionRepository 频道交集（campus/travel）', () {
    test('campus 频道有专属交集（事实 + 概率）', () async {
      final repo = MockIntersectionRepository();
      final items = await repo.getFeedIntersections(channel: 'campus');
      expect(items, isNotEmpty);
      final names = items.map((r) => r.displayName).toList();
      expect(names, contains('苏黎'));
      expect(items.any((r) => r.intersectionClass == 'fact'), isTrue);
      expect(items.any((r) => r.intersectionClass == 'affinity'), isTrue);
    });

    test('travel 频道有专属交集', () async {
      final repo = MockIntersectionRepository();
      final items = await repo.getFeedIntersections(channel: 'travel');
      expect(items.map((r) => r.displayName), contains('大理'));
    });

    test('未知频道回退 recommend 池', () async {
      final repo = MockIntersectionRepository();
      final items = await repo.getFeedIntersections(channel: 'unknown_x');
      expect(items, isNotEmpty);
    });

    test('feed 交集全部带交集点列表，事实与推荐都可直接展示', () async {
      final repo = MockIntersectionRepository();
      final items = await repo.getFeedIntersections(channel: 'travel');
      expect(items, isNotEmpty);
      expect(items.every((r) => r.displayText.trim().isNotEmpty), isTrue);
      expect(items.every((r) => r.intersectionPoints.isNotEmpty), isTrue);
      final affinity = items.firstWhere(
        (r) => r.intersectionClass == 'affinity',
      );
      expect(
        affinity.recommendedPointCount,
        affinity.intersectionPoints.length,
      );
      expect(affinity.pointClassLabel, '推荐交集');
    });
  });

  group('MockIntersectionRepository 曝光保留 / 分通道', () {
    test('曝光上报后同对象仍保留但降权为 seen', () async {
      final repo = MockIntersectionRepository();
      final before = await repo.getFeedIntersections(channel: 'campus');
      expect(before.map((r) => r.actionTargetId), contains('u_su'));

      await repo.reportExposure(objectIds: <String>['u_su']);

      final after = await repo.getFeedIntersections(channel: 'campus');
      expect(after.map((r) => r.actionTargetId), contains('u_su'));
      expect(after.last.actionTargetId, 'u_su');
      expect(after.last.rankState, 'seen');
      expect(after.last.seenAt, isNotEmpty);
    });

    test('概率交集标 affinity + confidenceLabel；事实交集为 fact', () async {
      final repo = MockIntersectionRepository();
      final items = await repo.getFeedIntersections(channel: 'campus');
      final affinity = items.firstWhere(
        (r) => r.intersectionClass == 'affinity',
        orElse: () => IntersectionReason(),
      );
      expect(affinity.intersectionClass, 'affinity');
      expect(affinity.confidenceLabel.isNotEmpty, isTrue);
    });
  });
}
