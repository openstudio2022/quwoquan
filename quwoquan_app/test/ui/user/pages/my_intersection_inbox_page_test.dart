import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/user/pages/my_intersection_inbox_page.dart';
import 'package:quwoquan_app/ui/user/providers/author_impact_provider.dart';

void main() {
  testWidgets('我的交集列表：展示筛选、时间桶和事实行，并打开即 visit 清零', (tester) async {
    final repo = _RecordingIntersectionRepository();
    final behaviorRepo = MockBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      repository: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          intersectionRepositoryProvider.overrideWithValue(repo),
          behaviorRepositoryProvider.overrideWithValue(behaviorRepo),
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
        ],
        child: CupertinoApp.router(routerConfig: _router()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // 交集 tab 选中：导航标题 + body 一级 tab 同名各一处。
    expect(
      find.text(UITextConstants.profileTabIntersection),
      findsNWidgets(2),
    );
    expect(find.text(UITextConstants.profileTabImpact), findsOneWidget);
    expect(find.text(DiscoveryFeedText.intersectionFilterAll), findsOneWidget);
    expect(
      find.text(DiscoveryFeedText.intersectionFilterPeople),
      findsOneWidget,
    );
    expect(
      find.text(DiscoveryFeedText.intersectionTimeBucketToday),
      findsOneWidget,
    );
    expect(find.text('你和林清越等4位用户都关注「黄金投资圈」'), findsOneWidget);
    expect(find.text(UITextConstants.follow), findsNothing);
    expect(repo.visitedDimension, '');
    expect(repo.requestedFilter, 'fact');

    await tester.tap(find.text('你和林清越等4位用户都关注「黄金投资圈」'));
    await tester.pumpAndSettle();
    expect(find.text('USER:u_lin'), findsOneWidget);
    expect(behaviorRepo.recorded, hasLength(1));
    final event = behaviorRepo.recorded.single;
    expect(event.contentId, 'u_lin');
    expect(event.action, BehaviorAction.click);
    // N10：我的交集中心点击 → 来源精确为 myIntersections（非推荐流 organicFeed）。
    expect(event.referralSource, ReferralSource.myIntersections);
    expect(event.intersectionId, 'ix_test_rel');
    expect(event.intersectionDimension, 'relationship');
    expect(event.intersectionClass, 'fact');
    expect(event.intersectionTagRefs, <String>[
      'tag/relationship/shared_follow',
    ]);
  });

  testWidgets('sourceRef 过滤：只渲染命中证据组的事实交集', (tester) async {
    final repo = _SourceRefIntersectionRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [intersectionRepositoryProvider.overrideWithValue(repo)],
        child: CupertinoApp.router(
          routerConfig: _router(
            page: const MyIntersectionInboxPage(
              dimension: 'relationship',
              sourceRef: 'circle',
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(repo.requestedDimension, 'relationship');
    expect(repo.requestedSourceRef, 'circle');
    expect(find.text('你和阿岚等4位用户都在「城市漫游圈」'), findsOneWidget);
    expect(find.text('你和小航等2位校友都去过「西湖」'), findsNothing);
  });

  testWidgets('我的交集时间轴：跨 5 年展示有 item 的桶，空时间段隐藏', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          intersectionRepositoryProvider.overrideWithValue(
            _FiveYearIntersectionRepository(),
          ),
        ],
        child: CupertinoApp.router(routerConfig: _router()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    final year = DateTime.now().year;
    // 有 item 的桶渲染（今天 + N-2 年 + N-4 年）。
    expect(
      find.text(DiscoveryFeedText.intersectionTimeBucketToday),
      findsOneWidget,
    );
    expect(find.text('${year - 2} 年'), findsOneWidget);
    expect(find.text('${year - 4} 年'), findsOneWidget);
    // 空时间段隐藏（N-1 / N-3 年无 item，不渲染表头）。
    expect(find.text('${year - 1} 年'), findsNothing);
    expect(find.text('${year - 3} 年'), findsNothing);
  });

  testWidgets('我的交集：代表人纯文本蓝字 + 生命周期弱标 + 行动 pill 同行呈现', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          intersectionRepositoryProvider.overrideWithValue(
            _LifecycleIntersectionRepository(),
          ),
        ],
        child: CupertinoApp.router(routerConfig: _router()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // 代表人是句中可点纯文本（无头像 Image）。
    expect(find.textContaining('王然'), findsOneWidget);
    // 生命周期弱标：reactivated → 「重新活跃」。
    expect(
      find.text(DiscoveryFeedText.intersectionLifecycleReactivated),
      findsOneWidget,
    );
    // 行动建议 pill。
    expect(find.text('进入讨论'), findsOneWidget);
    // 行内不出现任何网络图片（代表人改纯文本后，交集行无头像）。
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('filter=impact 时直达影响力一级 tab', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          authorImpactProvider.overrideWith((ref, userId) async {
            return AuthorImpactSummary(
              authorId: userId,
              total: 1,
              items: <AuthorImpactItem>[
                AuthorImpactItem(
                  intersectionDimension: 'content',
                  source: 'content_share',
                  count: 8,
                  primaryText: '8人因为你的记录收藏了路线',
                ),
              ],
            );
          }),
        ],
        child: CupertinoApp.router(
          routerConfig: _router(
            page: const MyIntersectionInboxPage(filter: 'impact'),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.profileTabIntersection), findsOneWidget);
    // 影响力 tab 选中：导航标题 + body 一级 tab 同名各一处。
    expect(find.text(UITextConstants.profileTabImpact), findsNWidgets(2));
    expect(find.text('8人因为你的记录收藏了路线'), findsOneWidget);
    expect(find.text(DiscoveryFeedText.intersectionFilterPeople), findsNothing);
  });

  testWidgets('我的交集页加载失败时展示统一页态', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          intersectionRepositoryProvider.overrideWithValue(
            _FailingIntersectionRepository(),
          ),
        ],
        child: const CupertinoApp(home: MyIntersectionInboxPage()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(
      find.text('${DiscoveryFeedText.myIntersectionsTitle}暂不可用'),
      findsOneWidget,
    );
  });
}

GoRouter _router({Widget page = const MyIntersectionInboxPage()}) {
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(path: '/', builder: (_, _) => page),
      GoRoute(
        path: '/user/:username',
        builder: (_, state) => Text('USER:${state.pathParameters['username']}'),
      ),
    ],
  );
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'test-token',
      ownerId: 'test-user',
      activeSubAccountId: 'test-sub-account',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}

class _RecordingIntersectionRepository implements IntersectionRepository {
  String? visitedDimension;
  String? requestedFilter;

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 1, totalNewCount: 1);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    requestedFilter = filter;
    return <IntersectionReason>[
      IntersectionReason(
        dimension: 'relationship',
        intersectionClass: 'fact',
        intersectionId: 'ix_test_rel',
        objectKind: 'person',
        displayName: '林清越',
        primaryText: '你和林清越等4位用户都关注「黄金投资圈」',
        actionTargetId: 'u_lin',
        source: 'sharedEntityAttention',
        timeBucket: 'today',
        tagRefs: const <String>['tag/relationship/shared_follow'],
        freshAt: DateTime.now().toUtc().toIso8601String(),
      ),
    ];
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {
    visitedDimension = dimension ?? '';
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

class _SourceRefIntersectionRepository implements IntersectionRepository {
  String? requestedDimension;
  String? requestedSourceRef;

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 2, totalNewCount: 1);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    requestedDimension = dimension;
    requestedSourceRef = sourceRef;
    final items = <IntersectionReason>[
      IntersectionReason(
        dimension: 'relationship',
        intersectionClass: 'fact',
        intersectionId: 'ix_circle',
        objectKind: 'circle',
        source: 'circle',
        primaryText: '你和阿岚等4位用户都在「城市漫游圈」',
        actionTargetId: 'fixture_circle_city',
        timeBucket: 'today',
        freshAt: DateTime.now().toUtc().toIso8601String(),
      ),
      IntersectionReason(
        dimension: 'location',
        intersectionClass: 'fact',
        intersectionId: 'ix_place',
        objectKind: 'place',
        source: 'place',
        primaryText: '你和小航等2位校友都去过「西湖」',
        actionTargetId: 'homepage_sight_west_lake',
        timeBucket: 'today',
        freshAt: DateTime.now().toUtc().toIso8601String(),
      ),
    ];
    return items
        .where((item) => sourceRef == null || item.source == sourceRef)
        .toList(growable: false);
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

class _FiveYearIntersectionRepository implements IntersectionRepository {
  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 3, totalNewCount: 1);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    final year = DateTime.now().year;
    // 三个不同对象、不同时间桶（今天 / N-2 年 / N-4 年），中间年份留空验证隐藏。
    return <IntersectionReason>[
      IntersectionReason(
        dimension: 'relationship',
        intersectionClass: 'fact',
        intersectionId: 'ix_year_today',
        objectKind: 'person',
        displayName: '林清越',
        primaryText: '你关注的4人也关注了林清越',
        actionTargetId: 'fixture_user_lin',
        timeBucket: 'today',
        freshAt: DateTime.now().toUtc().toIso8601String(),
      ),
      IntersectionReason(
        dimension: 'identity',
        intersectionClass: 'fact',
        intersectionId: 'ix_year_minus2',
        objectKind: 'school',
        displayName: '新东方',
        primaryText: '你和3位校友都来自新东方',
        actionTargetId: 'fixture_homepage_university_pku',
        timeBucket: 'year:${year - 2}',
        freshAt: DateTime.now().toUtc().toIso8601String(),
      ),
      IntersectionReason(
        dimension: 'location',
        intersectionClass: 'fact',
        intersectionId: 'ix_year_minus4',
        objectKind: 'place',
        displayName: '西湖',
        primaryText: '你和5人都去过西湖',
        actionTargetId: 'homepage_sight_west_lake',
        timeBucket: 'year:${year - 4}',
        freshAt: DateTime.now().toUtc().toIso8601String(),
      ),
    ];
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

class _LifecycleIntersectionRepository implements IntersectionRepository {
  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 1, totalReactivatedCount: 1);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    return <IntersectionReason>[
      IntersectionReason(
        dimension: 'content',
        intersectionClass: 'fact',
        intersectionId: 'ix_lifecycle',
        objectKind: 'circle',
        displayName: '黄金投资圈',
        actionTargetId: 'fixture_circle_gold_invest',
        timeBucket: 'today',
        lifecycleState: 'reactivated',
        iconKey: 'discussion',
        freshAt: DateTime.now().toUtc().toIso8601String(),
        primaryText: '你和王然等8人都讨论过黄金投资圈',
        primarySpans: <IntersectionTextSpan>[
          IntersectionTextSpan(text: '你和', role: 'plain'),
          IntersectionTextSpan(
            text: '王然',
            role: 'object',
            target: IntersectionTarget(
              objectId: 'fixture_user_photo',
              objectKind: 'person',
              routeId: 'userProfile',
            ),
          ),
          IntersectionTextSpan(text: '等', role: 'plain'),
          IntersectionTextSpan(
            text: '8',
            role: 'count',
            target: IntersectionTarget(
              objectId: 'content',
              routeId: 'myIntersections',
            ),
          ),
          IntersectionTextSpan(text: '人都讨论过', role: 'plain'),
          IntersectionTextSpan(
            text: '黄金投资圈',
            role: 'object',
            target: IntersectionTarget(
              objectId: 'fixture_circle_gold_invest',
              objectKind: 'circle',
              routeId: 'circleDetail',
            ),
          ),
        ],
        actionHints: <IntersectionActionHint>[
          IntersectionActionHint(
            actionKey: 'open_discussion',
            label: '进入讨论',
            isPrimary: true,
            priority: 1,
          ),
        ],
      ),
    ];
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

class _FailingIntersectionRepository implements IntersectionRepository {
  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 0, totalNewCount: 0);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    throw StateError('intersection unavailable');
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}
