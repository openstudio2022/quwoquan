import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/footprint_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/user/pages/my_footprint_page.dart';

void main() {
  testWidgets('我的足迹：渲染条目，点击带 referralSource 进作品浏览器', (tester) async {
    final repo = _StubFootprintRepository(
      pages: <CursorPage<FootprintEntry>>[
        CursorPage<FootprintEntry>(
          items: <FootprintEntry>[
            _entry('post_a', 'view'),
            _entry('post_b', 'like'),
          ],
        ),
      ],
    );
    final behaviorRepo = MockBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          footprintRepositoryProvider.overrideWithValue(repo),
          behaviorRepositoryProvider.overrideWithValue(behaviorRepo),
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
        ],
        child: CupertinoApp.router(
          routerConfig: GoRouter(
            initialLocation: '/',
            routes: [
              GoRoute(path: '/', builder: (_, _) => const MyFootprintPage()),
              GoRoute(
                path: '/works/browser/:workId',
                builder: (_, state) =>
                    Text('WORK:${state.pathParameters['workId']}'),
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.myFootprintTitle), findsOneWidget);
    expect(find.text(UITextConstants.myFootprintPrivacyHint), findsOneWidget);
    expect(find.text('post_a'), findsOneWidget);
    expect(find.text('post_b'), findsOneWidget);

    await tester.tap(find.text('post_a'));
    await tester.pumpAndSettle();
    expect(find.text('WORK:post_a'), findsOneWidget);
    expect(behaviorRepo.recorded, hasLength(1));
    final event = behaviorRepo.recorded.single;
    expect(event.contentId, 'post_a');
    expect(event.action, BehaviorAction.click);
    expect(event.referralSource, ReferralSource.authorProfile);
  });

  testWidgets('我的足迹：type 过滤透传云侧枚举', (tester) async {
    final repo = _StubFootprintRepository(
      pages: <CursorPage<FootprintEntry>>[
        CursorPage<FootprintEntry>(
          items: <FootprintEntry>[_entry('post_all', 'view')],
        ),
        CursorPage<FootprintEntry>(
          items: <FootprintEntry>[_entry('post_liked', 'like')],
        ),
      ],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [footprintRepositoryProvider.overrideWithValue(repo)],
        child: const CupertinoApp(home: MyFootprintPage()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(repo.requestedTypes, <String?>[null]);
    expect(find.text('post_all'), findsOneWidget);

    await tester.tap(find.text(UITextConstants.footprintTypeLabel('liked')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(repo.requestedTypes, <String?>[null, 'liked']);
    expect(find.text('post_liked'), findsOneWidget);
    expect(find.text('post_all'), findsNothing);
  });

  testWidgets('我的足迹：cursor 分页加载更多追加条目', (tester) async {
    final repo = _StubFootprintRepository(
      pages: <CursorPage<FootprintEntry>>[
        CursorPage<FootprintEntry>(
          items: <FootprintEntry>[_entry('post_1', 'view')],
          nextCursor: '1',
        ),
        CursorPage<FootprintEntry>(
          items: <FootprintEntry>[_entry('post_2', 'comment')],
        ),
      ],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [footprintRepositoryProvider.overrideWithValue(repo)],
        child: const CupertinoApp(home: MyFootprintPage()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('post_1'), findsOneWidget);
    expect(find.text(UITextConstants.myFootprintLoadMore), findsOneWidget);

    await tester.tap(find.text(UITextConstants.myFootprintLoadMore));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(repo.requestedCursors, <String?>[null, '1']);
    expect(find.text('post_1'), findsOneWidget);
    expect(find.text('post_2'), findsOneWidget);
    expect(find.text(UITextConstants.myFootprintLoadMore), findsNothing);
  });

  testWidgets('我的足迹：加载失败展示统一页态并可重试', (tester) async {
    final repo = _FailingFootprintRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [footprintRepositoryProvider.overrideWithValue(repo)],
        child: const CupertinoApp(home: MyFootprintPage()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(
      find.text('${UITextConstants.myFootprintTitle}暂不可用'),
      findsOneWidget,
    );
  });

  testWidgets('我的足迹：空列表展示空态文案', (tester) async {
    final repo = _StubFootprintRepository(
      pages: <CursorPage<FootprintEntry>>[
        const CursorPage<FootprintEntry>(items: <FootprintEntry>[]),
      ],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [footprintRepositoryProvider.overrideWithValue(repo)],
        child: const CupertinoApp(home: MyFootprintPage()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.myFootprintEmpty), findsOneWidget);
  });
}

FootprintEntry _entry(String postId, String action) {
  return FootprintEntry(
    postId: postId,
    action: action,
    occurredAt: DateTime.now().toUtc().toIso8601String(),
  );
}

class _StubFootprintRepository implements FootprintRepository {
  _StubFootprintRepository({required this.pages});

  final List<CursorPage<FootprintEntry>> pages;
  final List<String?> requestedTypes = <String?>[];
  final List<String?> requestedCursors = <String?>[];
  int _callIndex = 0;

  @override
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = 20,
  }) async {
    requestedTypes.add(type);
    requestedCursors.add(cursor);
    final page = pages[_callIndex < pages.length ? _callIndex : pages.length - 1];
    _callIndex++;
    return page;
  }
}

class _FailingFootprintRepository implements FootprintRepository {
  @override
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = 20,
  }) async {
    throw StateError('footprint unavailable');
  }
}
