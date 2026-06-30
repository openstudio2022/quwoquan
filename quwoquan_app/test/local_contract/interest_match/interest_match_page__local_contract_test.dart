import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/interest_match_text_constants.dart';
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
  group('InterestMatchPage 找同趣 launcher（local_contract）', () {
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

    testWidgets('今日同趣机会 → 导流到 /profile/intersections（我的交集）', (tester) async {
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
  });
}
