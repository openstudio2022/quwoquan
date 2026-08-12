import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/interactive_intersection_text.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_intersection_inbox_card.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

bool _tapSpanByText(WidgetTester tester, String text) {
  final richText = tester.widget<RichText>(
    find.descendant(
      of: find.byType(InteractiveIntersectionText),
      matching: find.byType(RichText),
    ),
  );
  var hit = false;
  richText.text.visitChildren((span) {
    if (span is TextSpan && span.text == text) {
      final recognizer = span.recognizer;
      if (recognizer is TapGestureRecognizer && recognizer.onTap != null) {
        recognizer.onTap!();
        hit = true;
        return false;
      }
    }
    return true;
  });
  return hit;
}

TextSpan _spanByText(WidgetTester tester, String text) {
  final richText = tester.widget<RichText>(
    find.descendant(
      of: find.byType(InteractiveIntersectionText),
      matching: find.byType(RichText),
    ),
  );
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

void main() {
  Widget host(IntersectionRepository repo) {
    return ProviderScope(
      overrides: [intersectionRepositoryProvider.overrideWithValue(repo)],
      child: CupertinoApp.router(
        routerConfig: _router(
          builder: () => const MyIntersectionInboxCard(isDark: false),
        ),
      ),
    );
  }

  Widget spanHost(IntersectionRepository repo, ContentBehaviorTracker tracker) {
    return ProviderScope(
      overrides: [
        intersectionRepositoryProvider.overrideWithValue(repo),
        contentBehaviorTrackerProvider.overrideWithValue(tracker),
      ],
      child: CupertinoApp.router(
        routerConfig: _router(
          builder: () => const MyIntersectionInboxCard(isDark: false),
        ),
      ),
    );
  }

  testWidgets('主页只展示 3 条真实 fact 交集，并提供查看全部', (tester) async {
    final repo = _StubIntersectionRepository(items: _items(4));

    await tester.pumpWidget(host(repo));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(DiscoveryFeedText.myIntersectionsTitle), findsOneWidget);
    expect(find.text(DiscoveryFeedText.intersectionViewAll), findsOneWidget);
    expect(find.text('你和林清越等4位用户都关注「黄金投资圈」'), findsOneWidget);
    expect(find.text('你和王然等8位用户都参与「黄金投资圈」'), findsOneWidget);
    expect(find.text('你和张可等5位校友都看过「西湖」'), findsOneWidget);
    expect(find.text('你和周屿等2位用户都在「城市漫游圈」'), findsNothing);
    expect(find.text(DiscoveryFeedText.intersectionExpandMore), findsNothing);

    await tester.tap(find.text(DiscoveryFeedText.intersectionViewAll));
    await tester.pumpAndSettle();
    expect(find.text('INBOX:fact::'), findsOneWidget);
  });

  testWidgets('主页展示 Remote 总数与最多三个维度新增，并按维度下钻', (tester) async {
    final repo = _StubIntersectionRepository(
      items: _items(4),
      summary: IntersectionInboxSummary(
        totalCount: 4,
        totalNewCount: 10,
        dimensions: <IntersectionDimensionTally>[
          _dimensionTally('relationship', '关系', 4),
          _dimensionTally('location', '足迹', 3),
          _dimensionTally('identity', '身份', 2),
          _dimensionTally('content', '内容', 1),
        ],
        generatedAt: '2026-08-10T00:00:00Z',
        totalStrengthenedCount: 0,
        totalReactivatedCount: 0,
      ),
    );

    await tester.pumpWidget(host(repo));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('4 个交集'), findsOneWidget);
    expect(find.text('关系 4条新增'), findsOneWidget);
    expect(find.text('足迹 3条新增'), findsOneWidget);
    expect(find.text('身份 2条新增'), findsOneWidget);
    expect(find.text('内容 1条新增'), findsNothing);

    await tester.tap(
      find.byKey(
        const ValueKey<String>('my-intersections-dimension-relationship'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('DIMENSION:relationship'), findsOneWidget);
  });

  testWidgets('点击事实行进入我的交集详情过滤页', (tester) async {
    final repo = _StubIntersectionRepository(items: _items(1));

    await tester.pumpWidget(host(repo));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    await tester.tap(find.text('你和林清越等4位用户都关注「黄金投资圈」'));
    await tester.pumpAndSettle();
    expect(find.text('INBOX:fact::ix_rel_1'), findsOneWidget);
  });

  testWidgets('无 fact 交集时展示高保空态文案', (tester) async {
    final repo = _StubIntersectionRepository(
      items: const <IntersectionReason>[],
    );

    await tester.pumpWidget(host(repo));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(
      find.text(ProfileText.profileIntersectionEmptyGuidance),
      findsOneWidget,
    );
  });

  testWidgets('缺少主句的 fact 条目不展示，避免空白预览行', (tester) async {
    final repo = _StubIntersectionRepository(
      items: <IntersectionReason>[
        _item(id: 'ix_blank', text: '   '),
        _item(id: 'ix_rel_1', text: '你和林清越等4位用户都关注「黄金投资圈」'),
      ],
    );

    await tester.pumpWidget(host(repo));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('你和林清越等4位用户都关注「黄金投资圈」'), findsOneWidget);
    expect(find.text('   '), findsNothing);
    expect(find.byType(InteractiveIntersectionText), findsOneWidget);
  });

  testWidgets('primarySpans 名字片段点击进对象主页（优先于整行）', (tester) async {
    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);
    final repo = _StubIntersectionRepository(
      items: <IntersectionReason>[
        _item(
          id: 'ix_span',
          text: '你和张晓明等3位用户都在「摄影圈」',
          spans: _spans(
            anchorName: '张晓明',
            count: '3',
            objectName: '摄影圈',
            sourceRef: 'sharedCircle',
          ),
        ),
      ],
    );

    await tester.pumpWidget(spanHost(repo, tracker));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(_tapSpanByText(tester, '张晓明'), isTrue);
    await tester.pumpAndSettle();

    expect(find.text('USER:u_zhang'), findsOneWidget);
    expect(find.textContaining('INBOX:'), findsNothing);
    expect(behaviorRepo.recorded.single.contentId, 'u_zhang');
  });

  testWidgets('主页交集名字和数字蓝色但保持普通字重', (tester) async {
    final repo = _StubIntersectionRepository(
      items: <IntersectionReason>[
        _item(
          id: 'ix_span',
          text: '你和张晓明等3位用户都在「摄影圈」',
          spans: _spans(
            anchorName: '张晓明',
            count: '3',
            objectName: '摄影圈',
            sourceRef: 'sharedCircle',
          ),
        ),
      ],
    );

    await tester.pumpWidget(host(repo));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byKey(MyIntersectionInboxCard.cardKey), findsOneWidget);
    expect(_spanByText(tester, '张晓明').style?.fontWeight, AppTypography.regular);
    expect(_spanByText(tester, '3').style?.fontWeight, AppTypography.regular);
    // 统一交互蓝字采用低饱和 slogan-accent（浅色态）。
    final accent = AppColors.profileSloganAccentLight;
    expect(_spanByText(tester, '张晓明').style?.color, accent);
    expect(_spanByText(tester, '3').style?.color, accent);
  });

  testWidgets('primarySpans 数字片段点击进入成员过滤列表并带 sourceRef', (tester) async {
    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);
    final repo = _StubIntersectionRepository(
      items: <IntersectionReason>[
        _item(
          id: 'ix_span',
          text: '你和张晓明等3位用户都在「摄影圈」',
          source: 'sharedCircle',
          spans: _spans(
            anchorName: '张晓明',
            count: '3',
            objectName: '摄影圈',
            sourceRef: 'sharedCircle',
          ),
        ),
      ],
    );

    await tester.pumpWidget(spanHost(repo, tracker));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(_tapSpanByText(tester, '3'), isTrue);
    await tester.pumpAndSettle();

    expect(find.textContaining('sharedCircle'), findsOneWidget);
  });
}

GoRouter _router({required Widget Function() builder}) {
  return GoRouter(
    initialLocation: '/',
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (_, _) =>
            CupertinoPageScaffold(child: SafeArea(child: builder())),
      ),
      GoRoute(
        path: '/profile/intersections',
        builder: (_, state) {
          final dimension = state.uri.queryParameters['dimension'] ?? '';
          final filter = state.uri.queryParameters['filter'] ?? '';
          final src = state.uri.queryParameters['sourceRef'] ?? '';
          final id = state.uri.queryParameters['intersectionId'] ?? '';
          return Column(
            children: <Widget>[
              Text('INBOX:$filter:$src:$id'),
              Text('DIMENSION:$dimension'),
            ],
          );
        },
      ),
      GoRoute(
        path: '/user/:userHandle',
        builder: (_, state) =>
            Text('USER:${state.pathParameters['userHandle']}'),
      ),
    ],
  );
}

List<IntersectionReason> _items(int count) {
  return <IntersectionReason>[
    _item(id: 'ix_rel_1', text: '你和林清越等4位用户都关注「黄金投资圈」', strength: 0.9),
    _item(
      id: 'ix_ct_1',
      text: '你和王然等8位用户都参与「黄金投资圈」',
      strength: 0.88,
      timeBucket: 'yesterday',
    ),
    _item(id: 'ix_loc_1', text: '你和张可等5位校友都看过「西湖」', strength: 0.76),
    _item(
      id: 'ix_circle_1',
      text: '你和周屿等2位用户都在「城市漫游圈」',
      strength: 0.7,
      timeBucket: 'last7Days',
    ),
  ].take(count).toList(growable: false);
}

IntersectionReason _item({
  required String id,
  required String text,
  List<IntersectionTextSpan> spans = const <IntersectionTextSpan>[],
  String source = 'sharedEntityAttention',
  String timeBucket = 'today',
  double strength = 0.8,
}) {
  final target = IntersectionTarget(
    objectType: 'circle',
    objectId: 'fixture_circle_gold_invest',
    objectKind: 'circle',
    routeId: 'circleDetail',
  );
  return intersectionReasonFixture(
    dimension: 'relationship',
    intersectionClass: 'fact',
    intersectionId: id,
    objectKind: 'circle',
    primaryText: text,
    primarySpans: spans.isEmpty
        ? <IntersectionTextSpan>[
            IntersectionTextSpan(text: text, role: 'object', target: target),
          ]
        : spans,
    actionTargetId: 'fixture_circle_gold_invest',
    source: source,
    timeBucket: timeBucket,
    dedupeKey: 'viewer:$id',
    strength: strength,
    freshAt: DateTime.now().toUtc().toIso8601String(),
    actorEvidenceTotalCount: 1,
    actorEvidenceCompleteness: 'complete',
    representativeActor: IntersectionRepresentativeActor(
      actorId: 'u_zhang',
      displayName: '张晓明',
      avatarUrl: '',
      relationLabel: '联系人',
      privacyState: 'visible',
      target: IntersectionTarget(
        objectType: 'user',
        objectId: 'u_zhang',
        objectKind: 'person',
        routeId: 'userProfile',
      ),
      evidenceRank: 1,
      snapshotVersion: 'intersection_fixture',
    ),
  );
}

List<IntersectionTextSpan> _spans({
  required String anchorName,
  required String count,
  required String objectName,
  required String sourceRef,
}) {
  return <IntersectionTextSpan>[
    IntersectionTextSpan(text: '你和', role: 'plain'),
    IntersectionTextSpan(
      text: anchorName,
      role: 'object',
      target: IntersectionTarget(
        objectType: 'user',
        objectId: 'u_zhang',
        objectKind: 'person',
        routeId: 'userProfile',
      ),
    ),
    IntersectionTextSpan(text: '等', role: 'plain'),
    IntersectionTextSpan(
      text: count,
      role: 'count',
      target: IntersectionTarget(
        objectType: 'dimension',
        objectId: 'relationship',
        objectKind: 'dimension',
        routeId: 'myIntersections',
      ),
    ),
    IntersectionTextSpan(text: '位用户都在「', role: 'plain'),
    IntersectionTextSpan(
      text: objectName,
      role: 'object',
      target: IntersectionTarget(
        objectType: 'circle',
        objectId: 'fixture_circle_gold_invest',
        objectKind: 'circle',
        routeId: 'circleDetail',
      ),
    ),
    IntersectionTextSpan(text: '」', role: 'plain'),
  ];
}

class _StubIntersectionRepository implements IntersectionRepository {
  _StubIntersectionRepository({required this.items, this.summary});

  final List<IntersectionReason> items;
  final IntersectionInboxSummary? summary;

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return summary ??
        IntersectionInboxSummary(
          totalCount: items.length,
          totalNewCount: items.length,
          dimensions: const [],
          generatedAt: '2026-08-03T00:00:00Z',
          totalStrengthenedCount: 0,
          totalReactivatedCount: 0,
        );
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
    return items.take(limit).toList(growable: false);
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

IntersectionDimensionTally _dimensionTally(
  String dimension,
  String label,
  int newCount,
) {
  return IntersectionDimensionTally(
    dimension: dimension,
    label: label,
    count: newCount,
    newCount: newCount,
    briefText: '',
    subtitleText: '',
    briefSpans: const <IntersectionTextSpan>[],
    sampleVisuals: const <IntersectionVisual>[],
    sourceRef: dimension,
    countObjectKind: 'dimension',
    strengthenedCount: 0,
    reactivatedCount: 0,
    iconKey: dimension,
  );
}
