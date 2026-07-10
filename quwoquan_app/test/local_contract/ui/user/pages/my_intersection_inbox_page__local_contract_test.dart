import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_list_page_semantics.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/user/pages/my_intersection_inbox_page.dart';
import 'package:quwoquan_app/ui/user/providers/author_impact_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/my_intersection_inbox_timeline.dart';

TextSpan _spanByText(RichText richText, String text) {
  TextSpan? result;
  richText.text.visitChildren((span) {
    if (span is TextSpan && span.text == text) {
      result = span;
      return false;
    }
    return true;
  });
  return result!;
}

IntersectionReason _displayableInboxReason({
  required String dimension,
  required String intersectionId,
  required String objectKind,
  required String primaryText,
  required String actionTargetId,
  required String source,
  String intersectionClass = 'fact',
  String displayName = '',
  String timeBucket = 'today',
  List<String> tagRefs = const <String>[],
  List<IntersectionTextSpan>? primarySpans,
  List<IntersectionPoint> intersectionPoints = const <IntersectionPoint>[],
  List<IntersectionActionHint> actionHints = const <IntersectionActionHint>[],
  String lifecycleState = '',
  String iconKey = '',
  String representativeName = '林清越',
  String representativeId = 'u_lin',
}) {
  final target = _targetFor(objectKind: objectKind, objectId: actionTargetId);
  return IntersectionReason(
    dimension: dimension,
    intersectionClass: intersectionClass,
    intersectionId: intersectionId,
    objectKind: objectKind,
    displayName: displayName,
    primaryText: primaryText,
    primarySpans:
        primarySpans ??
        <IntersectionTextSpan>[
          IntersectionTextSpan(
            text: primaryText,
            role: 'object',
            target: target,
          ),
        ],
    actionTargetId: actionTargetId,
    source: source,
    timeBucket: timeBucket,
    tagRefs: tagRefs,
    freshAt: DateTime.now().toUtc().toIso8601String(),
    actorEvidenceTotalCount: 1,
    actorEvidenceCompleteness: 'complete',
    representativeActor: IntersectionRepresentativeActor(
      actorId: representativeId,
      displayName: representativeName,
      relationLabel: '联系人',
      privacyState: 'visible',
      target: _targetFor(objectKind: 'person', objectId: representativeId),
    ),
    intersectionPoints: intersectionPoints,
    actionHints: actionHints,
    lifecycleState: lifecycleState,
    iconKey: iconKey,
  );
}

IntersectionTarget _targetFor({
  required String objectKind,
  required String objectId,
}) {
  switch (objectKind.trim()) {
    case 'person':
      return IntersectionTarget(
        objectType: 'user',
        objectId: objectId,
        objectKind: 'person',
        routeId: 'userProfile',
      );
    case 'circle':
      return IntersectionTarget(
        objectType: 'circle',
        objectId: objectId,
        objectKind: 'circle',
        routeId: 'circleDetail',
      );
    case 'dimension':
      return IntersectionTarget(
        objectType: 'dimension',
        objectId: objectId,
        objectKind: 'dimension',
        routeId: 'myIntersections',
      );
    case 'content':
      return IntersectionTarget(
        objectType: 'post',
        objectId: objectId,
        objectKind: 'content',
        routeId: 'workBrowser',
      );
    case 'place':
    case 'school':
    default:
      return IntersectionTarget(
        objectType: 'homepage',
        objectId: objectId,
        objectKind: objectKind,
        routeId: 'homepageDetail',
      );
  }
}

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

    // 交集/打动已收敛到 nav center compact switch；body 不再重复一级 segmented。
    expect(find.text(UITextConstants.profileTabIntersection), findsOneWidget);
    expect(find.text(UITextConstants.profileTabImpact), findsOneWidget);
    expect(
      find.byWidgetPredicate((widget) => widget is AppSegmentedChoiceBar),
      findsNothing,
    );
    expect(find.text(DiscoveryFeedText.intersectionFilterAll), findsOneWidget);
    expect(
      find.text(DiscoveryFeedText.intersectionFilterPeople),
      findsOneWidget,
    );
    expect(find.text('今天 1条'), findsOneWidget);
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

  testWidgets('负反馈真实入口：长按交集条目「不感兴趣」→ trackIntersectionFeedback（端云同源）', (
    tester,
  ) async {
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

    // 长按交集条目触发负反馈入口 → action sheet 出现「不感兴趣」。
    await tester.longPress(find.text('你和林清越等4位用户都关注「黄金投资圈」'));
    await tester.pumpAndSettle();
    expect(find.text(UITextConstants.notInterested), findsOneWidget);

    await tester.tap(find.text(UITextConstants.notInterested));
    await tester.pumpAndSettle();

    // 负反馈事件端云同源：intersection_feedback + subjectId(=coolKey actionTargetId) +
    // feedbackKind ∈ registry 闭集 + 同一漏斗归因键。
    final event = behaviorRepo.recorded.singleWhere(
      (e) => e.action == BehaviorAction.intersectionFeedback,
    );
    expect(event.subjectId, 'u_lin');
    expect(event.feedbackKind, intersectionFeedbackKindNotInterested);
    expect(intersectionFeedbackKinds, contains(event.feedbackKind));
    expect(event.intersectionId, 'ix_test_rel');
    expect(event.intersectionDimension, 'relationship');
    expect(event.intersectionClass, 'fact');
    expect(event.contentId, '');
    // 即时确认提示。
    expect(
      find.text(DiscoveryFeedText.feedNegativeFeedbackNotInterested),
      findsWidgets,
    );
    // 清空 AppToast 3 秒自动消失定时器，避免 pending timer 报错。
    await tester.pump(const Duration(seconds: 3));
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

  testWidgets('我的交集时间轴：仅展示最近 5 个互斥时间桶，旧年份桶隐藏', (tester) async {
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
    expect(find.text('今天 1条'), findsOneWidget);
    expect(find.text('${year - 2} 年'), findsNothing);
    expect(find.text('${year - 4} 年'), findsNothing);
    expect(
      find.text('- ${DiscoveryFeedText.intersectionTimelineRecentLimitNote} -'),
      findsOneWidget,
    );
  });

  testWidgets('我的交集：紧凑 row 展示 lifecycle 弱标，但不展示 secondary/行动 pill', (
    tester,
  ) async {
    final repo = _LifecycleIntersectionRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          intersectionRepositoryProvider.overrideWithValue(repo),
        ],
        child: CupertinoApp.router(routerConfig: _router()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.textContaining('王然'), findsOneWidget);
    // 列表入口 inbox 按 spec §21.6 四槽④ 渲染 lifecycle 弱标（reactivated→重新活跃）；
    // 弱标为独立提示（不进结论句 G2），故结论句仍无 secondary、无行动 pill。
    expect(
      find.text(DiscoveryFeedText.intersectionLifecycleReactivated),
      findsOneWidget,
    );
    expect(find.text('进入讨论'), findsNothing);
    expect(find.byType(Image), findsNothing);
    final rowSize = tester.getSize(find.byType(IntersectionCompactTimelineRow));
    expect(rowSize.height, inInclusiveRange(60, 64));

    final rowRichTexts = tester.widgetList<RichText>(
      find.descendant(
        of: find.byType(IntersectionCompactTimelineRow).first,
        matching: find.byType(RichText),
      ),
    );
    final richText = rowRichTexts.firstWhere(
      (widget) => widget.text.toPlainText().contains('王然'),
    );
    final countSpan = _spanByText(richText, '8');
    (countSpan.recognizer! as TapGestureRecognizer).onTap!();
    await tester.pumpAndSettle();
    expect(repo.requestedDimension, 'content');
    expect(repo.requestedSourceRef, 'coCommented');
    expect(find.textContaining('王然'), findsOneWidget);
  });

  testWidgets('filter=impact 时直达打动一级 tab', (tester) async {
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
    expect(find.text(UITextConstants.profileTabImpact), findsOneWidget);
    expect(find.text(DiscoveryFeedText.impactFilterRecords), findsOneWidget);
    expect(
      find.text(DiscoveryFeedText.impactFilterDiscussions),
      findsOneWidget,
    );
    expect(find.text(DiscoveryFeedText.impactFilterHomepage), findsOneWidget);
    expect(find.text('内容'), findsNothing);
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
        path: '/profile/intersections',
        builder: (_, state) =>
            MyIntersectionInboxPage.fromQuery(state.uri.queryParameters),
      ),
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
      _displayableInboxReason(
        dimension: 'relationship',
        intersectionId: 'ix_test_rel',
        objectKind: 'person',
        displayName: '林清越',
        primaryText: '你和林清越等4位用户都关注「黄金投资圈」',
        actionTargetId: 'u_lin',
        source: 'sharedEntityAttention',
        tagRefs: const <String>['tag/relationship/shared_follow'],
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
      _displayableInboxReason(
        dimension: 'relationship',
        intersectionId: 'ix_circle',
        objectKind: 'circle',
        source: 'circle',
        primaryText: '你和阿岚等4位用户都在「城市漫游圈」',
        actionTargetId: 'fixture_circle_city',
        representativeName: '阿岚',
        representativeId: 'u_alan',
      ),
      _displayableInboxReason(
        dimension: 'location',
        intersectionId: 'ix_place',
        objectKind: 'place',
        source: 'place',
        primaryText: '你和小航等2位校友都去过「西湖」',
        actionTargetId: 'homepage_sight_west_lake',
        representativeName: '小航',
        representativeId: 'u_xiaohang',
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
      _displayableInboxReason(
        dimension: 'relationship',
        intersectionId: 'ix_year_today',
        objectKind: 'person',
        displayName: '林清越',
        primaryText: '你关注的4人也关注了林清越',
        actionTargetId: 'fixture_user_lin',
        source: 'sharedFollowees',
      ),
      _displayableInboxReason(
        dimension: 'identity',
        intersectionId: 'ix_year_minus2',
        objectKind: 'school',
        displayName: '新东方',
        primaryText: '你和3位校友都来自新东方',
        actionTargetId: 'fixture_homepage_school_neworiental',
        source: 'identity',
        timeBucket: 'year:${year - 2}',
      ),
      _displayableInboxReason(
        dimension: 'location',
        intersectionId: 'ix_year_minus4',
        objectKind: 'place',
        displayName: '西湖',
        primaryText: '你和5人都去过西湖',
        actionTargetId: 'homepage_sight_west_lake',
        source: 'place',
        timeBucket: 'year:${year - 4}',
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
  String? requestedDimension;
  String? requestedSourceRef;

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
    requestedDimension = dimension;
    requestedSourceRef = sourceRef;
    return <IntersectionReason>[
      _displayableInboxReason(
        dimension: 'content',
        intersectionId: 'ix_lifecycle',
        objectKind: 'circle',
        source: 'content',
        displayName: '黄金投资圈',
        actionTargetId: 'fixture_circle_gold_invest',
        lifecycleState: 'reactivated',
        iconKey: 'discussion',
        primaryText: '你和王然等8人都讨论过黄金投资圈',
        primarySpans: <IntersectionTextSpan>[
          IntersectionTextSpan(text: '你和', role: 'plain'),
          IntersectionTextSpan(
            text: '王然',
            role: 'object',
            target: IntersectionTarget(
              objectType: 'user',
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
              objectType: 'dimension',
              objectId: 'content',
              objectKind: 'dimension',
              routeId: 'myIntersections',
            ),
          ),
          IntersectionTextSpan(text: '人都讨论过', role: 'plain'),
          IntersectionTextSpan(
            text: '黄金投资圈',
            role: 'object',
            target: IntersectionTarget(
              objectType: 'circle',
              objectId: 'fixture_circle_gold_invest',
              objectKind: 'circle',
              routeId: 'circleDetail',
            ),
          ),
        ],
        intersectionPoints: <IntersectionPoint>[
          IntersectionPoint(
            pointId: 'p_lifecycle',
            sourceRef: 'coCommented',
            count: 8,
            dimension: 'content',
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
        representativeName: '王然',
        representativeId: 'fixture_user_photo',
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
