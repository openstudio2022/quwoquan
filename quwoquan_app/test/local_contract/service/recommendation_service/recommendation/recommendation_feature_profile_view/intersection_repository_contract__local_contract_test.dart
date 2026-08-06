import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/generated/intersection_kind_metadata.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_statement_synthesizer.dart';

import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_repository_typed_double.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

/// 交集统一体验 · Alpha fixture 本地契约。
///
/// 范围已对齐统一交互子契约冻结后的 [IntersectionRepository]：
///   - 我的交集聚合摘要 / 分维度列表 / 已读水位清零；
///   - G2 单通道不变量：`*Spans` 只能是结论句（briefText / primaryText）的结构化富文本切分，
///     契约断言 `join(spans.text) == briefText/primaryText`；
///   - 禁止 reason 级 displayText / label / sharedCount / recommendationTraceId 回归。
///
/// 频道交集（GetFeedIntersections）与曝光上报（ReportIntersectionExposure）已移出
/// 本仓库契约（service.yaml 同步下线），不再在此断言。
void main() {
  group('InMemoryIntersectionRepository 我的交集摘要/清零', () {
    test('摘要含 5 维度，初始全部计入未读新增', () async {
      final repo = InMemoryIntersectionRepository();
      final summary = await repo.getMyIntersectionSummary();

      // 5 维闭集 + 初始全部记为未读新增；不锁易碎的枚举总数（随 alpha bundle 扩充自适应），
      // 改用结构不变量：总数==各维度计数之和，防分组/去重漂移。
      expect(summary.dimensions.length, 5);
      expect(summary.totalCount, greaterThan(0));
      expect(summary.totalNewCount, summary.totalCount);
      final dimensionSum = summary.dimensions.fold<int>(
        0,
        (sum, tally) => sum + tally.count,
      );
      expect(summary.totalCount, dimensionSum);
    });

    test('打开全部列表（visit 空维度）→ 全部未读清零', () async {
      final repo = InMemoryIntersectionRepository();
      await repo.markIntersectionsVisited();
      final summary = await repo.getMyIntersectionSummary();

      expect(summary.totalNewCount, 0);
      for (final tally in summary.dimensions) {
        expect(tally.newCount, 0, reason: '${tally.dimension} 应已清零');
      }
    });

    test('仅访问某维度 → 仅该维度清零，其余维度未读保留', () async {
      final repo = InMemoryIntersectionRepository();
      await repo.markIntersectionsVisited(
        dimension: IntersectionDimension.relationship,
      );
      final summary = await repo.getMyIntersectionSummary();

      final rel = summary.dimensions.firstWhere(
        (t) => t.dimension == 'relationship',
      );
      expect(rel.newCount, 0);
      expect(summary.totalNewCount, greaterThan(0));
    });

    test('分维度列表：自上次新增在前（不变量，不硬编码条数）', () async {
      final repo = InMemoryIntersectionRepository();
      final items = await repo.listMyIntersections(dimension: 'relationship');
      expect(items, isNotEmpty);
      expect(items.every((r) => r.dimension == 'relationship'), isTrue);
      // 排序不变量：新初始化仓库无已读水位，「新增」= freshAt 非空；
      // 新增项必须整体排在非新增项之前（一旦出现非新增项，其后不得再现新增项）。
      var seenStale = false;
      for (final r in items) {
        final isNew = r.freshAt.trim().isNotEmpty;
        if (!isNew) {
          seenStale = true;
        } else {
          expect(seenStale, isFalse, reason: '新增交集必须排在非新增之前');
        }
      }
    });

    test('我的交集列表下发可展示交集点，摘要数字由列表派生', () async {
      final repo = InMemoryIntersectionRepository();
      final items = await repo.listMyIntersections();
      expect(items, isNotEmpty);
      expect(items.every((r) => r.primaryText.trim().isNotEmpty), isTrue);
      expect(items.every((r) => r.intersectionPoints.isNotEmpty), isTrue);
      expect(
        items.every((r) => r.totalPointCount == r.intersectionPoints.length),
        isTrue,
      );
    });

    test('对象主页交集从 immutable alpha bundle 读取', () async {
      final repo = InMemoryIntersectionRepository();
      final items = await repo.getObjectIntersections(
        objectId: 'fixture_homepage_travel_route_erhai',
        objectType: 'entity',
      );

      expect(items, isNotEmpty);
      expect(
        items.map((reason) => reason.intersectionId),
        contains('objix_erhai_followee'),
      );
      expect(
        items.every((reason) => reason.intersectionPoints.isNotEmpty),
        isTrue,
      );
      final hostTarget = intersectionTargetFixture(
        objectType: 'homepage',
        objectId: 'fixture_homepage_travel_route_erhai',
        objectKind: 'route',
        routeId: 'homepageDetail',
      );
      expect(
        items.every(
          (reason) =>
              reason.displayBinding == intersectionDisplayBindingHostPlain &&
              displayReadyIntersectionReason(
                    reason,
                    contextObjectTarget: hostTarget,
                  ) !=
                  null,
        ),
        isTrue,
        reason: 'alpha 对象页必须复刻云侧 host_plain，不能让四主页卡整批落为空态',
      );
    });
  });

  group('交集统一交互子契约 · G2 单通道不变量', () {
    String joinSpans(List<IntersectionTextSpan> spans) =>
        spans.map((s) => s.text).join();

    test('维度简报 join(briefSpans.text) == briefText（端不拼装结论句）', () async {
      final repo = InMemoryIntersectionRepository();
      final summary = await repo.getMyIntersectionSummary();

      // 至少一个维度真实下发了结构化 spans（非空覆盖，而非纯空集放行）。
      final withSpans = summary.dimensions
          .where((t) => t.briefSpans.isNotEmpty)
          .toList(growable: false);
      expect(withSpans, isNotEmpty, reason: 'alpha adapter 应模拟云侧下发 briefSpans');

      for (final tally in summary.dimensions) {
        if (tally.briefSpans.isEmpty) {
          continue; // 降级链：spans 为空时回落 briefText，允许。
        }
        expect(
          joinSpans(tally.briefSpans),
          tally.briefText,
          reason: '${tally.dimension} 的 briefSpans 必须无损拼回 briefText',
        );
      }
    });

    test('交集理由 join(primarySpans.text) == primaryText（非空时无损拼回）', () async {
      final repo = InMemoryIntersectionRepository();
      final reasons = await repo.listMyIntersections();
      for (final reason in reasons) {
        if (reason.primarySpans.isEmpty) {
          continue; // 降级链：spans 缺省回落 primaryText。
        }
        expect(joinSpans(reason.primarySpans), reason.primaryText);
      }
    });

    test('count 片段进 myIntersections 下钻、object 片段进对象主页（target 角色分流）', () async {
      final repo = InMemoryIntersectionRepository();
      final summary = await repo.getMyIntersectionSummary();
      final spans = summary.dimensions
          .expand((t) => t.briefSpans)
          .toList(growable: false);

      final counts = spans.where((s) => s.role == 'count');
      expect(counts, isNotEmpty, reason: '简报应含可下钻的数字片段');
      for (final count in counts) {
        expect(
          count.target?.routeId,
          'myIntersections',
          reason: '数字片段必须携带维度下钻 target',
        );
      }
      for (final object in spans.where((s) => s.role == 'object')) {
        expect(object.target, isNotNull, reason: 'object 片段必须可达对象');
        expect(object.target!.routeId, isNot('myIntersections'));
      }
    });

    test(
      '禁止 reason 级 displayText/label/sharedCount/recommendationTraceId 回归',
      () {
        final map = intersectionReasonFixture().toWire();
        expect(map.containsKey('displayText'), isFalse);
        expect(map.containsKey('label'), isFalse);
        expect(map.containsKey('sharedCount'), isFalse);
        expect(map.containsKey('recommendationTraceId'), isFalse);
      },
    );

    test('Alpha actionHints hydrate 行动阶梯 metadata，不退回默认 navigate', () async {
      final repo = InMemoryIntersectionRepository();
      final reasons = await repo.listMyIntersections();
      final hints = reasons
          .expand((reason) => reason.actionHints)
          .toList(growable: false);
      expect(hints, isNotEmpty);

      for (final hint in hints) {
        final meta = IntersectionActionKeyMeta.of(hint.actionKey);
        expect(meta, isNotNull, reason: hint.actionKey);
        expect(hint.actionTier, meta!.tier, reason: hint.actionKey);
        expect(hint.requiredGates, meta.requiredGates, reason: hint.actionKey);
        expect(hint.dispatch, meta.dispatch, reason: hint.actionKey);
      }
    });
  });
}
