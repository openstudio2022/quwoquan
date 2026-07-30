import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_entity.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/widgets/home_intersection_spotlight_rail.dart';

/// 首页交集 spotlight 落地面契约：
/// 数据只来自「我的交集」事实读面，端不合成句子、不占空版式，点击落到统一导航器。
void main() {
  group('HomeIntersectionSpotlightRail', () {
    testWidgets('有事实交集时渲染标题与 IntersectionEntity spotlight 卡', (tester) async {
      await _pumpRail(
        tester,
        reasons: <IntersectionReason>[
          _factReason(id: 'ix_1', name: '西湖', text: '你们都去过西湖'),
          _factReason(id: 'ix_2', name: '陆衡', text: '你和陆衡都是摄影师'),
        ],
        channelId: 'travel',
      );

      expect(
        find.text(DiscoveryFeedText.intersectionTravelSpotlightTitle),
        findsOneWidget,
      );
      final cards = tester.widgetList<IntersectionEntity>(
        find.byType(IntersectionEntity),
      );
      expect(cards.length, 2);
      for (final card in cards) {
        expect(card.density, IntersectionEntityDensity.spotlight);
      }
    });

    testWidgets('无交集时整体缺席，不用占位撑住版式', (tester) async {
      await _pumpRail(tester, reasons: const <IntersectionReason>[]);

      expect(find.byType(IntersectionEntity), findsNothing);
      expect(
        find.text(DiscoveryFeedText.intersectionRecommendSpotlightTitle),
        findsNothing,
      );
      // 空态必须零高度：否则首页会给「你即将有交集」留一块假模块。
      final size = tester.getSize(
        find.byType(HomeIntersectionSpotlightRail),
      );
      expect(size.height, 0);
    });

    testWidgets('概率交集与无对象名的条目不进 spotlight', (tester) async {
      await _pumpRail(
        tester,
        reasons: <IntersectionReason>[
          _factReason(
            id: 'ix_affinity',
            name: '灵隐寺',
            text: '你可能也喜欢灵隐寺',
            intersectionClass: 'affinity',
          ),
          _factReason(id: 'ix_noname', name: '', text: '你们都去过某地'),
          _factReason(id: 'ix_ok', name: '西湖', text: '你们都去过西湖'),
        ],
      );

      expect(find.byType(IntersectionEntity), findsOneWidget);
      final card = tester.widget<IntersectionEntity>(
        find.byType(IntersectionEntity),
      );
      expect(card.reason.intersectionId, 'ix_ok');
    });

    test('displayable 上限截断，避免首页横滑无限长', () {
      final many = List<IntersectionReason>.generate(
        20,
        (i) => _factReason(id: 'ix_$i', name: '对象$i', text: '你们都去过对象$i'),
      );
      expect(HomeIntersectionSpotlightRail.displayable(many).length, 8);
    });

    test('频道标题来自频道 id 闭集，不做拼接', () {
      expect(
        HomeIntersectionSpotlightRail.titleFor('travel'),
        DiscoveryFeedText.intersectionTravelSpotlightTitle,
      );
      expect(
        HomeIntersectionSpotlightRail.titleFor('campus'),
        DiscoveryFeedText.intersectionCampusSpotlightTitle,
      );
      expect(
        HomeIntersectionSpotlightRail.titleFor('recommend'),
        DiscoveryFeedText.intersectionRecommendSpotlightTitle,
      );
    });
  });
}

Future<void> _pumpRail(
  WidgetTester tester, {
  required List<IntersectionReason> reasons,
  String channelId = 'recommend',
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        intersectionRepositoryProvider.overrideWithValue(
          _FixedIntersectionRepository(reasons),
        ),
      ],
      child: CupertinoApp(
        home: CupertinoPageScaffold(
          child: HomeIntersectionSpotlightRail(
            isDark: false,
            channelId: channelId,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

IntersectionReason _factReason({
  required String id,
  required String name,
  required String text,
  String intersectionClass = 'fact',
}) {
  final target = IntersectionTarget(
    objectType: 'homepage',
    objectId: 'homepage_$id',
    objectKind: 'entity',
    routeId: 'homepageDetail',
  );
  return IntersectionReason(
    kind: 'coVisitedEntity',
    dimension: 'location',
    intersectionClass: intersectionClass,
    intersectionId: id,
    objectKind: 'entity',
    displayName: name,
    primaryText: text,
    primarySpans: <IntersectionTextSpan>[
      IntersectionTextSpan(text: text, role: 'object', target: target),
    ],
    actionTargetId: 'homepage_$id',
    source: 'coVisitedEntity',
    dedupeKey: 'viewer:$id',
    freshAt: DateTime.utc(2026, 7, 28).toIso8601String(),
  );
}

class _FixedIntersectionRepository implements IntersectionRepository {
  _FixedIntersectionRepository(this.reasons);

  final List<IntersectionReason> reasons;

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async =>
      IntersectionInboxSummary(totalCount: 0, totalNewCount: 0);

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async => reasons;

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}
