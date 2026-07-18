import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/user/widgets/my_intersection_inbox_card.dart';

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
    expect(find.text('你和张可等5位校友都去过「西湖」'), findsOneWidget);
    expect(find.text('你和周屿等2位用户都在「城市漫游圈」'), findsNothing);
    expect(find.text(DiscoveryFeedText.intersectionExpandMore), findsNothing);

    await tester.tap(find.text(DiscoveryFeedText.intersectionViewAll));
    await tester.pumpAndSettle();
    expect(find.text('INBOX:fact::'), findsOneWidget);
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
      find.text(UITextConstants.profileIntersectionEmptyGuidance),
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

  testWidgets('契约 seed 默认 Mock：显示查看全部，不显示展开收起', (tester) async {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const CupertinoApp(
          home: CupertinoPageScaffold(
            child: SafeArea(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: MyIntersectionInboxCard(isDark: false),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(DiscoveryFeedText.myIntersectionsTitle), findsOneWidget);
    expect(find.text(DiscoveryFeedText.intersectionViewAll), findsOneWidget);
    expect(find.text(DiscoveryFeedText.intersectionExpandMore), findsNothing);
    // 真实契约 seed 至少渲染一条 fact 交集预览行，非空态；具体合成句由 T1 合成测试覆盖，
    // 此处不耦合 fixture 措辞，避免 seed 文案演进即误伤卡片行为契约。
    expect(find.byType(InteractiveIntersectionText), findsWidgets);
    expect(
      find.text(UITextConstants.profileIntersectionEmptyGuidance),
      findsNothing,
    );
  });

  testWidgets('primarySpans 名字片段点击进对象主页（优先于整行）', (tester) async {
    final behaviorRepo = MockBehaviorRepository();
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
    final behaviorRepo = MockBehaviorRepository();
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
          final filter = state.uri.queryParameters['filter'] ?? '';
          final src = state.uri.queryParameters['sourceRef'] ?? '';
          final id = state.uri.queryParameters['intersectionId'] ?? '';
          return Text('INBOX:$filter:$src:$id');
        },
      ),
      GoRoute(
        path: '/user/:username',
        builder: (_, state) => Text('USER:${state.pathParameters['username']}'),
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
    _item(id: 'ix_loc_1', text: '你和张可等5位校友都去过「西湖」', strength: 0.76),
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
  return IntersectionReason(
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
      relationLabel: '联系人',
      privacyState: 'visible',
      target: IntersectionTarget(
        objectType: 'user',
        objectId: 'u_zhang',
        objectKind: 'person',
        routeId: 'userProfile',
      ),
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
  _StubIntersectionRepository({required this.items});

  final List<IntersectionReason> items;

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(
      totalCount: items.length,
      totalNewCount: items.length,
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
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}
