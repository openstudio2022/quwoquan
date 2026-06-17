import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_entity.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/user/pages/my_intersection_inbox_page.dart';

void main() {
  testWidgets('我的交集列表：展示云侧对象名与证据，并打开即 visit 清零', (tester) async {
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
          intersectionRepositoryProvider.overrideWithValue(repo),
          behaviorRepositoryProvider.overrideWithValue(behaviorRepo),
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
        ],
        child: CupertinoApp.router(
          routerConfig: GoRouter(
            initialLocation: '/',
            routes: [
              GoRoute(
                path: '/',
                builder: (_, _) => const MyIntersectionInboxPage(),
              ),
              GoRoute(
                path: '/user/:username',
                builder: (_, state) =>
                    Text('USER:${state.pathParameters['username']}'),
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(IntersectionEntity), findsOneWidget);
    expect(find.text('林清越'), findsOneWidget);
    expect(find.text('4 位共同关注'), findsOneWidget);
    expect(repo.visitedDimension, '');

    await tester.tap(find.text('林清越'));
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
      find.text('${UITextConstants.myIntersectionsTitle}暂不可用'),
      findsOneWidget,
    );
  });
}

class _RecordingIntersectionRepository implements IntersectionRepository {
  String? visitedDimension;

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 1, totalNewCount: 1);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    int limit = 50,
  }) async {
    return <IntersectionReason>[
      IntersectionReason(
        dimension: 'relationship',
        intersectionClass: 'fact',
        intersectionId: 'ix_test_rel',
        relationKind: 'person',
        displayName: '林清越',
        primaryText: '4 位共同关注',
        actionTargetId: 'u_lin',
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
  Future<List<IntersectionReason>> getFeedIntersections({
    String? channel,
    int limit = 4,
  }) async {
    return const <IntersectionReason>[];
  }

  @override
  Future<void> reportExposure({required List<String> objectIds}) async {}

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
    int limit = 50,
  }) async {
    throw StateError('intersection unavailable');
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getFeedIntersections({
    String? channel,
    int limit = 4,
  }) async {
    return const <IntersectionReason>[];
  }

  @override
  Future<void> reportExposure({required List<String> objectIds}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}
