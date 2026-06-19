import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/user/pages/my_intersection_inbox_page.dart';

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

    expect(find.text(DiscoveryFeedText.intersectionFilterAll), findsOneWidget);
    expect(find.text(DiscoveryFeedText.intersectionFilterPeople), findsOneWidget);
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
    expect(event.referralSource, ReferralSource.organicFeed);
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
    int limit = 50,
  }) async {
    requestedFilter = filter;
    return <IntersectionReason>[
      IntersectionReason(
        dimension: 'relationship',
        intersectionClass: 'fact',
        intersectionId: 'ix_test_rel',
        relationKind: 'person',
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
    int limit = 50,
  }) async {
    requestedDimension = dimension;
    requestedSourceRef = sourceRef;
    final items = <IntersectionReason>[
      IntersectionReason(
        dimension: 'relationship',
        intersectionClass: 'fact',
        intersectionId: 'ix_circle',
        relationKind: 'circle',
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
        relationKind: 'place',
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
