import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/interest_match_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/ui/interest_match/pages/interest_match_page.dart';

const Key _searchMarker = ValueKey<String>('stub-search');
const Key _networkMarker = ValueKey<String>('stub-search-network');
const Key _intersectionsMarker = ValueKey<String>('stub-my-intersections');
const Key _homeMarker = ValueKey<String>('stub-home');
const Key _openInterestMatchMarker = ValueKey<String>(
  'stub-open-interest-match',
);

GoRouter _router({required String initialLocation}) {
  return GoRouter(
    initialLocation: initialLocation,
    routes: <RouteBase>[
      GoRoute(
        path: AppRoutePaths.home,
        builder: (context, _) => Scaffold(
          body: Center(
            child: TextButton(
              key: _openInterestMatchMarker,
              onPressed: () => context.push(AppRoutePaths.interestMatch),
              child: const Text('OPEN_INTEREST_MATCH'),
            ),
          ),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.interestMatch,
        builder: (_, _) => const InterestMatchPage(),
      ),
      GoRoute(
        path: AppRoutePaths.globalSearch,
        builder: (_, _) => const Scaffold(
          body: Center(child: Text('SEARCH', key: _searchMarker)),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.globalSearchNetworkResultsPathTemplate,
        builder: (_, _) => const Scaffold(
          body: Center(child: Text('NETWORK', key: _networkMarker)),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.myIntersectionsPathTemplate,
        builder: (_, _) => const Scaffold(
          body: Center(child: Text('INTERSECTIONS', key: _intersectionsMarker)),
        ),
      ),
    ],
  );
}

Future<void> _pump(WidgetTester tester) async {
  final router = GoRouter(
    initialLocation: AppRoutePaths.interestMatch,
    routes: <RouteBase>[
      GoRoute(
        path: AppRoutePaths.home,
        builder: (_, _) => const Scaffold(
          body: Center(child: Text('HOME', key: _homeMarker)),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.interestMatch,
        builder: (_, _) => const InterestMatchPage(),
      ),
      GoRoute(
        path: AppRoutePaths.globalSearch,
        builder: (_, _) => const Scaffold(
          body: Center(child: Text('SEARCH', key: _searchMarker)),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.globalSearchNetworkResultsPathTemplate,
        builder: (_, _) => const Scaffold(
          body: Center(child: Text('NETWORK', key: _networkMarker)),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.myIntersectionsPathTemplate,
        builder: (_, _) => const Scaffold(
          body: Center(child: Text('INTERSECTIONS', key: _intersectionsMarker)),
        ),
      ),
    ],
  );

  await tester.pumpWidget(
    ProviderScope(child: MaterialApp.router(routerConfig: router)),
  );
  await tester.pump();
  await tester.pump();
}

Future<void> _pumpRouter(
  WidgetTester tester, {
  required String initialLocation,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      child: MaterialApp.router(
        routerConfig: _router(initialLocation: initialLocation),
      ),
    ),
  );
  await tester.pump();
  await tester.pump();
}

void main() {
  group('InterestMatchPage 交集配对 launcher（local_contract）', () {
    testWidgets('渲染：返回、标题、今日机会、三段发现入口、搜索 CTA 与安全提示', (tester) async {
      await _pump(tester);

      expect(find.byKey(InterestMatchPage.viewKey), findsOneWidget);
      expect(find.byKey(InterestMatchPage.backButtonKey), findsOneWidget);
      expect(find.text(AppConceptConstants.interestMatchTitle), findsOneWidget);
      expect(find.byKey(InterestMatchPage.todayCtaKey), findsOneWidget);
      expect(find.byKey(InterestMatchPage.findPeopleKey), findsOneWidget);
      expect(find.byKey(InterestMatchPage.findCirclesKey), findsOneWidget);
      expect(find.byKey(InterestMatchPage.findPlacesKey), findsOneWidget);
      expect(find.byKey(InterestMatchPage.searchKey), findsOneWidget);
      await tester.scrollUntilVisible(
        find.byKey(InterestMatchPage.safetyNoteKey),
        160,
      );
      expect(find.text(InterestMatchTextConstants.safetyNote), findsOneWidget);
    });

    testWidgets('从加号入口 push 进入后，返回按钮 pop 回上一页', (tester) async {
      await _pumpRouter(tester, initialLocation: AppRoutePaths.home);

      await tester.tap(find.byKey(_openInterestMatchMarker));
      await tester.pumpAndSettle();
      expect(find.byKey(InterestMatchPage.viewKey), findsOneWidget);

      await tester.tap(find.byKey(InterestMatchPage.backButtonKey));
      await tester.pumpAndSettle();

      expect(find.byKey(_openInterestMatchMarker), findsOneWidget);
      expect(find.byKey(InterestMatchPage.viewKey), findsNothing);
    });

    testWidgets('深链直达时返回按钮兜底回首页', (tester) async {
      await _pumpRouter(tester, initialLocation: AppRoutePaths.interestMatch);

      await tester.tap(find.byKey(InterestMatchPage.backButtonKey));
      await tester.pumpAndSettle();

      expect(find.byKey(_openInterestMatchMarker), findsOneWidget);
      expect(find.byKey(InterestMatchPage.viewKey), findsNothing);
    });

    testWidgets('找同趣的人 → 导流到 /search/network 真实面', (tester) async {
      await _pump(tester);

      await tester.tap(find.byKey(InterestMatchPage.findPeopleKey));
      await tester.pumpAndSettle();

      expect(find.byKey(_networkMarker), findsOneWidget);
    });

    testWidgets('我的交集 → 导流到 /profile/intersections（我的交集）', (tester) async {
      await _pump(tester);

      await tester.tap(find.byKey(InterestMatchPage.todayCtaKey));
      await tester.pumpAndSettle();

      expect(find.byKey(_intersectionsMarker), findsOneWidget);
    });

    testWidgets('找圈子 / 按兴趣搜索 → 导流到 /search 真实面', (tester) async {
      await _pump(tester);

      await tester.tap(find.byKey(InterestMatchPage.findCirclesKey));
      await tester.pumpAndSettle();
      expect(find.byKey(_searchMarker), findsOneWidget);
    });

    testWidgets(
      '零伪候选（UAT-8 / 08-mock-isolation）：无候选列表/头像，无需任何 Repository 即渲染',
      (tester) async {
        // 无任何 Repository / 候选 provider override 也能完整渲染：证明 launcher 不依赖、
        // 也不自建第二套候选数据源（守 08-mock-isolation / R16）。
        await _pump(tester);

        expect(find.byKey(InterestMatchPage.viewKey), findsOneWidget);
        // 无候选卡头像 / 缩略图（伪候选的典型痕迹）。
        expect(find.byType(Image), findsNothing);
        // 页面只有固定导流入口（我的交集 + 三段发现 + 搜索），无动态生成的候选行。
        expect(find.byKey(InterestMatchPage.todayCtaKey), findsOneWidget);
        expect(find.byKey(InterestMatchPage.findPeopleKey), findsOneWidget);
        expect(find.byKey(InterestMatchPage.findCirclesKey), findsOneWidget);
        expect(find.byKey(InterestMatchPage.findPlacesKey), findsOneWidget);
        expect(find.byKey(InterestMatchPage.searchKey), findsOneWidget);
        // R-IX01-04 未闭前：不得出现「已按模型为你配同趣」等伪匹配结论断言。
        expect(find.textContaining('为你匹配'), findsNothing);
        expect(find.textContaining('已配对'), findsNothing);
      },
    );

    testWidgets('曝光埋点（R20）：进入 launcher 记录 page 曝光 interest_match', (
      tester,
    ) async {
      final recorder = _CapturingVisitRecorder();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [visitRecorderServiceProvider.overrideWithValue(recorder)],
          child: MaterialApp.router(
            routerConfig: _router(initialLocation: AppRoutePaths.interestMatch),
          ),
        ),
      );
      await tester.pump();
      await tester.pump();

      expect(
        recorder.recorded.map((t) => t.targetKey),
        contains(const VisitTarget.page('interest_match').targetKey),
      );
    });
  });
}

/// 捕获式访问记录器：断言 launcher 页面曝光埋点（不落 Hive / 不发远端）。
class _CapturingVisitRecorder extends VisitRecorderService {
  final List<VisitTarget> recorded = <VisitTarget>[];

  @override
  Future<void> recordVisit(VisitTarget target) async {
    recorded.add(target);
  }
}
