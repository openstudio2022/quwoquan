// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#req-008
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-008
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_experience_asset_card.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_intersection_inbox_timeline.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

/// 经历交集事实替身：只回放 `sourceRef=coExperiencedGathering` 的查询，
/// 校验消费方按 REQ-008 携带正确的服务端收窄参数。
final class _ExperienceIntersectionRepository implements IntersectionRepository {
  _ExperienceIntersectionRepository({
    this.items = const <IntersectionReason>[],
    this.failure,
  });

  final List<IntersectionReason> items;
  final Object? failure;
  String? requestedSourceRef;
  String? requestedFilter;
  int listCalls = 0;

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    listCalls += 1;
    requestedSourceRef = sourceRef;
    requestedFilter = filter;
    final error = failure;
    if (error != null) {
      throw error;
    }
    return items;
  }

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async =>
      intersectionInboxSummaryFixture(totalCount: items.length);

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

IntersectionReason _experienceReason({
  String id = 'ix_exp',
  String gatheringId = 'gathering_huanglong',
  int count = 1,
}) {
  return intersectionReasonFixture(
    kind: 'coExperiencedGathering',
    dimension: 'relationship',
    intersectionClass: 'fact',
    intersectionId: id,
    objectKind: 'person',
    relationObjectId: 'peer_user',
    actionTargetId: gatheringId,
    source: 'gathering_shared_experience_events',
    primaryText: '你们一起参加过 $count 次行动',
    primarySpans: <IntersectionTextSpan>[
      intersectionTextSpanFixture(text: '你们一起参加过 $count 次行动', role: 'plain'),
    ],
    iconKey: 'experience',
    intersectionPoints: <IntersectionPoint>[
      intersectionPointFixture(
        pointId: 'p_exp',
        pointClass: 'fact',
        dimension: 'relationship',
        sourceRef: 'coExperiencedGathering',
        count: count,
      ),
    ],
    actionHints: <IntersectionActionHint>[
      intersectionActionHintFixture(
        actionKey: 'start_gathering',
        label: '再约一次',
        isPrimary: true,
        priority: 1,
        dispatch: 'gathering',
        target: intersectionTargetFixture(
          objectType: 'gathering',
          objectId: gatheringId,
          objectKind: 'gathering',
          routeId: 'gatheringDetail',
        ),
      ),
    ],
  );
}

List<Override> _boundaryOverrides(
  _ExperienceIntersectionRepository repo,
  ContentBehaviorTracker tracker,
) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    intersectionRepositoryProvider.overrideWithValue(repo),
    contentBehaviorTrackerProvider.overrideWithValue(tracker),
  ];
}

Future<void> _pumpCard(
  WidgetTester tester,
  _ExperienceIntersectionRepository repo,
) async {
  final tracker = ContentBehaviorTracker(
    reporter: RecordingContentBehaviorRepository(),
    maxBatchSize: 1,
    enablePeriodicFlush: false,
  );
  addTearDown(tracker.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: _boundaryOverrides(repo, tracker),
      child: CupertinoApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: <GoRoute>[
            GoRoute(
              path: '/',
              builder: (_, _) => const CupertinoPageScaffold(
                child: SingleChildScrollView(
                  child: MyExperienceAssetCard(isDark: false),
                ),
              ),
            ),
            GoRoute(
              path: '/gatherings/:id',
              builder: (_, state) =>
                  Text('GATHERING:${state.pathParameters['id']}'),
            ),
            GoRoute(
              path: '/profile/intersections',
              builder: (_, state) => Text(
                'LIST:${state.uri.queryParameters['sourceRef'] ?? ''}',
              ),
            ),
          ],
        ),
      ),
    ),
  );
  // 防卡死模式：有限帧 pump，不使用 pumpAndSettle。
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  testWidgets('有经历交集时渲染资产卡：云侧主句直出 + 再约一次 pill', (tester) async {
    final repo = _ExperienceIntersectionRepository(
      items: <IntersectionReason>[_experienceReason(count: 2)],
    );
    await _pumpCard(tester, repo);

    // 服务端收窄参数正确（DEC-002 单一真相源）。
    expect(repo.requestedSourceRef, 'coExperiencedGathering');
    expect(repo.requestedFilter, 'fact');

    expect(find.byKey(MyExperienceAssetCard.cardKey), findsOneWidget);
    expect(find.text(DiscoveryFeedText.myExperienceTitle), findsOneWidget);
    expect(find.textContaining('你们一起参加过 2 次行动'), findsOneWidget);
    // 行尾主行动 pill：label 云侧直出（再约一次 = 飞轮复利环）。
    expect(find.byType(IntersectionActionablePill), findsOneWidget);
    expect(find.text('再约一次'), findsOneWidget);
  });

  testWidgets('整行点击回看行动详情（actionTargetId 直通 gathering）', (tester) async {
    final repo = _ExperienceIntersectionRepository(
      items: <IntersectionReason>[
        _experienceReason(gatheringId: 'gathering_x'),
      ],
    );
    await _pumpCard(tester, repo);
    await tester.tap(find.textContaining('你们一起参加过'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('GATHERING:gathering_x'), findsOneWidget);
  });

  testWidgets('无经历交集时整个区块不渲染（诚实空态=不渲染，不放鼓励文案）', (tester) async {
    final repo = _ExperienceIntersectionRepository();
    await _pumpCard(tester, repo);
    expect(find.byKey(MyExperienceAssetCard.cardKey), findsNothing);
    expect(find.text(DiscoveryFeedText.myExperienceTitle), findsNothing);
  });

  testWidgets('读取失败渲染可恢复错误行并可重试，不伪造「暂无经历」空态', (tester) async {
    final repo = _ExperienceIntersectionRepository(
      failure: StateError('intersection read unavailable'),
    );
    await _pumpCard(tester, repo);

    expect(find.byKey(MyExperienceAssetCard.cardKey), findsOneWidget);
    expect(
      find.text(DiscoveryFeedText.myExperienceLoadFailed),
      findsOneWidget,
    );
    expect(find.byKey(MyExperienceAssetCard.retryKey), findsOneWidget);
    expect(repo.listCalls, 1);
  });

  testWidgets('查看全部进入经历过滤的交集列表深链', (tester) async {
    final repo = _ExperienceIntersectionRepository(
      items: <IntersectionReason>[_experienceReason()],
    );
    await _pumpCard(tester, repo);
    await tester.tap(find.text(DiscoveryFeedText.intersectionViewAll));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('LIST:coExperiencedGathering'), findsOneWidget);
  });
}
